from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional, List, Dict, Any
from sqlalchemy import or_
from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.models import ReviewSheet, FileMeta
from ..services.course_service import load_json_list


router = APIRouter()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_subject_code(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    return cleaned.lower() if cleaned else None


def _normalize_exam_type(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    return cleaned.lower() if cleaned else None


@router.get("")
def list_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(default=None, description="Search in content/kind"),
    kind: Optional[str] = Query(default=None, description="Filter by kind"),
    fav: Optional[bool] = Query(default=None, description="Only favorites"),
    subject_code: Optional[str] = Query(default=None, description="Filter by subject"),
    course_name: Optional[str] = Query(default=None, description="Filter by course name"),
    exam_type: Optional[str] = Query(default=None, description="Filter by exam type"),
    exam_name: Optional[str] = Query(default=None, description="Filter by exam name"),
    session: Session = Depends(get_session),
    uid: Optional[int] = Depends(get_current_user),
):
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    normalized_subject_code = _normalize_subject_code(subject_code)
    normalized_course_name = _clean_optional_text(course_name)
    normalized_exam_type = _normalize_exam_type(exam_type)
    normalized_exam_name = _clean_optional_text(exam_name)
    stmt = select(ReviewSheet).where(ReviewSheet.user_id == uid)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            ReviewSheet.content.ilike(pattern),
            ReviewSheet.kind.ilike(pattern),
            ReviewSheet.course_name.ilike(pattern),
            ReviewSheet.exam_name.ilike(pattern),
            ReviewSheet.selected_chapter_labels.ilike(pattern),
        ))
    if kind:
        stmt = stmt.where(ReviewSheet.kind == kind.lower())
    if fav is True:
        stmt = stmt.where(ReviewSheet.is_favorite == True)
    if normalized_subject_code:
        stmt = stmt.where(ReviewSheet.subject_code == normalized_subject_code)
    if normalized_course_name:
        stmt = stmt.where(ReviewSheet.course_name.ilike(normalized_course_name))
    if normalized_exam_type:
        stmt = stmt.where(ReviewSheet.exam_type == normalized_exam_type)
    if normalized_exam_name:
        stmt = stmt.where(ReviewSheet.exam_name.ilike(normalized_exam_name))
    stmt = stmt.order_by(ReviewSheet.created_at.desc()).limit(limit).offset(offset)
    items: List[ReviewSheet] = session.exec(stmt).all()
    # Map source filenames
    src_ids = [it.source_id for it in items if it.source_id]
    fn_map: Dict[int, str] = {}
    if src_ids:
        metas = session.exec(select(FileMeta).where(FileMeta.id.in_(src_ids))).all()
        fn_map = {m.id: m.filename for m in metas if m and m.id}
    def preview(txt: str, n: int = 160) -> str:
        if not txt:
            return ""
        s = txt.strip().replace("\r", "").replace("\n", " ")
        return s[:n]
    data = [
        {
            "id": it.id,
            "kind": it.kind,
            "created_at": it.created_at.isoformat() if it.created_at else None,
            "source_id": it.source_id,
            "source_name": fn_map.get(it.source_id) if it.source_id else None,
            "subject_code": it.subject_code,
            "course_name": it.course_name,
            "exam_type": it.exam_type,
            "exam_name": it.exam_name,
            "selected_chapter_ids": load_json_list(it.selected_chapter_ids),
            "selected_chapter_labels": load_json_list(it.selected_chapter_labels),
            "preview": preview(it.content or ""),
            "is_favorite": bool(it.is_favorite),
        }
        for it in items
    ]
    return {"ok": True, "items": data}


@router.get("/{rid}")
def get_history_item(rid: int, session: Session = Depends(get_session), uid: Optional[int] = Depends(get_current_user)):
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    rs = session.get(ReviewSheet, rid)
    if not rs or rs.user_id != uid:
        raise HTTPException(status_code=404, detail="Not found")
    src_name = None
    if rs.source_id:
        fm = session.get(FileMeta, rs.source_id)
        if fm:
            src_name = fm.filename
    return {
        "ok": True,
        "id": rs.id,
        "kind": rs.kind,
        "created_at": rs.created_at.isoformat() if rs.created_at else None,
        "source_id": rs.source_id,
        "source_name": src_name,
        "subject_code": rs.subject_code,
        "course_name": rs.course_name,
        "exam_type": rs.exam_type,
        "exam_name": rs.exam_name,
        "selected_chapter_ids": load_json_list(rs.selected_chapter_ids),
        "selected_chapter_labels": load_json_list(rs.selected_chapter_labels),
        "text": rs.content or "",
        "is_favorite": bool(rs.is_favorite),
    }


@router.post("/{rid}/favorite")
def toggle_favorite(rid: int, session: Session = Depends(get_session), uid: Optional[int] = Depends(get_current_user)):
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    rs = session.get(ReviewSheet, rid)
    if not rs or rs.user_id != uid:
        raise HTTPException(status_code=404, detail="Not found")
    rs.is_favorite = not rs.is_favorite
    session.add(rs)
    session.commit()
    return {"ok": True, "is_favorite": rs.is_favorite}


@router.delete("/{rid}")
def delete_history_item(rid: int, session: Session = Depends(get_session), uid: Optional[int] = Depends(get_current_user)):
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    rs = session.get(ReviewSheet, rid)
    if not rs or rs.user_id != uid:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(rs)
    session.commit()
    return {"ok": True}
