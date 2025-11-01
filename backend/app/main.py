from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from .core.config import settings
from .core.db import init_db
from .routes import auth, upload, generate, chat, embed
from .routes import status, admin, vip, history, support, test
from .core.db import get_session, engine
from sqlmodel import Session, select
from .models.entities import FileMeta, ReviewSheet
from datetime import datetime, timedelta
import threading, time, os

app = FastAPI(title="RRviewer API", version="0.1.0")

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
    # Redirect to frontend workspace page by default
    base = settings.FRONTEND_BASE or (settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "http://localhost:8080")
    return RedirectResponse(url=f"{base}/workspace.html")


@app.on_event("startup")
def _startup():
    init_db()
    # start cleanup background thread
    def cleaner():
        interval = max(1, settings.CLEAN_INTERVAL_HOURS) * 3600
        retention = max(1, settings.RETENTION_DAYS)
        while True:
            try:
                with Session(engine) as session:
                    cutoff = datetime.utcnow() - timedelta(days=retention)
                    # find files older than cutoff and not referenced
                    old_files = session.exec(select(FileMeta).where(FileMeta.created_at < cutoff)).all()
                    for fm in old_files:
                        used = session.exec(select(ReviewSheet).where(ReviewSheet.source_id == fm.id)).first()
                        if used:
                            continue
                        # delete file on disk
                        if fm.stored_path and os.path.exists(fm.stored_path):
                            try:
                                os.remove(fm.stored_path)
                            except Exception:
                                pass
                        session.delete(fm)
                    session.commit()
            except Exception:
                pass
            time.sleep(interval)
    threading.Thread(target=cleaner, daemon=True).start()
