from fastapi import APIRouter, Depends
from ..core.config import settings
from ..core.deps import get_user_key
from ..core.db import get_session
from sqlmodel import Session, select
from datetime import date, datetime
from ..models.models import Vip, UsageCounter
from ..models.models import Vip, MonthlyUsage
from datetime import date, datetime

router = APIRouter()


@router.get("/ai")
def ai_status():
    provider = (settings.LLM_PROVIDER or "mock").lower()
    model = settings.LLM_MODEL
    has_key = bool(settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY)
    ready = (provider == 'mock') or has_key
    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "has_key": has_key,
        "ready": ready,
    }


@router.get("/quota")
def quota_status(user_key: str | None = Depends(get_user_key), session: Session = Depends(get_session)):
    # Anonymous/trial users: cannot attribute usage -> show generic free quota (5/month)
    if not user_key:
        return {"ok": True, "vip": False, "used": 0, "remaining": 5, "limit": 5}
    # Compute current month used count
    now = datetime.utcnow()
    mu = session.exec(select(MonthlyUsage).where(MonthlyUsage.user_key == user_key, MonthlyUsage.year == now.year, MonthlyUsage.month == now.month)).first()
    used = mu.count if mu else 0
    # VIP status
    vip = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
    is_vip = bool(vip and vip.is_vip and (vip.expires_at is None or vip.expires_at > datetime.utcnow()))
    if is_vip:
        return {
            "ok": True,
            "vip": True,
            "used": used,
            "remaining": None,
            "limit": None,
            "expires_at": (vip.expires_at.isoformat() if vip and vip.expires_at else None),
        }
    # Non-VIP: monthly limit applies
    limit = getattr(settings, 'FREE_MONTHLY_LIMIT', 5)
    remaining = max(0, limit - used)
    return {"ok": True, "vip": False, "used": used, "remaining": remaining, "limit": limit}
