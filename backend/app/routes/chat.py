from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from sqlmodel import Session
from ..core.db import get_session
from ..core.deps import get_current_user
from ..models.models import ReviewSheet
from ..services.agent_service import answer_questions
from starlette.concurrency import run_in_threadpool
from ..services.embedding_service import embed_texts
import json


router = APIRouter()


class ChatRequest(BaseModel):
    review_sheet_id: str | None = None
    question: str | None = None
    questions: List[str] | None = None
    stream: bool | None = False


@router.post("")
async def chat(payload: ChatRequest, session: Session = Depends(get_session), uid: int | None = Depends(get_current_user)):
    if uid is None:
        raise HTTPException(status_code=401, detail="Login required")
    # Load context if review_sheet_id provided
    def load_context(limit: int = 4000) -> str:
        if payload.review_sheet_id:
            rs = session.get(ReviewSheet, int(payload.review_sheet_id))
            if rs and rs.content and rs.user_id == uid:
                try:
                    data = json.loads(rs.content)
                    return json.dumps(data, ensure_ascii=False)[:limit]
                except Exception:
                    return rs.content[:limit]
        return ""

    if payload.questions and len(payload.questions) > 0:
        # no usage enforcement for chat
        context = load_context()
        answers = await run_in_threadpool(answer_questions, context, payload.questions)
        return {"ok": True, "text": "\n\n".join(answers)}

    if payload.question and payload.question.strip():
        # no usage enforcement for chat
        context = load_context()
        single = await run_in_threadpool(answer_questions, context, [payload.question.strip()])
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
    # load review context
    context_text = ""
    if payload.review_sheet_id:
        rs = session.get(ReviewSheet, int(payload.review_sheet_id))
        if rs and rs.content and rs.user_id == uid:
            try:
                data = json.loads(rs.content)
                context_text = json.dumps(data, ensure_ascii=False)
            except Exception:
                context_text = rs.content
    # slice context into chunks for embeddings
    chunks: List[str] = []
    buf: List[str] = []
    for line in context_text.splitlines():
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
        # streaming answer (mock: send in 40-char chunks)
        question = payload.question.strip()
        system_msg = "你是严谨、简洁的学习助教。基于引用片段回答。"
        # call llm.chat once (no true token stream available with current wrapper)
        answer_full = (await run_in_threadpool(answer_questions, context_text[:4000], [question]))[0]
        if not answer_full:
            answer_full = "(no answer)"
        chunk_size = 50
        for i in range(0, len(answer_full), chunk_size):
            part = answer_full[i:i+chunk_size]
            yield f"event: chunk\ndata: {json.dumps(part, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
