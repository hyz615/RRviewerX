from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from sqlmodel import Session
from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.models import ReviewSheet
from ..services.agent_service import answer_questions
from ..services.course_service import load_json_list
from starlette.concurrency import run_in_threadpool
from ..services.embedding_service import embed_texts
import json


router = APIRouter()


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    review_sheet_id: str | None = None
    question: str | None = None
    questions: List[str] | None = None
    stream: bool | None = False
    history: List[ChatHistoryMessage] | None = None


def _load_review_sheet(review_sheet_id: str | None, session: Session, uid: int | None) -> ReviewSheet | None:
    if not review_sheet_id or uid is None:
        return None
    try:
        rid = int(review_sheet_id)
    except Exception:
        return None
    rs = session.get(ReviewSheet, rid)
    if rs and rs.user_id == uid:
        return rs
    return None


def _extract_review_text(raw_content: str | None, limit: int = 4000) -> str:
    raw = str(raw_content or "").strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        return raw[:limit]

    if isinstance(data, dict):
        for key in ("text", "content", "review", "review_text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:limit]
        items = data.get("items")
        if isinstance(items, list):
            lines = [str(item).strip() for item in items if str(item).strip()]
            if lines:
                return "\n".join(lines)[:limit]
    if isinstance(data, list):
        lines: List[str] = []
        for item in data:
            if isinstance(item, dict):
                text_value = item.get("text") or item.get("content")
                if isinstance(text_value, str) and text_value.strip():
                    lines.append(text_value.strip())
                    continue
            rendered = str(item).strip()
            if rendered:
                lines.append(rendered)
        if lines:
            return "\n".join(lines)[:limit]
    if isinstance(data, str):
        return data[:limit]
    return raw[:limit]


def _build_study_context(review_sheet: ReviewSheet | None) -> str:
    if review_sheet is None:
        return ""

    lines: List[str] = []
    if review_sheet is not None:
        if review_sheet.subject_code:
            lines.append(f"科目: {review_sheet.subject_code}")
        if review_sheet.course_name:
            lines.append(f"课程: {review_sheet.course_name}")
        if review_sheet.exam_type:
            lines.append(f"考试类型: {review_sheet.exam_type}")
        if review_sheet.exam_name:
            lines.append(f"考试: {review_sheet.exam_name}")
        chapter_labels = [
            str(label).strip()
            for label in load_json_list(review_sheet.selected_chapter_labels)
            if str(label).strip()
        ]
        if chapter_labels:
            preview = "，".join(chapter_labels[:6])
            if len(chapter_labels) > 6:
                preview += f" 等 {len(chapter_labels)} 个章节"
            lines.append(f"章节范围: {preview}")

    return "\n".join(lines).strip()


def _normalize_history(history: List[ChatHistoryMessage] | None, limit: int = 8) -> List[dict[str, str]]:
    normalized: List[dict[str, str]] = []
    for item in history or []:
        role = str(item.role or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.content or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content[:2000]})
    return normalized[-limit:]


@router.post("")
async def chat(payload: ChatRequest, session: Session = Depends(get_session), uid: int | None = Depends(get_current_user)):
    if uid is None:
        raise HTTPException(status_code=401, detail="Login required")
    review_sheet = _load_review_sheet(payload.review_sheet_id, session, uid)
    review_text = _extract_review_text(review_sheet.content if review_sheet else "")
    study_context = _build_study_context(review_sheet)
    history = _normalize_history(payload.history)

    if payload.questions and len(payload.questions) > 0:
        answers = await run_in_threadpool(
            answer_questions,
            review_text,
            payload.questions,
            "zh",
            history,
            study_context,
        )
        return {"ok": True, "text": "\n\n".join(answers)}

    if payload.question and payload.question.strip():
        single = await run_in_threadpool(
            answer_questions,
            review_text,
            [payload.question.strip()],
            "zh",
            history,
            study_context,
        )
        return {"ok": True, "text": (single[0] if single else "")}

    return {"ok": False, "error": "No question(s) provided"}


@router.post("/stream")
async def chat_stream(payload: ChatRequest, session: Session = Depends(get_session), uid: int | None = Depends(get_current_user)):
    """Server-Sent Events streaming single question with reference segments.
    Fallback to mock if no real llm client."""
    if uid is None:
        raise HTTPException(status_code=401, detail="Login required")
    if not payload.question:
        return Response(content="missing question", status_code=400)
    review_sheet = _load_review_sheet(payload.review_sheet_id, session, uid)
    review_text = _extract_review_text(review_sheet.content if review_sheet else "", limit=12000)
    study_context = _build_study_context(review_sheet)
    history = _normalize_history(payload.history)

    chunks: List[str] = []
    buf: List[str] = []
    for line in review_text.splitlines():
        if not line.strip():
            if buf:
                chunks.append("\n".join(buf).strip())
                buf = []
            continue
        buf.append(line)
        if sum(len(x) for x in buf) > 400:
            chunks.append("\n".join(buf).strip())
            buf = []
    if buf:
        chunks.append("\n".join(buf).strip())
    chunks = [c for c in chunks if c][:50]
    refs = []
    try:
        q_emb = embed_texts([payload.question])[0]
        c_embs = embed_texts(chunks)
        # cosine similarity (vectors already normalized in mock; assume provider returns raw -> normalize)
        import math
        def norm(v):
            n = math.sqrt(sum(x*x for x in v)) or 1.0
            return [x/n for x in v]
        qn = norm(q_emb)
        sims: List[tuple[float,int]] = []
        for idx, ce in enumerate(c_embs):
            ce_n = norm(ce)
            sims.append((sum(a*b for a,b in zip(qn, ce_n)), idx))
        sims.sort(reverse=True)
        for score, idx in sims[:3]:
            refs.append({"score": round(score,4), "text": chunks[idx][:500]})
    except Exception:
        # simple fallback: first 3 non-empty chunks containing any keyword
        kws = [w for w in payload.question.split() if len(w) > 1][:5]
        for c in chunks:
            if len(refs) >= 3: break
            if any(k.lower() in c.lower() for k in kws):
                refs.append({"score": 0.0, "text": c[:500]})
        if not refs:
            refs = [{"score":0.0, "text": c[:500]} for c in chunks[:3]]

    async def event_gen():
        # send refs event first
        yield f"event: refs\ndata: {json.dumps(refs, ensure_ascii=False)}\n\n"
        question = payload.question.strip()
        answer_full = (await run_in_threadpool(
            answer_questions,
            review_text[:4000],
            [question],
            "zh",
            history,
            study_context,
        ))[0]
        if not answer_full:
            answer_full = "(no answer)"
        chunk_size = 50
        for i in range(0, len(answer_full), chunk_size):
            part = answer_full[i:i+chunk_size]
            yield f"event: chunk\ndata: {json.dumps(part, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
