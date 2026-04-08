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