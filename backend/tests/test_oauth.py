import os
import pytest
from fastapi.testclient import TestClient


def get_client():
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    if str(root / 'backend') not in sys.path:
        sys.path.insert(0, str(root / 'backend'))
    from app.main import app
    return TestClient(app)


def test_oauth_start_fallback_google(monkeypatch):
    client = get_client()
    # Ensure google not fully configured -> returns JSON with auth_url (fallback)
    monkeypatch.delenv('GOOGLE_CLIENT_ID', raising=False)
    r = client.get('/auth/oauth/google/start')
    assert r.status_code in (200, 400)
    data = r.json()
    # When not configured, return 400
    if r.status_code == 400:
        assert data.get('ok') is False
    else:
        assert data.get('ok') is True and 'auth_url' in data


def test_oauth_callback_sets_cookie_and_redirect(monkeypatch):
    client = get_client()
    # No real exchange, should fallback and issue app token
    r = client.get('/auth/oauth/google/callback?code=dummy')
    # Redirect to frontend callback.html
    assert r.status_code in (302, 307, 303)
    # Cookie rr_token should be present
    cookies = r.cookies
    # In TestClient, cookies from redirect response are not automatically exposed; check headers
    set_cookie = r.headers.get('set-cookie', '')
    assert 'rr_token=' in set_cookie
