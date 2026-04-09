import asyncio
import sys
import threading
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.main import app
from app.routes import generate as generate_route


def test_iter_review_pro_events_runs_in_background_thread(monkeypatch):
    captured: dict[str, int] = {}

    def fake_iter(model_input: str, lang: str):
        captured["worker_thread_id"] = threading.get_ident()
        yield {"name": "chapters", "status": "start"}
        yield {"name": "done", "text": "# Review"}

    monkeypatch.setattr(generate_route, "generate_review_pro_agent_iter", fake_iter)

    async def collect_events():
        events = []
        async for event in generate_route._iter_review_pro_events("材料", "zh"):
            events.append(event)
        return events

    caller_thread_id = threading.get_ident()
    events = asyncio.run(collect_events())

    assert [event["name"] for event in events] == ["chapters", "done"]
    assert captured["worker_thread_id"] != caller_thread_id


def test_generate_stream_preserves_sse_contract(monkeypatch):
    def fake_iter(model_input: str, lang: str):
        yield {"name": "condense", "status": "start"}
        yield {"name": "chapters", "status": "done", "count": 2}
        yield {"name": "chapter", "i": 1, "n": 2, "title": "Chapter A"}
        yield {
            "name": "section",
            "chapterIndex": 1,
            "sectionIndex": 1,
            "sectionTitle": "核心概念",
            "chapterTitle": "Chapter A",
        }
        yield {"name": "assemble", "status": "start"}
        yield {"name": "done", "text": "# Review"}

    monkeypatch.setattr(generate_route, "generate_review_pro_agent_iter", fake_iter)

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/generate/stream",
            json={
                "text": "测试材料",
                "format": "review_sheet_pro",
                "length": "long",
                "lang": "zh",
            },
        ) as response:
            body = b"".join(response.iter_raw()).decode("utf-8")

    assert response.status_code == 200
    assert "event: condense" in body
    assert "event: chapters" in body
    assert '"count": 2' in body or '"count":2' in body
    assert "event: chapter" in body
    assert "Chapter A" in body
    assert "event: section" in body
    assert "核心概念" in body
    assert "event: assemble" in body
    assert "event: done" in body
    assert "event: text" in body
    assert "# Review" in body