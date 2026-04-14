import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.db import engine
from app.core.jwt import sign_jwt
from app.main import app
from app.models.models import LocalUser
from app.routes import generate as generate_route


def _quota(client: TestClient, headers: dict[str, str] | None = None) -> dict:
    response = client.get("/status/quota", headers=headers or {})
    assert response.status_code == 200
    return response.json()


def _monthly_usage(client: TestClient, admin_headers: dict[str, str], user_key: str) -> dict:
    response = client.get("/admin/usage/monthly", headers=admin_headers, params={"user_key": user_key})
    assert response.status_code == 200
    return response.json()


def _ensure_admin_user(user_id: int) -> None:
    with Session(engine) as session:
        admin = session.get(LocalUser, user_id)
        if admin is None:
            admin = LocalUser(
                id=user_id,
                email=f"admin-{user_id}@example.com",
                password_hash="test-hash",
                is_admin=True,
                disabled=False,
            )
        else:
            admin.is_admin = True
            admin.disabled = False
        session.add(admin)
        session.commit()


def test_guest_generate_increments_site_total_only():
    with TestClient(app) as client:
        before = _quota(client)

        response = client.post(
            "/generate",
            json={"text": "guest review material", "format": "review_sheet_pro", "length": "short"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True

        after = _quota(client)

    assert after["site_generation_total"] >= before["site_generation_total"] + 1
    assert after["used"] == before["used"]


def test_signed_in_generate_updates_monthly_usage_and_site_total():
    headers = {"Authorization": f"Bearer {sign_jwt('local:97001', 'local')}"}

    with TestClient(app) as client:
        before = _quota(client, headers)

        response = client.post(
            "/generate",
            headers=headers,
            json={"text": "member review material", "format": "review_sheet_pro", "length": "short"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True

        after = _quota(client, headers)

    assert after["used"] == before["used"] + 1
    assert after["site_generation_total"] >= before["site_generation_total"] + 1


def test_admin_usage_endpoint_reflects_generation_count():
    admin_id = 97010
    target_id = 97011
    _ensure_admin_user(admin_id)

    admin_headers = {"Authorization": f"Bearer {sign_jwt(f'local:{admin_id}', 'local')}"}
    target_headers = {"Authorization": f"Bearer {sign_jwt(f'local:{target_id}', 'local')}"}
    user_key = f"local:{target_id}"

    with TestClient(app) as client:
        before = _monthly_usage(client, admin_headers, user_key)

        response = client.post(
            "/generate",
            headers=target_headers,
            json={"text": "admin-visible review material", "format": "review_sheet_pro", "length": "short"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True

        after = _monthly_usage(client, admin_headers, user_key)

    assert after["count"] == before["count"] + 1


def test_stream_generate_updates_monthly_usage_and_site_total(monkeypatch):
    headers = {"Authorization": f"Bearer {sign_jwt('local:97021', 'local')}"}

    def fake_iter(model_input: str, lang: str):
        yield {"name": "chapters", "status": "start"}
        yield {"name": "done", "text": "# Review"}

    monkeypatch.setattr(generate_route, "generate_review_pro_agent_iter", fake_iter)

    with TestClient(app) as client:
        before = _quota(client, headers)

        with client.stream(
            "POST",
            "/generate/stream",
            headers=headers,
            json={
                "text": "stream review material",
                "format": "review_sheet_pro",
                "length": "long",
                "lang": "zh",
            },
        ) as response:
            body = b"".join(response.iter_raw()).decode("utf-8")

        assert response.status_code == 200
        assert "event: text" in body
        assert "# Review" in body

        after = _quota(client, headers)

    assert after["used"] == before["used"] + 1
    assert after["site_generation_total"] >= before["site_generation_total"] + 1


def test_signed_in_generate_returns_text_when_persistence_fails(monkeypatch):
    headers = {"Authorization": f"Bearer {sign_jwt('local:97031', 'local')}"}

    def fake_generate_review(text: str, fmt: str, lang: str = "zh", length: str = "short"):
        return {"text": "# Review"}

    def fail_persist(session, user_key=None):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(generate_route, "generate_review", fake_generate_review)
    monkeypatch.setattr(generate_route, "record_review_generation", fail_persist)

    with TestClient(app) as client:
        response = client.post(
            "/generate",
            headers=headers,
            json={
                "text": "member review material member review material member review material",
                "format": "review_sheet_pro",
                "length": "short",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["id"] is None
    assert payload["text"] == "# Review"
    assert payload["save_warning"] == "Generated successfully, but saving the result failed."