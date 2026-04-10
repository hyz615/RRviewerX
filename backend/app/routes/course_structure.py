import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlmodel import Session

from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.models import FileMeta
from ..services.agent_service import infer_textbook_structure
from ..services.course_service import (
    clean_optional_text,
    delete_course_textbook_chapters,
    delete_course_bundle,
    get_course_textbook,
    normalize_subject_code,
    replace_course_textbook_chapters,
    replace_course_structure,
    resolve_course,
    serialize_course_structure,
)
from ..services.file_service import sniff_and_read


router = APIRouter()


class ChapterInput(BaseModel):
    id: int | None = None
    title: str


class UnitInput(BaseModel):
    id: int | None = None
    title: str
    chapters: list[ChapterInput] = Field(default_factory=list)


class EnsureCourseRequest(BaseModel):
    subject_code: str | None = None
    course_name: str


class CourseStructureRequest(BaseModel):
    subject_code: str | None = None
    course_name: str
    units: list[UnitInput] = Field(default_factory=list)


def _require_user(uid: int | None) -> int:
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return uid


def _store_uploaded_textbook(
    session: Session,
    user_id: int,
    subject_code: str | None,
    course_name: str,
    file: UploadFile,
    raw: bytes,
) -> FileMeta:
    file_meta = FileMeta(
        filename=file.filename or "course_textbook",
        content_type=file.content_type or None,
        size=len(raw),
        user_id=user_id,
        subject_code=subject_code,
        course_name=course_name,
        source_role="textbook",
    )
    session.add(file_meta)
    session.commit()

    base_dir = Path(__file__).resolve().parents[2] / "storage" / "uploads"
    base_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{file_meta.id}_{file_meta.filename}"
    path = base_dir / safe_name
    with open(path, "wb") as handle:
        handle.write(raw)

    file_meta.stored_path = str(path)
    session.add(file_meta)
    session.commit()
    session.refresh(file_meta)
    return file_meta


def _flatten_structure_chapters(structure: dict[str, Any] | None) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for unit in (structure or {}).get("units") or []:
        for chapter in unit.get("chapters") or []:
            flattened.append(chapter)
    return flattened


def _flatten_inferred_chapters(units: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for unit in units or []:
        for chapter in unit.get("chapters") or []:
            flattened.append(chapter)
    return flattened


@router.get("/list")
def list_courses(
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    """Return all courses belonging to the current user (lightweight, no full structure)."""
    from sqlmodel import select as sel
    from ..models.models import Course, FileMeta
    user_id = _require_user(uid)
    courses = list(session.exec(
        sel(Course).where(Course.user_id == user_id).order_by(Course.created_at.desc())
    ).all())
    result = []
    for c in courses:
        file_count = session.exec(
            sel(FileMeta.id).where(
                FileMeta.user_id == user_id,
                FileMeta.subject_code == c.subject_code,
                FileMeta.course_name == c.course_name,
                or_(FileMeta.source_role.is_(None), FileMeta.source_role == "material"),
            )
        ).all()
        result.append({
            "id": c.id,
            "subject_code": c.subject_code,
            "course_name": c.course_name,
            "source_count": len(file_count),
            "has_textbook": bool(c.textbook_file_id),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return {"ok": True, "courses": result}


@router.post("/ensure")
def ensure_course(
    payload: EnsureCourseRequest,
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    user_id = _require_user(uid)
    normalized_course_name = clean_optional_text(payload.course_name)
    if not normalized_course_name:
        raise HTTPException(status_code=400, detail="course_name is required")

    course = resolve_course(
        session,
        user_id,
        normalize_subject_code(payload.subject_code),
        normalized_course_name,
        create_if_missing=True,
    )
    if course is None:
        raise HTTPException(status_code=400, detail="Failed to resolve course")

    return {"ok": True, "course": serialize_course_structure(session, course)}


@router.delete("")
def delete_course(
    subject_code: str | None = Query(default=None),
    course_name: str | None = Query(default=None),
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    user_id = _require_user(uid)
    normalized_course_name = clean_optional_text(course_name)
    if not normalized_course_name:
        raise HTTPException(status_code=400, detail="course_name is required")

    result = delete_course_bundle(
        session,
        user_id,
        normalize_subject_code(subject_code),
        normalized_course_name,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Course not found")

    removed_stored_file_count = 0
    for stored_path in result.get("stored_paths", []):
        if not stored_path:
            continue
        try:
            if os.path.exists(stored_path):
                os.remove(stored_path)
                removed_stored_file_count += 1
        except Exception:
            continue

    return {
        "ok": True,
        "subject_code": result["subject_code"],
        "course_name": result["course_name"],
        "removed_course": result["removed_course"],
        "removed_file_count": result["removed_file_count"],
        "removed_review_count": result["removed_review_count"],
        "removed_unit_count": result["removed_unit_count"],
        "removed_chapter_count": result["removed_chapter_count"],
        "removed_stored_file_count": removed_stored_file_count,
    }


@router.get("")
def get_structure(
    subject_code: str | None = Query(default=None),
    course_name: str | None = Query(default=None),
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    user_id = _require_user(uid)
    normalized_course_name = clean_optional_text(course_name)
    if not normalized_course_name:
        return {"ok": True, "course": None}

    course = resolve_course(
        session,
        user_id,
        normalize_subject_code(subject_code),
        normalized_course_name,
        create_if_missing=False,
    )
    return {"ok": True, "course": serialize_course_structure(session, course)}


@router.put("")
def put_structure(
    payload: CourseStructureRequest,
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    user_id = _require_user(uid)
    normalized_course_name = clean_optional_text(payload.course_name)
    if not normalized_course_name:
        raise HTTPException(status_code=400, detail="course_name is required")

    course = resolve_course(
        session,
        user_id,
        normalize_subject_code(payload.subject_code),
        normalized_course_name,
        create_if_missing=True,
    )
    if course is None:
        raise HTTPException(status_code=400, detail="Failed to resolve course")

    structure = replace_course_structure(
        session,
        course,
        [unit.model_dump() for unit in payload.units],
    )
    return {"ok": True, "course": structure}


@router.post("/textbook")
async def upload_textbook(
    file: UploadFile = File(...),
    subject_code: str | None = Form(default=None),
    course_name: str | None = Form(default=None),
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    user_id = _require_user(uid)
    normalized_subject_code = normalize_subject_code(subject_code)
    normalized_course_name = clean_optional_text(course_name)
    if not normalized_course_name:
        raise HTTPException(status_code=400, detail="course_name is required")

    raw = await file.read()
    extracted = sniff_and_read(file.filename or "course_textbook", raw) or (raw.decode(errors="ignore") if raw else "")
    if not extracted.strip():
        raise HTTPException(status_code=400, detail="Unable to extract textbook text")

    course = resolve_course(
        session,
        user_id,
        normalized_subject_code,
        normalized_course_name,
        create_if_missing=True,
    )
    if course is None:
        raise HTTPException(status_code=400, detail="Failed to resolve course")

    textbook_meta = _store_uploaded_textbook(
        session,
        user_id,
        course.subject_code,
        course.course_name,
        file,
        raw,
    )

    inferred = infer_textbook_structure(extracted, textbook_meta.filename)
    units_payload = [
        {
            "title": str(unit.get("title") or "").strip() or ("教材章节"),
            "chapters": [
                {"title": str(chapter.get("title") or "").strip()}
                for chapter in unit.get("chapters") or []
                if str(chapter.get("title") or "").strip()
            ],
        }
        for unit in inferred.get("units") or []
        if str(unit.get("title") or "").strip() or (unit.get("chapters") or [])
    ]
    if not units_payload:
        raise HTTPException(status_code=400, detail="Failed to infer textbook chapters")

    structure = replace_course_structure(session, course, units_payload)
    flat_structure_chapters = _flatten_structure_chapters(structure)
    flat_inferred_chapters = _flatten_inferred_chapters(inferred.get("units") or [])
    segment_payload = []
    for index, chapter in enumerate(flat_structure_chapters):
        content = ""
        if index < len(flat_inferred_chapters):
            content = str(flat_inferred_chapters[index].get("content") or "").strip()
        if not content:
            continue
        segment_payload.append({
            "chapter_id": chapter.get("id"),
            "content": content,
        })

    course.textbook_file_id = textbook_meta.id
    session.add(course)
    session.commit()
    session.refresh(course)
    replace_course_textbook_chapters(session, course, textbook_meta.id, segment_payload)

    return {
        "ok": True,
        "course": serialize_course_structure(session, course),
        "strategy": inferred.get("strategy"),
        "textbook_chars": len(extracted),
        "chapter_count": len(flat_structure_chapters),
    }


@router.delete("/textbook")
def delete_textbook(
    subject_code: str | None = Query(default=None),
    course_name: str | None = Query(default=None),
    session: Session = Depends(get_session),
    uid: int | None = Depends(get_current_user),
):
    user_id = _require_user(uid)
    normalized_course_name = clean_optional_text(course_name)
    if not normalized_course_name:
        raise HTTPException(status_code=400, detail="course_name is required")

    course = resolve_course(
        session,
        user_id,
        normalize_subject_code(subject_code),
        normalized_course_name,
        create_if_missing=False,
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    textbook = get_course_textbook(session, course)
    if textbook is None:
        raise HTTPException(status_code=404, detail="Textbook not found")

    delete_course_textbook_chapters(session, course.id)
    course.textbook_file_id = None
    session.add(course)
    session.commit()
    session.refresh(course)

    return {
        "ok": True,
        "course": serialize_course_structure(session, course),
    }