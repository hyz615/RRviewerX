from fastapi import Depends, Header, HTTPException, Response, Cookie
from typing import Optional
from .jwt import verify_jwt
from ..models.models import LocalUser, User
from .db import get_session
from sqlmodel import select
import re
import zlib


def _sub_to_uid(sub: str) -> int:
    m = re.match(r"^local:(\d+)$", sub)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    # stable non-negative int from sub
    return zlib.adler32(sub.encode("utf-8")) & 0x7FFFFFFF


def get_user_key(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        try:
            token = authorization.split(" ", 1)[1]
            payload = verify_jwt(token)
            sub = str(payload.get("sub") or "")
            provider = str(payload.get("provider") or "")
            if sub:
                # For local accounts, sub already includes 'local:{id}'
                if sub.startswith("local:"):
                    return sub
                # For OAuth or others, use 'provider:sub' if provider exists
                return f"{provider}:{sub}" if provider else sub
        except Exception:
            return None
    return None


def get_current_user(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Optional[int]:
    # Validate JWT and return a numeric user id (derived from sub)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            payload = verify_jwt(token)
            sub = str(payload.get("sub") or "")
            provider = str(payload.get("provider") or "")
            if sub:
                # Ban enforcement: if mapped to LocalUser and disabled -> reject
                try:
                    with next(get_session()) as s:  # type: ignore
                        from datetime import datetime
                        if sub.startswith("local:"):
                            try:
                                lid = int(sub.split(":",1)[1])
                                u = s.get(LocalUser, lid)
                                if u and u.disabled:
                                    # auto-unban if expired
                                    if u.ban_expires_at and u.ban_expires_at < datetime.utcnow():
                                        u.disabled = False; u.ban_reason=None; u.ban_expires_at=None; s.add(u); s.commit()
                                    else:
                                        return None
                            except Exception:
                                pass
                        else:
                            ou = s.exec(select(User).where(User.provider == provider, User.sub == sub)).first()
                            if ou and getattr(ou, 'disabled', False):
                                if getattr(ou, 'ban_expires_at', None) and ou.ban_expires_at < datetime.utcnow():
                                    ou.disabled = False; ou.ban_reason=None; ou.ban_expires_at=None; s.add(ou); s.commit()
                                else:
                                    return None
                except Exception:
                    pass
                return _sub_to_uid(sub)
        except Exception:
            return None
    return None


def require_auth_or_trial(
    response: Response,
    user_id: Optional[str] = Depends(get_current_user),
    rr_trial: Optional[str] = Cookie(default=None),
):
    # Allow if user logged in
    if user_id is not None:
        return {"user_id": user_id, "trial": False}
    # Trial session: allow if no cookie (set active) or if cookie==active
    if rr_trial is None:
        response.set_cookie(
            key="rr_trial",
            value="active",
            max_age=60 * 60 * 24 * 3,
            httponly=False,
            samesite="lax",
            path="/",
        )
        return {"user_id": None, "trial": True}
    if rr_trial == "active":
        return {"user_id": None, "trial": True}
    # Otherwise reject
    raise HTTPException(status_code=401, detail="Login required (trial already used)")
