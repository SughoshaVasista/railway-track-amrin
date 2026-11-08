from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import api
from app.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models import User
from app.security.passwords import hash_password


@pytest.fixture
def recovery_app(tmp_path):
    app = create_app(Settings(
        environment="test",
        jwt_secret_key="password-recovery-test-secret-32-characters",
        database_url=f"sqlite:///{(tmp_path / 'recovery.sqlite').as_posix()}",
        demo_mode=False,
    ))
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory.begin() as db:
        db.add(User(
            id="ADMIN-TEST", name="Admin Test", email="admin@example.com",
            username="admin-test", role="admin", approval_status="approved",
            is_active=True, source="test", password_hash=hash_password("old-password-123"),
        ))
    return app


def test_password_reset_is_generic_one_time_and_revokes_old_tokens(recovery_app, monkeypatch):
    delivered = {}
    monkeypatch.setattr(api.routers.auth, "_send_password_reset", lambda _request, email, token: delivered.update(email=email, token=token))
    client = TestClient(recovery_app)
    existing = client.post("/api/auth/forgot-password", json={"email": "admin@example.com"})
    missing = client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})
    assert existing.status_code == missing.status_code == 202
    assert existing.json() == missing.json()
    assert delivered["email"] == "admin@example.com"
    assert delivered["token"] not in existing.text

    login = client.post("/api/auth/login", json={"username": "admin-test", "password": "old-password-123"})
    old_token = login.json()["token"]
    reset = client.post("/api/auth/reset-password", json={"token": delivered["token"], "password": "new-password-456"})
    assert reset.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert client.post("/api/auth/reset-password", json={"token": delivered["token"], "password": "another-password-789"}).status_code == 400
    assert client.post("/api/auth/login", json={"username": "admin-test", "password": "new-password-456"}).status_code == 200


def test_admin_can_list_safe_account_profiles(recovery_app):
    client = TestClient(recovery_app)
    token = client.post("/api/auth/login", json={"username": "admin-test", "password": "old-password-123"}).json()["token"]
    response = client.get("/api/users?limit=1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    account = response.json()["items"][0]
    assert account["email"] == "admin@example.com"
    assert "password_hash" not in account


def test_admin_can_reset_account_without_email_and_old_sessions_are_revoked(recovery_app):
    client = TestClient(recovery_app)
    admin_token = client.post("/api/auth/login", json={
        "username": "admin-test", "password": "old-password-123",
    }).json()["token"]
    response = client.post(
        "/api/users/ADMIN-TEST/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"password": "admin-reset-password-789"},
    )
    assert response.status_code == 200
    assert "admin-reset-password-789" not in response.text
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": "admin-test", "password": "admin-reset-password-789",
    }).status_code == 200
    with recovery_app.state.session_factory() as db:
        from app.models import EventLog
        assert db.query(EventLog).filter_by(action="admin_password_reset", object_id="ADMIN-TEST").count() == 1
