from fastapi import APIRouter, Depends
from ..core.config import settings
from ..core.deps import get_user_key
from ..core.db import get_session
from sqlmodel import Session
from ..services.generation_stats_service import get_monthly_generation_count, get_site_generation_total

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
    used = get_monthly_generation_count(session, user_key)
    return {
        "ok": True,
        "vip": False,
        "plan": "free",
        "unlimited": True,
        "used": used,
        "remaining": None,
        "limit": None,
        "site_generation_total": get_site_generation_total(session),
    }
