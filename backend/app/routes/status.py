from fastapi import APIRouter, Depends
from ..core.config import settings
from ..core.deps import get_user_key
from ..core.db import get_session
from sqlmodel import Session, select
from datetime import datetime, timezone
from ..models.models import MonthlyUsage

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
    used = 0
    if user_key:
        now = datetime.now(timezone.utc)
        mu = session.exec(select(MonthlyUsage).where(MonthlyUsage.user_key == user_key, MonthlyUsage.year == now.year, MonthlyUsage.month == now.month)).first()
        used = mu.count if mu else 0
    return {
        "ok": True,
        "vip": False,
        "plan": "free",
        "unlimited": True,
        "used": used,
        "remaining": None,
        "limit": None,
    }
