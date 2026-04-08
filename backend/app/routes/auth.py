from fastapi import APIRouter, Cookie, Request, Response, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from ..core.config import settings
from ..core.jwt import sign_jwt
from urllib.parse import urlencode
from urllib.parse import urlparse, urlunparse, parse_qsl
import json
import logging
from authlib.integrations.starlette_client import OAuth, OAuthError
import os
from sqlmodel import Session, select
from ..core.db import get_session
from ..models.entities import LocalUser
from ..models.models import User as OauthUser
import bcrypt
import base64, os, random, string, time
import jwt
import hmac, hashlib
from typing import Dict, Tuple
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("rrviewer.auth")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    provider: str  # google|microsoft|anonymous


oauth = OAuth()

def _register_oauth_clients():
    # Register Google
    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        if 'google' not in oauth._clients:
            oauth.register(
                name='google',
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                client_kwargs={'scope': 'openid email profile'},
            )
    # Register Microsoft (common tenant)
    if settings.MICROSOFT_CLIENT_ID and settings.MICROSOFT_CLIENT_SECRET:
        if 'microsoft' not in oauth._clients:
            oauth.register(
                name='microsoft',
                client_id=settings.MICROSOFT_CLIENT_ID,
                client_secret=settings.MICROSOFT_CLIENT_SECRET,
                server_metadata_url='https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration',
                client_kwargs={'scope': 'openid email profile'},
            )


_register_oauth_clients()


@router.post("/login")
def login(payload: LoginRequest):
    # Placeholder login; return a fake session token
    provider = payload.provider.lower()
    if provider in ("google", "microsoft"):
        # In a full flow, redirect URL should be returned for front-end to navigate.
        return {"ok": True, "provider": provider, "auth_url": f"/auth/oauth/{provider}/start"}
    # anonymous fallback for development
    return {"ok": True, "provider": provider, "token": sign_jwt("dev-user", provider)}


class RegisterLocal(BaseModel):
    email: str
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None


@router.post("/register")
@limiter.limit("5/minute")
def register_local(request: Request, payload: RegisterLocal, session: Session = Depends(get_session)):
    email = payload.email.strip().lower()
    if not email or not payload.password:
        return JSONResponse({"ok": False, "error": "Email and password required"}, status_code=400)
    # captcha required
    if not _verify_captcha(payload.captcha_id, payload.captcha_code):
        return JSONResponse({"ok": False, "error": "Invalid captcha"}, status_code=400)
    # check exists
    exists = session.exec(select(LocalUser).where(LocalUser.email == email)).first()
    if exists:
        return JSONResponse({"ok": False, "error": "Email already registered"}, status_code=400)
    pw_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode()
    user = LocalUser(email=email, password_hash=pw_hash)
    session.add(user)
    session.commit()
    token = sign_jwt(f"local:{user.id}", "local")
    return {"ok": True, "token": token}


class LoginLocal(BaseModel):
    email: str
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None


@router.post("/login-local")
@limiter.limit("10/minute")
def login_local(request: Request, payload: LoginLocal, session: Session = Depends(get_session)):
    email = payload.email.strip().lower()
    # captcha required
    if not _verify_captcha(payload.captcha_id, payload.captcha_code):
        return JSONResponse({"ok": False, "error": "Invalid captcha"}, status_code=400)
    user = session.exec(select(LocalUser).where(LocalUser.email == email)).first()
    if not user:
        return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=400)
    if user.disabled:
        if user.ban_expires_at and user.ban_expires_at < datetime.now(timezone.utc):
            user.disabled = False; user.ban_reason=None; user.ban_expires_at=None; session.add(user); session.commit()
        else:
            return JSONResponse({"ok": False, "error": (user.ban_reason or "User disabled")}, status_code=403)
    if not bcrypt.checkpw(payload.password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=400)
    token = sign_jwt(f"local:{user.id}", "local")
    return {"ok": True, "token": token}


# ===== Forgot / Reset password via Resend =====
class ForgotPayload(BaseModel):
    email: str

class ResetPayload(BaseModel):
    token: str
    new_password: str

def _make_reset_token(user_id: int, email: str) -> str:
    now = int(time.time())
    payload = {"sub": f"local:{user_id}", "email": email, "iat": now, "exp": now + 15*60, "kind": "pwd_reset"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def _verify_reset_token(tok: str) -> dict | None:
    try:
        data = jwt.decode(tok, settings.SECRET_KEY, algorithms=["HS256"])
        if data.get("kind") != "pwd_reset":
            return None
        return data
    except Exception:
        return None

def _send_resend_email(to_email: str, subject: str, html: str) -> tuple[bool, str | None]:
    api_key = settings.RESEND_API_KEY
    sender = settings.EMAIL_FROM or "no-reply@example.com"
    if not api_key:
        return False, "RESEND_API_KEY not configured"
    data = json.dumps({"from": sender, "to": [to_email], "subject": subject, "html": html}).encode("utf-8")
    req = urllib.request.Request("https://api.resend.com/emails", data=data, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                return True, None
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as he:
        try:
            body = he.read().decode("utf-8")
        except Exception:
            body = str(he)
        return False, f"HTTPError: {body}"
    except Exception as e:
        return False, str(e)

@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(payload: ForgotPayload, request: Request, session: Session = Depends(get_session)):
    email = (payload.email or "").strip().lower()
    if not email:
        return JSONResponse({"ok": False, "error": "Email required"}, status_code=400)
    user = session.exec(select(LocalUser).where(LocalUser.email == email)).first()
    # Always respond ok to avoid user enumeration
    if not user:
        return {"ok": True}
    tok = _make_reset_token(user.id, email)
    # Build reset link
    front = settings.FRONTEND_BASE
    if not front:
        # derive from request.headers['origin'] or fallback to first allowed origin
        front = request.headers.get('origin') or (settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "http://localhost:8080")
    link = f"{front.rstrip('/')}/reset.html#token={tok}"
    html = (
        f"<div>\n"
        f"  <p>点击以下链接重置密码�?5分钟内有效）�?/p>\n"
        f"  <p><a href=\"{link}\">{link}</a></p>\n"
        f"  <hr/>\n"
        f"  <p>Click the link below to reset your password (valid for 15 minutes):</p>\n"
        f"  <p><a href=\"{link}\">{link}</a></p>\n"
        f"</div>"
    )
    ok, err = _send_resend_email(email, "重置密码", html)
    if not ok:
        # 记录失败但仍返回 ok，避免泄�?
        return {"ok": True, "warn": "email_failed"}
    return {"ok": True}

@router.post("/reset-password")
def reset_password(payload: ResetPayload, session: Session = Depends(get_session)):
    data = _verify_reset_token(payload.token or "")
    if not data:
        return JSONResponse({"ok": False, "error": "Invalid or expired token"}, status_code=400)
    sub = data.get("sub") or ""
    if not sub.startswith("local:"):
        return JSONResponse({"ok": False, "error": "Invalid token subject"}, status_code=400)
    uid = int(sub.split(":",1)[1])
    user = session.get(LocalUser, uid)
    if not user:
        return JSONResponse({"ok": False, "error": "User not found"}, status_code=404)
    new_pw = payload.new_password or ""
    # Password strength: >=8, include lower/upper/digit
    if len(new_pw) < 8 or not re.search(r"[a-z]", new_pw) or not re.search(r"[A-Z]", new_pw) or not re.search(r"\d", new_pw):
        return JSONResponse({"ok": False, "error": "密码强度不足：至�?位，需含大小写与数�?/ Password too weak: min 8 chars incl. upper/lower/digit"}, status_code=400)
    user.password_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode()
    session.add(user); session.commit()
    return {"ok": True}


@router.get("/trial-status")
def trial_status(rr_trial: str | None = Cookie(default=None)):
    return {"trial_used": False}


@router.get("/oauth/{provider}/start")
async def oauth_start(provider: str, request: Request):
    provider = provider.lower()
    # Base redirect_uri to our callback
    # Prefer explicit OAUTH_REDIRECT_BASE to avoid scheme/host mismatch behind proxies
    if settings.OAUTH_REDIRECT_BASE:
        redirect_uri = settings.OAUTH_REDIRECT_BASE.rstrip('/') + f"/auth/oauth/{provider}/callback"
    else:
        redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    # Capture frontend origin to carry in OAuth state (do NOT mutate redirect_uri, Google requires exact match)
    front = request.query_params.get('front')
    # Use Authlib if configured
    if provider in oauth._clients:
        client = oauth.create_client(provider)
        st = json.dumps({"front": front}) if front else None
        return await client.authorize_redirect(request, redirect_uri, state=st)
    # Fallback: construct authorization URL if client_id available
    if provider == "google":
        client_id = settings.GOOGLE_CLIENT_ID or os.getenv("GOOGLE_CLIENT_ID")
        if not client_id:
            return JSONResponse({"ok": False, "error": "Google OAuth not configured"}, status_code=400)
        scope = "openid email profile"
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?" +
            urlencode({
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scope,
                "access_type": "online",
                "prompt": "consent",
            })
        )
        return {"ok": True, "auth_url": auth_url}
    if provider == "microsoft":
        client_id = settings.MICROSOFT_CLIENT_ID or os.getenv("MICROSOFT_CLIENT_ID")
        if not client_id:
            return JSONResponse({"ok": False, "error": "Microsoft OAuth not configured"}, status_code=400)
        scope = "openid email profile"
        tenant = "common"
        auth_url = (
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?" +
            urlencode({
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scope,
            })
        )
        return {"ok": True, "auth_url": auth_url}
    return JSONResponse({"ok": False, "error": "Unknown provider"}, status_code=400)


@router.get("/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(provider: str, request: Request, response: Response, code: str | None = None, error: str | None = None):
    if error:
        return JSONResponse({"ok": False, "error": error}, status_code=400)
    sub = None
    provider = provider.lower()
    # If Authlib client configured, exchange code
    email_from_idp = None
    if provider in oauth._clients:
        try:
            client = oauth.create_client(provider)
            token = await client.authorize_access_token(request)
            # Try OIDC userinfo / id_token
            userinfo = token.get('userinfo')
            if not userinfo:
                try:
                    userinfo = await client.parse_id_token(request, token)
                except Exception:
                    userinfo = None
            if userinfo and 'sub' in userinfo:
                sub = str(userinfo['sub'])
                # capture email if available
                try:
                    email_from_idp = userinfo.get('email') if isinstance(userinfo, dict) else None
                except Exception:
                    email_from_idp = None
            elif 'id_token' in token:
                sub = provider + "-user"
        except OAuthError as oe:
            return JSONResponse({"ok": False, "error": str(oe)}, status_code=400)
        except Exception as e:
            # Graceful fallback
            sub = provider + "-user"
    # Fallback: demo subject
    if not sub:
        sub = provider + "-user"
    # Ensure OAuth user exists in DB; if disabled, block
    try:
        from ..core.db import get_session
        from sqlmodel import Session, select
        with next(get_session()) as s:  # type: ignore
            ou = s.exec(select(OauthUser).where(OauthUser.provider == provider, OauthUser.sub == sub)).first()
            created = False
            if not ou:
                # create record so that admin can manage this OAuth user
                try:
                    ou = OauthUser(provider=provider, sub=sub, email=email_from_idp)
                    s.add(ou); s.commit(); s.refresh(ou)
                    created = True
                except Exception:
                    pass
            else:
                # update email if newly available
                try:
                    if email_from_idp and getattr(ou, 'email', None) != email_from_idp:
                        ou.email = email_from_idp; s.add(ou); s.commit()
                except Exception:
                    pass
            if ou and getattr(ou, 'disabled', False):
                if getattr(ou, 'ban_expires_at', None) and ou.ban_expires_at < datetime.now(timezone.utc):
                    ou.disabled=False; ou.ban_reason=None; ou.ban_expires_at=None; s.add(ou); s.commit()
                else:
                    return JSONResponse({"ok": False, "error": (ou.ban_reason or "User disabled")}, status_code=403)
    except Exception:
        pass
    app_token = sign_jwt(sub, provider)
    # Set cookie (works when callback and frontend are same-origin); we also pass token via URL fragment for cross-origin ports
    response.set_cookie("rr_token", app_token, httponly=False, samesite="lax", path="/")
    # Preferred frontend origin from state (JSON) or direct query param
    front = request.query_params.get('front')
    if not front:
        try:
            st = request.query_params.get('state')
            if st:
                obj = json.loads(st)
                if isinstance(obj, dict):
                    front = obj.get('front')
        except Exception:
            front = None
    # Normalize loopback host to 'localhost' to align cookie scope between 8000 and 8080
    def _normalize_origin(origin: str | None) -> str | None:
        try:
            if not origin: return None
            pu = urlparse(origin)
            host = pu.hostname or ''
            if host in ('127.0.0.1', '::1'):
                # rebuild with localhost
                netloc = 'localhost'
                if pu.port:
                    netloc += f":{pu.port}"
                return urlunparse((pu.scheme or 'http', netloc, '', '', '', ''))
            return origin
        except Exception:
            return origin
    front = _normalize_origin(front)
    frontend = front or (settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "http://localhost:8080")
    # Pass token via fragment so frontend can store to localStorage even if cookie domain differs
    url = f"{frontend}/callback.html#token={app_token}"
    return RedirectResponse(url)


# ---- Simple Captcha (SVG) ----
# Use stateless, signed token (JWT) to avoid multi-worker memory issues
_CAPTCHA_TTL = 5 * 60  # seconds

def _gen_code(n=5):
    # Remove ambiguous characters to reduce user misreads: 0/O, 1/I/L
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(random.choice(chars) for _ in range(n))

def _svg_captcha_text(txt: str):
    # minimal noisy SVG
    w, h = 120, 40
    # jitter positions
    xs = [15, 35, 55, 75, 95]
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">']
    svg.append('<rect width="100%" height="100%" fill="#f8fafc"/>')
    # random lines
    for _ in range(6):
        x1,y1,x2,y2 = random.randint(0,w), random.randint(0,h), random.randint(0,w), random.randint(0,h)
        color = random.choice(['#cbd5e1','#e2e8f0','#94a3b8'])
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1"/>')
    for i,ch in enumerate(txt[:5]):
        y = random.randint(24, 34)
        rot = random.randint(-18, 18)
        svg.append(f'<text x="{xs[i]}" y="{y}" fill="#0f172a" font-size="20" font-family="monospace" transform="rotate({rot} {xs[i]},{y})">{ch}</text>')
    svg.append('</svg>')
    return ''.join(svg)

def _new_captcha()->tuple[str,str]:
    # Stateless captcha: JWT contains only salt + digest (no plaintext code)
    code = _gen_code()
    salt = base64.urlsafe_b64encode(os.urandom(8)).decode().rstrip('=')
    now = int(time.time())
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f"{salt}:{code.strip().upper()}".encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    payload = {"salt": salt, "digest": digest, "iat": now, "exp": now + _CAPTCHA_TTL}
    cid = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    svg = _svg_captcha_text(code)
    data_url = 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return cid, data_url

def _verify_captcha(cid: str | None, code: str | None)->bool:
    if not cid or not code:
        return False
    try:
        data = jwt.decode(cid, settings.SECRET_KEY, algorithms=["HS256"])
        salt = data.get("salt") or ""
        expect = data.get("digest") or ""
        if not salt or not expect:
            return False
        inp = (code or '').strip().upper()
        got = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            f"{salt}:{inp}".encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expect, got)
    except Exception:
        return False

@router.get('/captcha')
def get_captcha():
    cid, data_url = _new_captcha()
    return {"ok": True, "id": cid, "image": data_url}
