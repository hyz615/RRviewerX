import sys
from pathlib import Path

# Ensure backend root is in sys.path so `from app.main import app` works from repo root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
import pytest


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

