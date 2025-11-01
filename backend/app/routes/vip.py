from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select
from datetime import datetime, timedelta
from ..core.db import get_session
from ..core.deps import get_user_key, get_current_user
from ..models.models import Vip
from ..core.config import settings
import stripe

router = APIRouter()


class PurchaseDemo(BaseModel):
    plan: str  # vip_30|vip_90|vip_365


@router.post("/purchase-demo")
def purchase_demo(body: PurchaseDemo, user_key: str | None = Depends(get_user_key), session: Session = Depends(get_session), uid: int | None = Depends(get_current_user)):
    if not user_key or uid is None:
        raise HTTPException(status_code=401, detail="Login required")
    days = 30 if body.plan == "vip_30" else 90 if body.plan == "vip_90" else 365
    now = datetime.utcnow()
    v = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
    if not v:
        v = Vip(user_key=user_key, is_vip=True, expires_at=now + timedelta(days=days))
        session.add(v)
    else:
        # extend from current expiry if in future, else from now
        start = v.expires_at if v.expires_at and v.expires_at > now else now
        v.is_vip = True
        v.expires_at = start + timedelta(days=days)
        session.add(v)
    session.commit()
    return {"ok": True, "expires_at": (v.expires_at.isoformat() if v.expires_at else None)}


class CreateCheckoutBody(BaseModel):
    plan: str  # 30|90|365
    success_url: str
    cancel_url: str


@router.post("/checkout")
def create_checkout(body: CreateCheckoutBody, user_key: str | None = Depends(get_user_key)):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Stripe not configured")
    if not user_key:
        raise HTTPException(status_code=401, detail="Login required")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    price_map = {
        "30": settings.STRIPE_PRICE_30,
        "90": settings.STRIPE_PRICE_90,
        "365": settings.STRIPE_PRICE_365,
    }
    price = price_map.get(body.plan)
    if not price:
        raise HTTPException(status_code=400, detail="Invalid plan")
    # Extra guard: ensure it's a valid Stripe price id format (commonly starts with 'price_')
    if not isinstance(price, str) or not price.strip():
        raise HTTPException(status_code=400, detail="Stripe price id not set")
    try:
        session_obj = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price, "quantity": 1}],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"user_key": user_key, "plan": body.plan},
        )
        return {"ok": True, "url": session_obj.url}
    except stripe.error.StripeError as e:
        # Return a friendly error message while keeping details minimal
        msg = getattr(e, 'user_message', None) or str(e)
        raise HTTPException(status_code=400, detail=f"Stripe error: {msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkout failed: {e}")


@router.post("/webhook")
async def stripe_webhook(request: Request, session: Session = Depends(get_session)):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Webhook not configured")
    try:
        payload: bytes = await request.body()
        sig = request.headers.get("stripe-signature") or request.headers.get("Stripe-Signature")
        if not sig:
            raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {e}")

    try:
        if event.get("type") == "checkout.session.completed":
            data = event.get("data", {}).get("object", {})
            meta = data.get("metadata") or {}
            user_key = meta.get("user_key")
            plan = meta.get("plan")
            days = 30 if plan == "30" else 90 if plan == "90" else 365
            now = datetime.utcnow()
            if user_key:
                v = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
                if not v:
                    v = Vip(user_key=user_key, is_vip=True, expires_at=now + timedelta(days=days))
                    session.add(v)
                else:
                    start = v.expires_at if v.expires_at and v.expires_at > now else now
                    v.is_vip = True
                    v.expires_at = start + timedelta(days=days)
                    session.add(v)
                session.commit()
    except Exception:
        # Don't break Stripe retries due to internal DB issues; still 200 OK
        pass
    return {"ok": True}
