from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
from sqlmodel import Session
from ..core.db import get_session
from ..core.deps import require_auth_or_trial, get_user_key
from ..services.agent_service import generate_review, generate_review_pro_agent_iter
from starlette.concurrency import run_in_threadpool
from ..core.config import settings
from ..models.models import ReviewSheet, FileMeta, Vip, MonthlyUsage
from datetime import date, datetime
from sqlmodel import select
from ..services.file_service import sniff_and_read
from typing import List


router = APIRouter()


class GenerateRequest(BaseModel):
    source_id: str | None = None
    source_ids: List[str] | None = None
    text: str | None = None
    format: str  # qa|flashcards|review_sheet_pro
    lang: str | None = None  # 'zh' | 'en'
    length: str | None = None  # 'short' | 'medium' | 'long'


@router.post("")
async def generate(payload: GenerateRequest, response: Response, _ctx=Depends(require_auth_or_trial), session: Session = Depends(get_session), user_key: str | None = Depends(get_user_key)):
    # Usage accounting: always count for authenticated users; only non-VIP enforce limit
    if user_key:
        vip = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
        is_vip = bool(vip and vip.is_vip and (vip.expires_at is None or vip.expires_at > datetime.utcnow()))
        now = datetime.utcnow()
        mu = session.exec(select(MonthlyUsage).where(MonthlyUsage.user_key == user_key, MonthlyUsage.year == now.year, MonthlyUsage.month == now.month)).first()
        if not mu:
            mu = MonthlyUsage(user_key=user_key, year=now.year, month=now.month, count=0)
            session.add(mu); session.commit(); session.refresh(mu)
        if not is_vip:
            limit = getattr(settings, 'FREE_MONTHLY_LIMIT', 5)
            if mu.count + 1 > limit:
                return {"ok": False, "error": f"Monthly limit reached for non-VIP users ({limit})."}
        mu.count += 1; mu.updated_at = datetime.utcnow(); session.add(mu); session.commit()
    fmt = payload.format.lower()
    # Enforce long-length restriction for non-VIP
    if (payload.length or 'short').lower() == 'long' and user_key:
        vip = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
        is_vip = bool(vip and vip.is_vip and (vip.expires_at is None or vip.expires_at > datetime.utcnow()))
        if not is_vip:
            return {"ok": False, "error": "Long length generation requires VIP."}
    text = (payload.text or "").strip()
    used_source_id: int | None = None
    used_names: List[str] = []
    owner_id = _ctx.get("user_id")
    # Gather texts from multiple files if provided
    texts: List[str] = []
    ids: List[int] = []
    if payload.source_ids and len(payload.source_ids) > 0:
        for sid in payload.source_ids:
            try:
                fid = int(sid)
                fm = session.get(FileMeta, fid)
                if fm and fm.stored_path and (owner_id is None or fm.user_id == owner_id):
                    with open(fm.stored_path, "rb") as f:
                        raw = f.read()
                    ex = sniff_and_read(fm.filename, raw) or (raw.decode(errors="ignore") if raw else "")
                    if ex:
                        texts.append(ex)
                        ids.append(fid)
                        used_names.append(fm.filename)
            except Exception:
                continue
        if texts:
            text = ("\n\n".join(texts) + ("\n\n" + text if text else "")).strip()
            used_source_id = ids[0] if ids else None
    elif (not text) and payload.source_id:
        try:
            fid = int(payload.source_id)
            fm = session.get(FileMeta, fid)
            if fm and fm.stored_path and (owner_id is None or fm.user_id == owner_id):
                try:
                    with open(fm.stored_path, "rb") as f:
                        raw = f.read()
                    text = sniff_and_read(fm.filename, raw) or (raw.decode(errors="ignore") if raw else "")
                    used_source_id = fm.id
                    if fm.filename:
                        used_names.append(fm.filename)
                except Exception:
                    pass
        except Exception:
            pass
    if not text:
        return {"ok": False, "error": "Empty text"}

    try:
        # Run blocking LLM work in a thread to avoid blocking the event loop
        result = await run_in_threadpool(generate_review, text, fmt, (payload.lang or 'zh'), (payload.length or 'short'))  # type: ignore[arg-type]
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Persist as plain text for easier downstream usage
    header = ("Sources: " + ", ".join(used_names) + "\n\n") if used_names else ""
    # If original text exceeded threshold, note that condensation likely occurred
    try:
        if len(text) > getattr(settings, "MAX_INPUT_CHARS", 16000):
            header += f"[Note] Condensed to ~{getattr(settings, 'CONDENSE_TARGET_CHARS', 6000)} chars before generation\n\n"
    except Exception:
        pass
    text_out = ""
    if fmt == "outline":
        text_out = header + "\n".join(f"- {it}" for it in result.get("items", []))
    elif fmt == "qa":
        text_out = header + "\n\n".join([f"Q: {p.get('q','')}\nA: {p.get('a','')}" for p in result.get("pairs", [])])
    elif fmt == "flashcards":
        text_out = header + "\n\n".join([f"Front: {c.get('front','')}\nBack: {c.get('back','')}" for c in result.get("cards", [])])
    elif fmt == "review_sheet_pro":
        text_out = header + (result.get("text") or "")
    else:
        text_out = header + json.dumps(result, ensure_ascii=False)

    rs = ReviewSheet(user_id=owner_id, source_id=used_source_id, kind=fmt, content=text_out)
    session.add(rs)
    session.commit()
    # If this was a trial (not logged-in), consume it by marking cookie as used
    try:
        if _ctx.get("trial") and _ctx.get("user_id") is None:
            response.set_cookie(key="rr_trial", value="used", max_age=60*60*24*180, httponly=False, samesite="lax", path="/")
    except Exception:
        pass
    return {"ok": True, "id": rs.id, "text": text_out, "review_sheet": result}


def _sse_event(name: str, data: str) -> bytes:
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


@router.post("/stream")
async def generate_stream(payload: GenerateRequest, _ctx=Depends(require_auth_or_trial), session: Session = Depends(get_session), user_key: str | None = Depends(get_user_key)):
    # stream only for review_sheet_pro
    if (payload.format or "").lower() != "review_sheet_pro":
        # Fallback to non-stream JSON
        async def _fallback():
            yield _sse_event("error", "Only review_sheet_pro supports streaming")
            yield _sse_event("done", "")
        return StreamingResponse(_fallback(), media_type="text/event-stream")
    # Enforce: streaming is intended for long mode
    if (payload.length or 'short').lower() != 'long':
        async def _fallback2():
            yield _sse_event("error", "Streaming supported only when length=long for review_sheet_pro")
            yield _sse_event("done", "")
        return StreamingResponse(_fallback2(), media_type="text/event-stream")

    # Restrict: non-VIP cannot use long length
    if user_key:
        vip = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
        is_vip = bool(vip and vip.is_vip and (vip.expires_at is None or vip.expires_at > datetime.utcnow()))
        if not is_vip:
            async def _vip_only():
                yield _sse_event("error", "Long length generation requires VIP.")
                yield _sse_event("done", "")
            return StreamingResponse(_vip_only(), media_type="text/event-stream")

    # Monthly usage accounting (streaming counts as 1): always count; only non-VIP enforce limit
    if user_key:
        vip = session.exec(select(Vip).where(Vip.user_key == user_key)).first()
        is_vip = bool(vip and vip.is_vip and (vip.expires_at is None or vip.expires_at > datetime.utcnow()))
        now = datetime.utcnow()
        mu = session.exec(select(MonthlyUsage).where(MonthlyUsage.user_key == user_key, MonthlyUsage.year == now.year, MonthlyUsage.month == now.month)).first()
        if not mu:
            mu = MonthlyUsage(user_key=user_key, year=now.year, month=now.month, count=0)
            session.add(mu); session.commit(); session.refresh(mu)
        if not is_vip:
            limit = getattr(settings, 'FREE_MONTHLY_LIMIT', 5)
            if mu.count + 1 > limit:
                async def _limit():
                    yield _sse_event("error", f"Monthly limit reached for non-VIP users ({limit}).")
                    yield _sse_event("done", "")
                return StreamingResponse(_limit(), media_type="text/event-stream")
        mu.count += 1; mu.updated_at = datetime.utcnow(); session.add(mu); session.commit()

    # Reuse file reading logic from non-stream endpoint: support source_ids/source_id/text
    text = (payload.text or "").strip()
    owner_id = _ctx.get("user_id")
    used_source_id = None
    try:
        from ..services.file_service import sniff_and_read
    except Exception:
        sniff_and_read = None  # type: ignore

    # Always merge files if provided, then append text if any (consistent with non-stream endpoint)
    if payload.source_ids:
        merged: list[str] = []
        first_id = None
        for sid in payload.source_ids:
            try:
                fid = int(sid)
                fm = session.get(FileMeta, fid)
                if fm and fm.stored_path and (owner_id is None or fm.user_id == owner_id):
                    with open(fm.stored_path, "rb") as f:
                        raw = f.read()
                    ex = sniff_and_read(fm.filename, raw) if sniff_and_read else None
                    tx = ex or (raw.decode(errors="ignore") if raw else "")
                    if tx:
                        merged.append(tx)
                        if first_id is None:
                            first_id = fm.id
            except Exception:
                continue
        if merged:
            combined = "\n\n".join(merged)
            text = (combined + ("\n\n" + text if text else "")).strip()
            used_source_id = first_id
    elif payload.source_id:
        try:
            fid = int(payload.source_id)
            fm = session.get(FileMeta, fid)
            if fm and fm.stored_path and (owner_id is None or fm.user_id == owner_id):
                with open(fm.stored_path, "rb") as f:
                    raw = f.read()
                ex = sniff_and_read(fm.filename, raw) if sniff_and_read else None
                tx = ex or (raw.decode(errors="ignore") if raw else "")
                if tx:
                    text = (tx + ("\n\n" + text if text else "")).strip()
                    used_source_id = fm.id
        except Exception:
            text = text or ""
    if not text:
        async def _empty():
            yield _sse_event("error", "Empty text")
            yield _sse_event("done", "")
        return StreamingResponse(_empty(), media_type="text/event-stream")

    lang = (payload.lang or 'zh')

    async def _gen():
        # Progress events
        try:
            buf_text = ""
            for ev in generate_review_pro_agent_iter(text, lang):
                name = ev.get("name")
                if name == "done":
                    buf_text = ev.get("text", "")
                    yield _sse_event("done", "ok")
                elif name == "assemble":
                    status = ev.get("status", "")
                    yield _sse_event("assemble", status)
                elif name == "condense":
                    yield _sse_event("condense", ev.get("status", ""))
                elif name == "chapters":
                    payload = {k: ev[k] for k in ("status","count") if k in ev}
                    import json as _json
                    yield _sse_event("chapters", _json.dumps(payload, ensure_ascii=False))
                elif name == "chapter":
                    import json as _json
                    yield _sse_event("chapter", _json.dumps({k: ev[k] for k in ("i","n","title") if k in ev}, ensure_ascii=False))
                elif name == "section":
                    import json as _json
                    yield _sse_event("section", _json.dumps({k: ev[k] for k in ("chapterIndex","sectionIndex","sectionTitle","chapterTitle") if k in ev}, ensure_ascii=False))
            # Persist after generation completes
            if buf_text:
                rs = ReviewSheet(user_id=owner_id, source_id=used_source_id, kind='review_sheet_pro', content=buf_text)
                session.add(rs)
                session.commit()
                import json as _json
                yield _sse_event("id", str(rs.id))
                yield _sse_event("text", _json.dumps({"text": buf_text}, ensure_ascii=False))
        except Exception as e:
            yield _sse_event("error", str(e))
            yield _sse_event("done", "")

    resp = StreamingResponse(_gen(), media_type="text/event-stream")
    # Mark trial as used at stream start for anonymous users
    try:
        if _ctx.get("trial") and _ctx.get("user_id") is None:
            resp.set_cookie(key="rr_trial", value="used", max_age=60*60*24*180, httponly=False, samesite="lax", path="/")
    except Exception:
        pass
    return resp
