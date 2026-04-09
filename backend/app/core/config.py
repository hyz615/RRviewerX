import os
from typing import List
from pathlib import Path
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # optional


class Settings:
    APP_ENV: str
    SECRET_KEY: str
    ALLOWED_ORIGINS: List[str]
    ALLOWED_ORIGIN_REGEX: str | None

    OPENAI_API_KEY: str | None
    DEEPSEEK_API_KEY: str | None
    LLM_PROVIDER: str
    LLM_MODEL: str
    LLM_BASE_URL: str | None
    LLM_API_CONFIGS: str | None
    VLM_PROVIDER: str | None
    VLM_MODEL: str | None
    VLM_BASE_URL: str | None
    VLM_API_KEY: str | None
    VLM_API_CONFIGS: str | None

    GOOGLE_CLIENT_ID: str | None
    GOOGLE_CLIENT_SECRET: str | None
    MICROSOFT_CLIENT_ID: str | None
    MICROSOFT_CLIENT_SECRET: str | None

    DATABASE_URL: str
    RETENTION_DAYS: int
    CLEAN_INTERVAL_HOURS: int
    MAX_INPUT_CHARS: int
    CONDENSE_TARGET_CHARS: int
    STRIPE_SECRET_KEY: str | None
    STRIPE_WEBHOOK_SECRET: str | None
    STRIPE_PRICE_30: str | None
    STRIPE_PRICE_90: str | None
    STRIPE_PRICE_365: str | None
    EMBEDDING_MODEL: str
    EMBEDDING_DIM: int
    FREE_MONTHLY_LIMIT: int
    # Email / Resend
    RESEND_API_KEY: str | None
    EMAIL_FROM: str | None
    FRONTEND_BASE: str | None
    OAUTH_REDIRECT_BASE: str | None
    VLM_MAX_IMAGES: int
    VLM_PDF_PAGE_LIMIT: int
    VLM_SUMMARY_MAX_CHARS: int

    def __init__(self) -> None:
        # Load backend/.env first (if python-dotenv available), then default .env
        if load_dotenv:
            backend_dir = Path(__file__).resolve().parents[2]
            env_path = backend_dir / ".env"
            if env_path.exists():
                load_dotenv(env_path)  # load explicit backend/.env
            else:
                # fallback: load default .env via search
                load_dotenv()
        self.APP_ENV = os.getenv("APP_ENV", "dev")
        self.SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
        origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
        # Normalize: trim spaces and trailing slashes to avoid mismatch with browser Origin
        self.ALLOWED_ORIGINS = [o.strip().rstrip('/') for o in origins.split(",") if o.strip()]
        # Optional regex for wildcard domains, e.g. ^https?://(.*\.)?example\.com$
        self.ALLOWED_ORIGIN_REGEX = os.getenv("ALLOWED_ORIGIN_REGEX")

        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
        self.LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL")
        self.LLM_API_CONFIGS = os.getenv("LLM_API_CONFIGS")
        self.VLM_PROVIDER = os.getenv("VLM_PROVIDER")
        self.VLM_MODEL = os.getenv("VLM_MODEL")
        self.VLM_BASE_URL = os.getenv("VLM_BASE_URL")
        self.VLM_API_KEY = os.getenv("VLM_API_KEY")
        self.VLM_API_CONFIGS = os.getenv("VLM_API_CONFIGS")

        self.GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        self.GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
        self.MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
        self.MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")

        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./rrviewer.db")
        self.RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
        self.CLEAN_INTERVAL_HOURS = int(os.getenv("CLEAN_INTERVAL_HOURS", "6"))
        self.MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "16000"))
        self.CONDENSE_TARGET_CHARS = int(os.getenv("CONDENSE_TARGET_CHARS", "6000"))
        # Stripe
        self.STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
        self.STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.STRIPE_PRICE_30 = os.getenv("STRIPE_PRICE_30")
        self.STRIPE_PRICE_90 = os.getenv("STRIPE_PRICE_90")
        self.STRIPE_PRICE_365 = os.getenv("STRIPE_PRICE_365")
        # Embeddings
        self.EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        try:
            self.EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
        except Exception:
            self.EMBEDDING_DIM = 1536
        # Free monthly limit for non-VIP users
        try:
            self.FREE_MONTHLY_LIMIT = int(os.getenv("FREE_MONTHLY_LIMIT", "5"))
        except Exception:
            self.FREE_MONTHLY_LIMIT = 5
        # Email / Resend
        self.RESEND_API_KEY = os.getenv("RESEND_API_KEY")
        self.EMAIL_FROM = os.getenv("EMAIL_FROM")
        self.FRONTEND_BASE = os.getenv("FRONTEND_BASE")
        # Explicit base URL for OAuth redirect URIs (e.g. https://myapp.com)
        # When behind a reverse proxy, request.url_for() may produce wrong scheme/host.
        self.OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE")
        try:
            self.VLM_MAX_IMAGES = int(os.getenv("VLM_MAX_IMAGES", "6"))
        except Exception:
            self.VLM_MAX_IMAGES = 6
        try:
            self.VLM_PDF_PAGE_LIMIT = int(os.getenv("VLM_PDF_PAGE_LIMIT", "4"))
        except Exception:
            self.VLM_PDF_PAGE_LIMIT = 4
        try:
            self.VLM_SUMMARY_MAX_CHARS = int(os.getenv("VLM_SUMMARY_MAX_CHARS", "3000"))
        except Exception:
            self.VLM_SUMMARY_MAX_CHARS = 3000


settings = Settings()
