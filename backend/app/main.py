import logging
import threading
import time
import os
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import Session, select

from .core.config import settings
from .core.db import init_db, get_session, engine
from .routes import auth, upload, generate, chat, embed
from .routes import status, admin, vip, history, support, test
from .models.entities import FileMeta, ReviewSheet

# ── Structured Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rrviewer")


# ── Lifespan (replaces deprecated @app.on_event) ──────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RRviewer API …")
    init_db()
    logger.info("Database initialized")
    # Background cleaner thread
    stop_event = threading.Event()

    def cleaner():
        interval = max(1, settings.CLEAN_INTERVAL_HOURS) * 3600
        retention = max(1, settings.RETENTION_DAYS)
        while not stop_event.is_set():
            try:
                with Session(engine) as session:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
                    old_files = session.exec(select(FileMeta).where(FileMeta.created_at < cutoff)).all()
                    removed = 0
                    for fm in old_files:
                        used = session.exec(select(ReviewSheet).where(ReviewSheet.source_id == fm.id)).first()
                        if used:
                            continue
                        if fm.stored_path and os.path.exists(fm.stored_path):
                            try:
                                os.remove(fm.stored_path)
                            except Exception:
                                logger.warning("Failed to remove file: %s", fm.stored_path)
                        session.delete(fm)
                        removed += 1
                    session.commit()
                    if removed:
                        logger.info("Cleanup: removed %d orphaned file(s)", removed)
            except Exception:
                logger.exception("Cleanup cycle failed")
            stop_event.wait(interval)

    t = threading.Thread(target=cleaner, daemon=True)
    t.start()
    logger.info("Background cleanup thread started (interval=%dh, retention=%dd)",
                settings.CLEAN_INTERVAL_HOURS, settings.RETENTION_DAYS)
    yield
    stop_event.set()
    logger.info("Shutting down RRviewer API")


app = FastAPI(title="RRviewer API", version="0.2.0", lifespan=lifespan)

# ── Rate limiter ──────────────────────────────────────────────────
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_origin_regex=(settings.ALLOWED_ORIGIN_REGEX or None),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session cookie for OAuth (Authlib)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(generate.router, prefix="/generate", tags=["generate"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(embed.router, prefix="/embed", tags=["embed"])
app.include_router(status.router, prefix="/status", tags=["status"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(vip.router, prefix="/vip", tags=["vip"])
app.include_router(history.router, prefix="/history", tags=["history"])
app.include_router(support.router, prefix="/support", tags=["support"])
app.include_router(test.router, prefix="/test", tags=["test"])

@app.get("/")
def root():
    base = settings.FRONTEND_BASE or (settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "http://localhost:8080")
    return RedirectResponse(url=f"{base}/workspace.html")


# ── Health check (for Docker / k8s / monitoring) ──────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


# ── Request logging middleware ────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    if not request.url.path.startswith("/health"):
        logger.info("%s %s → %d (%.0fms)",
                     request.method, request.url.path,
                     response.status_code, duration_ms)
    return response
