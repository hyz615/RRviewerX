from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.entities import LocalUser, User
import bcrypt
from pydantic import BaseModel
from ..models.models import Vip, MonthlyUsage

router = APIRouter()


def require_admin(user_id: int | None, session: Session) -> LocalUser:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Only local users can be admins in this simplified model
    u = session.get(LocalUser, user_id)
    if not u or not u.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    return u


@router.get("/users")
def list_users(
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
    query: str | None = Query(default=None, description="email contains"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    require_admin(current, session)
    stmt = select(LocalUser)
    if query:
        like = f"%{query.lower()}%"
        stmt = stmt.where(LocalUser.email.ilike(like))
    total = len(session.exec(stmt).all())
    stmt = stmt.order_by(LocalUser.id.desc()).offset((page-1)*page_size).limit(page_size)
    rows = session.exec(stmt).all()
    return {"ok": True, "total": total, "page": page, "page_size": page_size, "items": [
        {"id": u.id, "email": u.email, "is_admin": u.is_admin, "disabled": u.disabled, "ban_reason": u.ban_reason, "ban_expires_at": (u.ban_expires_at.isoformat() if u.ban_expires_at else None), "created_at": u.created_at.isoformat()}
        for u in rows
    ]}


class DisableBody(BaseModel):
    reason: str | None = None
    expires_at: str | None = None  # ISO8601


@router.post("/users/{user_id}/disable")
def disable_user(user_id: int, body: DisableBody | None = None, current=Depends(get_current_user), session: Session = Depends(get_session)):
    require_admin(current, session)
    u = session.get(LocalUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.disabled = True
    # parse expires_at
    from datetime import datetime
    if body and body.expires_at:
        try:
            u.ban_expires_at = datetime.fromisoformat(body.expires_at)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid expires_at")
    else:
        u.ban_expires_at = None
    u.ban_reason = (body.reason if body and body.reason else None)
    session.add(u)
    session.commit()
    return {"ok": True}


@router.post("/users/{user_id}/enable")
def enable_user(user_id: int, current=Depends(get_current_user), session: Session = Depends(get_session)):
    require_admin(current, session)
    u = session.get(LocalUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.disabled = False
    u.ban_reason = None
    u.ban_expires_at = None
    session.add(u)
    session.commit()
    return {"ok": True}


class ResetPasswordBody:
    password: str


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: dict, current=Depends(get_current_user), session: Session = Depends(get_session)):
    require_admin(current, session)
    pw = (body or {}).get("password", "").strip()
    if not pw:
        raise HTTPException(status_code=400, detail="Password required")
    u = session.get(LocalUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.password_hash = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode()
    session.add(u)
    session.commit()
    return {"ok": True}


@router.get("/oauth-users")
def list_oauth_users(
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
    query: str | None = Query(default=None, description="email contains"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    require_admin(current, session)
    stmt = select(User)
    if query:
        like = f"%{(query or '').lower()}%"
        # email is optional
        from sqlmodel import or_
        stmt = stmt.where(or_(User.email.ilike(like), User.sub.ilike(like)))
    total = len(session.exec(stmt).all())
    stmt = stmt.order_by(User.id.desc()).offset((page-1)*page_size).limit(page_size)
    rows = session.exec(stmt).all()
    return {"ok": True, "total": total, "page": page, "page_size": page_size, "items": [
        {"id": u.id, "provider": u.provider, "sub": u.sub, "email": u.email, "disabled": getattr(u, 'disabled', False), "ban_reason": getattr(u, 'ban_reason', None), "ban_expires_at": (u.ban_expires_at.isoformat() if getattr(u, 'ban_expires_at', None) else None), "created_at": u.created_at.isoformat()}
        for u in rows
    ]}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, current=Depends(get_current_user), session: Session = Depends(get_session)):
    me = require_admin(current, session)
    if me.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    u = session.get(LocalUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(u)
    session.commit()
    return {"ok": True}


@router.post("/oauth-users/{user_id}/disable")
def disable_oauth_user(user_id: int, body: DisableBody | None = None, current=Depends(get_current_user), session: Session = Depends(get_session)):
    require_admin(current, session)
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.disabled = True
    from datetime import datetime
    if body and body.expires_at:
        try:
            u.ban_expires_at = datetime.fromisoformat(body.expires_at)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid expires_at")
    else:
        u.ban_expires_at = None
    u.ban_reason = (body.reason if body and body.reason else None)
    session.add(u)
    session.commit()
    return {"ok": True}


@router.post("/oauth-users/{user_id}/enable")
def enable_oauth_user(user_id: int, current=Depends(get_current_user), session: Session = Depends(get_session)):
    require_admin(current, session)
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.disabled = False
    u.ban_reason = None
    u.ban_expires_at = None
    session.add(u)
    session.commit()
    return {"ok": True}


# ------------- VIP admin management -------------


class VipGrantBody(BaseModel):
    user_key: str
    days: int  # e.g. 30|90|365


@router.get("/vip/status")
def vip_status(
    user_key: str,
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    require_admin(current, session)
    v = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
    if not v:
        return {"ok": True, "is_vip": False, "expires_at": None}
    return {"ok": True, "is_vip": bool(v.is_vip), "expires_at": (v.expires_at.isoformat() if v.expires_at else None)}


@router.post("/vip/grant")
def vip_grant(
    body: VipGrantBody,
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    require_admin(current, session)
    days = max(0, int(body.days or 0))
    if days <= 0:
        raise HTTPException(status_code=400, detail="days must be > 0")
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    v = session.exec(select(Vip).where(Vip.user_key == body.user_key)).first()
    if not v:
        v = Vip(user_key=body.user_key, is_vip=True, expires_at=now + timedelta(days=days))
        session.add(v)
    else:
        start = v.expires_at if v.expires_at and v.expires_at > now else now
        v.is_vip = True
        v.expires_at = start + timedelta(days=days)
        session.add(v)
    session.commit()
    return {"ok": True, "expires_at": (v.expires_at.isoformat() if v.expires_at else None)}


class VipCancelBody(BaseModel):
    user_key: str


@router.post("/vip/cancel")
def vip_cancel(
    body: VipCancelBody,
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    require_admin(current, session)
    v = session.exec(select(Vip).where(Vip.user_key == body.user_key)).first()
    if not v:
        # idempotent
        return {"ok": True}
    v.is_vip = False
    session.add(v)
    session.commit()
    return {"ok": True}


# ------------- Monthly usage admin -------------


@router.get("/usage/monthly")
def get_monthly_usage(
    user_key: str,
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    require_admin(current, session)
    from datetime import datetime
    now = datetime.utcnow()
    m = session.exec(select(MonthlyUsage).where(MonthlyUsage.user_key == user_key, MonthlyUsage.year == now.year, MonthlyUsage.month == now.month)).first()
    count = m.count if m else 0
    return {"ok": True, "user_key": user_key, "year": now.year, "month": now.month, "count": count}


class MonthlySetBody(BaseModel):
    user_key: str
    year: int | None = None
    month: int | None = None
    count: int


@router.post("/usage/monthly/set")
def set_monthly_usage(
    body: MonthlySetBody,
    current=Depends(get_current_user),
    session: Session = Depends(get_session),
):
    require_admin(current, session)
    from datetime import datetime
    year = body.year or datetime.utcnow().year
    month = body.month or datetime.utcnow().month
    m = session.exec(select(MonthlyUsage).where(MonthlyUsage.user_key == body.user_key, MonthlyUsage.year == year, MonthlyUsage.month == month)).first()
    if not m:
        m = MonthlyUsage(user_key=body.user_key, year=year, month=month, count=body.count)
        session.add(m)
    else:
        m.count = body.count
        m.updated_at = datetime.utcnow()
        session.add(m)
    session.commit()
    return {"ok": True}
