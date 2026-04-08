from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..core.db import get_session
from ..core.deps import get_current_user
from ..services.course_service import (
    clean_optional_text,
    normalize_subject_code,
    replace_course_structure,
    resolve_course,
    serialize_course_structure,
)


router = APIRouter()


class ChapterInput(BaseModel):
    id: int | None = None
    title: str


class UnitInput(BaseModel):
    id: int | None = None
    title: str
    chapters: list[ChapterInput] = Field(default_factory=list)


class CourseStructureRequest(BaseModel):
    subject_code: str | None = None
    course_name: str
    units: list[UnitInput] = Field(default_factory=list)


def _require_user(uid: int | None) -> int:
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return uid


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
            )
        ).all()
        result.append({
            "id": c.id,
            "subject_code": c.subject_code,
            "course_name": c.course_name,
            "source_count": len(file_count),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return {"ok": True, "courses": result}


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