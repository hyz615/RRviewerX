from typing import Optional
from ..core.config import settings


class AuthService:
    def __init__(self) -> None:
        self.secret = settings.SECRET_KEY

    def verify_or_trial(self, token: Optional[str], trial_used: bool) -> bool:
        # Placeholder logic: allow if token present or trial not used
        return bool(token) or not trial_used


auth_service = AuthService()
