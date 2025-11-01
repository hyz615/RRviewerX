from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional, List, Dict, Any
from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.models import ReviewSheet, FileMeta


router = APIRouter()


@router.get("")
def list_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    uid: Optional[int] = Depends(get_current_user),
):
    if uid is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    q = select(ReviewSheet).where(ReviewSheet.user_id == uid).order_by(ReviewSheet.created_at.desc()).limit(limit).offset(offset)
    items: List[ReviewSheet] = session.exec(q).all()
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
            "preview": preview(it.content or ""),
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
        "text": rs.content or "",
    }
