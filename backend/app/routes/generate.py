import asyncio
import re
import threading
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
from sqlmodel import Session
from ..core.db import get_session
from ..core.deps import get_user_key, require_auth_or_trial
from ..services.agent_service import generate_review, generate_review_pro_agent_iter
from ..services.course_service import (
    dump_json_list,
    get_course_textbook,
    list_course_textbook_chapters,
    resolve_course,
    resolve_files_for_chapters,
)
from ..services.generation_stats_service import record_review_generation
from starlette.concurrency import run_in_threadpool
from ..core.config import settings
from ..models.models import ReviewSheet, FileMeta
from ..services.file_service import sniff_and_read
from typing import List


router = APIRouter()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_subject_code(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    return cleaned.lower() if cleaned else None


def _normalize_exam_type(value: str | None) -> str | None:
    cleaned = _clean_optional_text(value)
    return cleaned.lower() if cleaned else None


def _normalize_chapter_ids(values: List[str] | None) -> list[int]:
    seen_ids: set[int] = set()
    normalized: list[int] = []
    for value in values or []:
        try:
            chapter_id = int(value)
        except Exception:
            continue
        if chapter_id in seen_ids:
            continue
        seen_ids.add(chapter_id)
        normalized.append(chapter_id)
    return normalized


def _normalize_generation_mode(value: str | None) -> str:
    cleaned = _clean_optional_text(value)
    if cleaned in {"materials", "textbook", "combined"}:
        return cleaned
    return "materials"


def _read_file_text(file_meta: FileMeta) -> str:
    if not file_meta.stored_path:
        return ""
    try:
        with open(file_meta.stored_path, "rb") as handle:
            raw = handle.read()
        return sniff_and_read(file_meta.filename, raw) or (raw.decode(errors="ignore") if raw else "")
    except Exception:
        return ""


def _collect_generation_sources(
    payload: "GenerateRequest",
    session: Session,
    owner_id: int | None,
) -> dict[str, object]:
    text = (payload.text or "").strip()
    used_names: List[str] = []
    used_source_id: int | None = None
    first_meta: FileMeta | None = None
    selected_chapter_ids = _normalize_chapter_ids(payload.chapter_ids)
    selected_chapter_labels: list[str] = []
    generation_mode = _normalize_generation_mode(payload.generation_mode)
    include_materials = generation_mode in {"materials", "combined"}
    include_textbook = generation_mode in {"textbook", "combined"}
    candidate_ids: list[int] = []
    seen_candidate_ids: set[int] = set()

    def add_candidate(raw_id: str | int | None) -> None:
        if raw_id is None:
            return
        try:
            file_id = int(raw_id)
        except Exception:
            return
        if file_id in seen_candidate_ids:
            return
        seen_candidate_ids.add(file_id)
        candidate_ids.append(file_id)

    material_texts: List[str] = []
    material_ids: List[int] = []
    if include_materials:
        for source_id in payload.source_ids or []:
            add_candidate(source_id)
        add_candidate(payload.source_id)

        if selected_chapter_ids and owner_id is not None:
            chapter_file_ids, selected_chapter_ids, selected_chapter_labels = resolve_files_for_chapters(
                session,
                owner_id,
                selected_chapter_ids,
            )
            for file_id in chapter_file_ids:
                add_candidate(file_id)

        for file_id in candidate_ids:
            file_meta = session.get(FileMeta, file_id)
            if file_meta is None or not file_meta.stored_path or file_meta.source_role == "textbook":
                continue
            if owner_id is not None and file_meta.user_id != owner_id:
                continue
            extracted = _read_file_text(file_meta)
            if not extracted:
                continue
            if first_meta is None:
                first_meta = file_meta
            material_texts.append(extracted)
            material_ids.append(file_id)
            used_names.append(file_meta.filename)

        if material_ids:
            used_source_id = material_ids[0]

    effective_subject_code = _normalize_subject_code(payload.subject_code)
    effective_course_name = _clean_optional_text(payload.course_name)
    if first_meta is not None:
        if not effective_subject_code:
            effective_subject_code = first_meta.subject_code
        if not effective_course_name:
            effective_course_name = first_meta.course_name

    textbook_file_id: int | None = None
    textbook_missing_selected = False
    used_textbook = False
    textbook_texts: List[str] = []
    if include_textbook and owner_id is not None and effective_course_name:
        course = resolve_course(
            session,
            owner_id,
            effective_subject_code,
            effective_course_name,
            create_if_missing=False,
        )
        textbook_meta = get_course_textbook(session, course)
        if textbook_meta is not None and textbook_meta.id is not None:
            textbook_file_id = textbook_meta.id
            if selected_chapter_ids:
                textbook_chapters = list_course_textbook_chapters(session, textbook_meta.id, selected_chapter_ids)
                textbook_texts = [item.get("content") for item in textbook_chapters if str(item.get("content") or "").strip()]
                textbook_missing_selected = not bool(textbook_texts)
                if textbook_chapters and not selected_chapter_labels:
                    selected_chapter_labels = [
                        str(item.get("label") or "").strip()
                        for item in textbook_chapters
                        if str(item.get("label") or "").strip()
                    ]
            else:
                full_text = _read_file_text(textbook_meta)
                if full_text:
                    textbook_texts = [full_text]
            if textbook_texts:
                used_textbook = True
                if first_meta is None:
                    first_meta = textbook_meta
                if used_source_id is None:
                    used_source_id = textbook_meta.id
                used_names = [f"Textbook: {textbook_meta.filename}"] + used_names

    combined_parts: List[str] = []
    if textbook_texts:
        combined_parts.extend(textbook_texts)
    if material_texts:
        combined_parts.extend(material_texts)
    if text:
        combined_parts.append(text)
    text = "\n\n".join(part for part in combined_parts if part).strip()

    return {
        "text": text,
        "used_source_id": used_source_id,
        "used_names": used_names,
        "first_meta": first_meta,
        "selected_chapter_ids": selected_chapter_ids,
        "selected_chapter_labels": selected_chapter_labels,
        "generation_mode": generation_mode,
        "textbook_file_id": textbook_file_id,
        "textbook_missing_selected": textbook_missing_selected,
        "used_textbook": used_textbook,
    }


def _build_generation_context(
    text: str,
    lang: str,
    subject_code: str | None,
    course_name: str | None,
    exam_type: str | None,
    exam_name: str | None,
    chapter_labels: list[str] | None = None,
) -> str:
    lines: list[str] = []
    is_en = (lang or "").lower().startswith("en")
    if subject_code:
        lines.append(("Subject" if is_en else "科目") + f": {subject_code}")
    if course_name:
        lines.append(("Course" if is_en else "课程") + f": {course_name}")
    if exam_type:
        lines.append(("Exam Type" if is_en else "考试类型") + f": {exam_type}")
    if exam_name:
        lines.append(("Exam" if is_en else "考试") + f": {exam_name}")
    if chapter_labels:
        preview = ", ".join(chapter_labels[:8])
        if len(chapter_labels) > 8:
            preview += f" (+{len(chapter_labels) - 8})"
        lines.append(("Chapters" if is_en else "章节范围") + f": {preview}")

    if not lines:
        return text

    prefix = "Context" if is_en else "上下文"
    return prefix + ":\n- " + "\n- ".join(lines) + "\n\n" + text


_MIN_CONTENT_CHARS = 50


def _check_content_sufficiency(text: str, lang: str = "zh") -> str | None:
    """Return an error message if the text is insufficient for generation, else None."""
    stripped = text.strip()
    # Remove pure whitespace / punctuation / digits to measure real content
    meaningful = re.sub(r'[\s\d\W]+', '', stripped)
    if len(meaningful) < _MIN_CONTENT_CHARS:
        if (lang or "").lower().startswith("en"):
            return (
                "Insufficient content for generation. "
                "Please provide more study material (notes, textbook chapters, etc.) before generating."
            )
        return "内容不足以生成复习资料，请先上传或选择更多学习材料（笔记、教材章节等）后再尝试生成。"
    return None


class GenerateRequest(BaseModel):
    source_id: str | None = None
    source_ids: List[str] | None = None
    text: str | None = None
    format: str  # qa|flashcards|review_sheet_pro
    lang: str | None = None  # 'zh' | 'en'
    length: str | None = None  # 'short' | 'medium' | 'long'
    subject_code: str | None = None
    course_name: str | None = None
    exam_type: str | None = None
    exam_name: str | None = None
    chapter_ids: List[str] | None = None
    generation_mode: str | None = None


@router.post("")
async def generate(
    payload: GenerateRequest,
    _ctx=Depends(require_auth_or_trial),
    user_key: str | None = Depends(get_user_key),
    session: Session = Depends(get_session),
):
    fmt = payload.format.lower()
    owner_id = _ctx.get("user_id")
    subject_code = _normalize_subject_code(payload.subject_code)
    course_name = _clean_optional_text(payload.course_name)
    exam_type = _normalize_exam_type(payload.exam_type)
    exam_name = _clean_optional_text(payload.exam_name)
    source_bundle = _collect_generation_sources(payload, session, owner_id)
    text = str(source_bundle["text"])
    used_source_id = source_bundle["used_source_id"]
    used_names = list(source_bundle["used_names"])
    first_meta = source_bundle["first_meta"]
    selected_chapter_ids = list(source_bundle["selected_chapter_ids"])
    selected_chapter_labels = list(source_bundle["selected_chapter_labels"])
    generation_mode = str(source_bundle["generation_mode"])
    textbook_file_id = source_bundle["textbook_file_id"]
    textbook_missing_selected = bool(source_bundle["textbook_missing_selected"])
    used_textbook = bool(source_bundle["used_textbook"])
    if generation_mode in {"textbook", "combined"} and not textbook_file_id:
        return {"ok": False, "error": "Course textbook not found"}
    if generation_mode in {"textbook", "combined"} and selected_chapter_ids and textbook_missing_selected:
        return {"ok": False, "error": "Selected chapters are not available in the course textbook"}
    if not text:
        return {"ok": False, "error": "Empty text"}
    insufficiency_error = _check_content_sufficiency(text, payload.lang or "zh")
    if insufficiency_error:
        return {"ok": False, "error": insufficiency_error}

    if first_meta is not None:
        if not subject_code:
            subject_code = first_meta.subject_code
        if not course_name:
            course_name = first_meta.course_name

    model_input = _build_generation_context(
        text,
        payload.lang or "zh",
        subject_code,
        course_name,
        exam_type,
        exam_name,
        selected_chapter_labels,
    )

    try:
        # Run blocking LLM work in a thread to avoid blocking the event loop
        result = await run_in_threadpool(generate_review, model_input, fmt, (payload.lang or 'zh'), (payload.length or 'short'))  # type: ignore[arg-type]
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Persist as plain text for easier downstream usage
    header = ("Sources: " + ", ".join(used_names) + "\n\n") if used_names else ""
    # If original text exceeded threshold, note that condensation likely occurred
    try:
        if len(model_input) > getattr(settings, "MAX_INPUT_CHARS", 16000):
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

    record_review_generation(session, user_key)

    review_id = None
    if owner_id is not None:
        rs = ReviewSheet(
            user_id=owner_id,
            source_id=used_source_id,
            kind=fmt,
            content=text_out,
            subject_code=subject_code,
            course_name=course_name,
            exam_type=exam_type,
            exam_name=exam_name,
            selected_chapter_ids=dump_json_list(selected_chapter_ids),
            selected_chapter_labels=dump_json_list(selected_chapter_labels),
            generation_mode=generation_mode,
            textbook_file_id=textbook_file_id if used_textbook else None,
        )
        session.add(rs)
        session.flush()
        review_id = rs.id
    session.commit()
    return {
        "ok": True,
        "id": review_id,
        "text": text_out,
        "review_sheet": result,
        "selected_chapter_ids": selected_chapter_ids,
        "selected_chapter_labels": selected_chapter_labels,
        "generation_mode": generation_mode,
        "textbook_file_id": textbook_file_id if used_textbook else None,
    }


def _sse_event(name: str, data: str) -> bytes:
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


async def _iter_review_pro_events(model_input: str, lang: str):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
    stop_event = threading.Event()

    def publish(kind: str, payload: object) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))
        except RuntimeError:
            # The request was already torn down; drop late events from the worker thread.
            pass

    def worker() -> None:
        try:
            for event in generate_review_pro_agent_iter(model_input, lang):
                if stop_event.is_set():
                    break
                publish("event", event)
        except Exception as exc:
            publish("error", exc)
        finally:
            publish("end", None)

    thread = threading.Thread(target=worker, name="rr-review-pro-stream", daemon=True)
    thread.start()

    try:
        while True:
            kind, payload = await queue.get()
            if kind == "event":
                yield payload
                continue
            if kind == "error":
                raise payload  # type: ignore[misc]
            break
    finally:
        stop_event.set()


@router.post("/stream")
async def generate_stream(
    payload: GenerateRequest,
    _ctx=Depends(require_auth_or_trial),
    user_key: str | None = Depends(get_user_key),
    session: Session = Depends(get_session),
):
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

    owner_id = _ctx.get("user_id")
    subject_code = _normalize_subject_code(payload.subject_code)
    course_name = _clean_optional_text(payload.course_name)
    exam_type = _normalize_exam_type(payload.exam_type)
    exam_name = _clean_optional_text(payload.exam_name)
    source_bundle = _collect_generation_sources(payload, session, owner_id)
    text = str(source_bundle["text"])
    used_source_id = source_bundle["used_source_id"]
    first_meta = source_bundle["first_meta"]
    selected_chapter_ids = list(source_bundle["selected_chapter_ids"])
    selected_chapter_labels = list(source_bundle["selected_chapter_labels"])
    generation_mode = str(source_bundle["generation_mode"])
    textbook_file_id = source_bundle["textbook_file_id"]
    textbook_missing_selected = bool(source_bundle["textbook_missing_selected"])
    used_textbook = bool(source_bundle["used_textbook"])
    if generation_mode in {"textbook", "combined"} and not textbook_file_id:
        async def _missing_textbook():
            yield _sse_event("error", "Course textbook not found")
            yield _sse_event("done", "")
        return StreamingResponse(_missing_textbook(), media_type="text/event-stream")
    if generation_mode in {"textbook", "combined"} and selected_chapter_ids and textbook_missing_selected:
        async def _missing_chapter_scope():
            yield _sse_event("error", "Selected chapters are not available in the course textbook")
            yield _sse_event("done", "")
        return StreamingResponse(_missing_chapter_scope(), media_type="text/event-stream")
    if not text:
        async def _empty():
            yield _sse_event("error", "Empty text")
            yield _sse_event("done", "")
        return StreamingResponse(_empty(), media_type="text/event-stream")
    insufficiency_error = _check_content_sufficiency(text, payload.lang or "zh")
    if insufficiency_error:
        async def _insufficient():
            yield _sse_event("error", insufficiency_error)
            yield _sse_event("done", "")
        return StreamingResponse(_insufficient(), media_type="text/event-stream")

    lang = (payload.lang or 'zh')
    if first_meta is not None:
        if not subject_code:
            subject_code = first_meta.subject_code
        if not course_name:
            course_name = first_meta.course_name

    model_input = _build_generation_context(
        text,
        lang,
        subject_code,
        course_name,
        exam_type,
        exam_name,
        selected_chapter_labels,
    )

    async def _gen():
        # Progress events
        try:
            buf_text = ""
            async for ev in _iter_review_pro_events(model_input, lang):
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
            # Persist after generation completes for signed-in users only.
            if buf_text:
                import json as _json
                record_review_generation(session, user_key)
                if owner_id is not None:
                    rs = ReviewSheet(
                        user_id=owner_id,
                        source_id=used_source_id,
                        kind='review_sheet_pro',
                        content=buf_text,
                        subject_code=subject_code,
                        course_name=course_name,
                        exam_type=exam_type,
                        exam_name=exam_name,
                        selected_chapter_ids=dump_json_list(selected_chapter_ids),
                        selected_chapter_labels=dump_json_list(selected_chapter_labels),
                        generation_mode=generation_mode,
                        textbook_file_id=textbook_file_id if used_textbook else None,
                    )
                    session.add(rs)
                    session.flush()
                    yield _sse_event("id", str(rs.id))
                session.commit()
                yield _sse_event("text", _json.dumps({"text": buf_text}, ensure_ascii=False))
        except Exception as e:
            yield _sse_event("error", str(e))
            yield _sse_event("done", "")

    return StreamingResponse(_gen(), media_type="text/event-stream")
