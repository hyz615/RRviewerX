import time
import jwt
from .config import settings


def sign_jwt(sub: str, provider: str, exp_seconds: int = 60 * 60 * 24 * 7) -> str:
    now = int(time.time())
    payload = {"sub": sub, "provider": provider, "iat": now, "exp": now + exp_seconds}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def verify_jwt(token: str):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
