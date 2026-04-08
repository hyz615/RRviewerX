import sys
from pathlib import Path

# Ensure backend root is in sys.path so `from app.main import app` works from repo root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
import pytest
from app.core.jwt import sign_jwt


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_trial_status(client):
    r = client.get("/auth/trial-status")
    assert r.status_code == 200
    assert "trial_used" in r.json()


def test_generate_outline_and_chat(client):
    r = client.post("/generate", json={"text": "测试文本", "format": "outline"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["review_sheet"]["type"] == "outline"

    # single question
    r2 = client.post("/chat", json={"question": "这段主旨是什么？"})
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    # batch questions
    r3 = client.post("/chat", json={"questions": ["A?", "B?"]})
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3["ok"] is True and len(j3["answers"]) == 2


def test_subject_history_persists_exam_metadata(client):
    token = sign_jwt("local:9301", "local")
    headers = {"Authorization": f"Bearer {token}"}

    upload = client.post(
        "/upload",
        headers=headers,
        data={"subject_code": "math", "course_name": "Linear Algebra"},
        files={"file": ("matrix.txt", b"matrix inverse determinant eigenvalue", "text/plain")},
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]

    first = client.post(
        "/generate",
        headers=headers,
        json={
            "format": "qa",
            "length": "short",
            "source_ids": [str(file_id)],
            "exam_type": "midterm",
            "exam_name": "2026 Spring Midterm",
        },
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = client.post(
        "/generate",
        headers=headers,
        json={
            "format": "qa",
            "length": "short",
            "source_ids": [str(file_id)],
            "exam_type": "final",
            "exam_name": "2026 Spring Final",
        },
    )
    assert second.status_code == 200

    filtered = client.get(
        "/history",
        headers=headers,
        params={"subject_code": "math", "exam_type": "midterm"},
    )
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert any(item["id"] == first_id for item in items)
    assert all(item["subject_code"] == "math" for item in items)
    assert all(item["exam_type"] == "midterm" for item in items)

    detail = client.get(f"/history/{first_id}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["subject_code"] == "math"
    assert payload["course_name"] == "Linear Algebra"
    assert payload["exam_type"] == "midterm"
    assert payload["exam_name"] == "2026 Spring Midterm"

