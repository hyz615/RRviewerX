import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app


def test_upload_text_trial():
    with TestClient(app) as client:
        r = client.post("/upload", data={"text": "hello world"})
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j["chars"] >= 5