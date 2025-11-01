from fastapi import APIRouter, UploadFile, File, Form, Depends
from pydantic import BaseModel
from ..services.file_service import sniff_and_read
from ..core.db import get_session
from sqlmodel import Session, select
from ..models.entities import FileMeta
from ..core.deps import require_auth_or_trial
import os
from pathlib import Path
import httpx
from urllib.parse import urlparse
import mimetypes
import socket, ipaddress


router = APIRouter()


class ManualInput(BaseModel):
    text: str


@router.post("")
@router.post("/")
async def upload_file(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    url: str | None = Form(default=None),
    ctx=Depends(require_auth_or_trial),
    session: Session = Depends(get_session),
):
    # Minimal stub to accept either a file or manual text
    meta = {}
    content = ""
    if file:
        raw = await file.read()
        extracted = sniff_and_read(file.filename, raw) or ""
        meta = {"filename": file.filename, "content_type": file.content_type}
        content = extracted or raw.decode(errors="ignore")
        # trial 用户：不持久化，自动清除（仅内存解析）
        if ctx.get("user_id") is None:
            fm = None
        else:
            # persist metadata and store raw file
            fm = FileMeta(filename=file.filename, content_type=file.content_type or None, size=len(raw), user_id=ctx.get("user_id"))
            session.add(fm)
            session.commit()
            # store to storage/uploads
            base_dir = Path(__file__).resolve().parents[2] / "storage" / "uploads"
            base_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{fm.id}_{file.filename}"
            path = base_dir / safe_name
            with open(path, "wb") as f:
                f.write(raw)
            fm.stored_path = str(path)
            session.add(fm)
            session.commit()
    elif url:
        # Basic SSRF guard and size-limited download
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return {"ok": False, "error": "Only http/https URLs are allowed"}
            host = parsed.hostname or ""
            # resolve and block private/local addresses
            try:
                infos = socket.getaddrinfo(host, None)
                for _, _, _, _, sockaddr in infos:
                    ip = sockaddr[0]
                    ip_obj = ipaddress.ip_address(ip)
                    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
                        return {"ok": False, "error": "Target host not allowed"}
            except Exception:
                # if DNS fails, reject
                return {"ok": False, "error": "Cannot resolve host"}
            MAX_BYTES = int(os.getenv("MAX_FETCH_BYTES", "10485760"))  # 10MB default
            timeout = httpx.Timeout(15.0, read=15.0, connect=10.0)
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return {"ok": False, "error": f"Fetch failed: {resp.status_code}"}
                cl = resp.headers.get("content-length")
                if cl:
                    try:
                        if int(cl) > MAX_BYTES:
                            return {"ok": False, "error": "File too large"}
                    except Exception:
                        pass
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    if len(buf) + len(chunk) > MAX_BYTES:
                        return {"ok": False, "error": "File too large"}
                    buf.extend(chunk)
                raw = bytes(buf)
                # filename from header or URL
                fname = None
                cd = resp.headers.get("content-disposition") or ""
                if "filename=" in cd:
                    # naive parse
                    try:
                        part = cd.split("filename=")[-1].strip().strip('"')
                        if part:
                            fname = part
                    except Exception:
                        pass
                if not fname:
                    fname = os.path.basename(parsed.path) or "download"
                ctype = resp.headers.get("content-type") or None
                # guess extension if missing
                if "." not in fname and ctype:
                    ext = mimetypes.guess_extension(ctype.split(";")[0].strip())
                    if ext:
                        fname = fname + ext
                extracted = sniff_and_read(fname, raw) or ""
                meta = {"filename": fname, "content_type": ctype}
                content = extracted or raw.decode(errors="ignore")
                if ctx.get("user_id") is None:
                    fm = None
                else:
                    fm = FileMeta(filename=fname, content_type=ctype or None, size=len(raw), user_id=ctx.get("user_id"))
                    session.add(fm)
                    session.commit()
                    base_dir = Path(__file__).resolve().parents[2] / "storage" / "uploads"
                    base_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = f"{fm.id}_{fname}"
                    path = base_dir / safe_name
                    with open(path, "wb") as f:
                        f.write(raw)
                    fm.stored_path = str(path)
                    session.add(fm)
                    session.commit()
        except Exception:
            return {"ok": False, "error": "Fetch error"}
    elif text:
        content = text
    else:
        return {"ok": False, "error": "No file or text provided"}

    # return file_id for referencing later (drag-to-generate etc.)
    resp = {"ok": True, "meta": meta, "chars": len(content), "content": content}
    try:
        if 'fm' in locals() and fm and fm.id:
            resp["file_id"] = fm.id
    except Exception:
        pass
    return resp


@router.get("/list")
def list_files(session: Session = Depends(get_session), _ctx=Depends(require_auth_or_trial)):
    # 未登录：不返回任何文件（试用上传不落盘）
    if _ctx.get("user_id") is None:
        return {"ok": True, "items": []}
    stmt = select(FileMeta).where(FileMeta.user_id == _ctx.get("user_id")).order_by(FileMeta.created_at.desc()).limit(20)
    rows = session.exec(stmt).all()
    items = [
        {
            "id": r.id,
            "filename": r.filename,
            "content_type": r.content_type,
            "size": r.size,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return {"ok": True, "items": items}


@router.delete("/all")
def clear_all_files(session: Session = Depends(get_session), _ctx=Depends(require_auth_or_trial)):
    """Delete all uploaded files for current user (metadata + stored files)."""
    user_id = _ctx.get("user_id")
    if user_id is None:
        # Trial/anonymous: nothing persisted
        return {"ok": True, "count": 0}
    stmt = select(FileMeta).where(FileMeta.user_id == user_id)
    rows = session.exec(stmt).all()
    count = 0
    for r in rows:
        try:
            if r.stored_path and os.path.exists(r.stored_path):
                try:
                    os.remove(r.stored_path)
                except Exception:
                    pass
            session.delete(r)
            count += 1
        except Exception:
            # continue best-effort
            continue
    session.commit()
    return {"ok": True, "count": count}
