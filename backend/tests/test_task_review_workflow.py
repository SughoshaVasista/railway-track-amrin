from __future__ import annotations

import binascii
import struct
import sys
import zlib
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models import Alert, MaintenanceTask, User


SECRET = "review-workflow-test-secret"


def png_bytes() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def workflow():
    def _make(tmp_path: Path):
        database_path = tmp_path / "review-test.sqlite"
        upload_path = tmp_path / "evidence"
        app = create_app(Settings(
            environment="test",
            demo_mode=False,
            jwt_secret_key=SECRET,
            database_url=f"sqlite:///{database_path.as_posix()}",
            upload_folder=str(upload_path),
            max_content_length=1024,
        ))
        Base.metadata.create_all(app.state.engine)

        with app.state.session_factory() as db:
            admin = User(
                id="ADMIN-1", name="Admin", email="admin@example.test", role="admin",
                approval_status="approved", is_active=True, source="test",
            )
            worker = User(
                id="WORKER-1", worker_id="W-1", name="Worker", email="worker@example.test",
                role="worker", approval_status="approved", is_active=True, source="test",
            )
            other = User(
                id="WORKER-2", worker_id="W-2", name="Other Worker", email="other@example.test",
                role="worker", approval_status="approved", is_active=True, source="test",
            )
            alert = Alert(
                id="ALERT-1", defect="Rail crack", severity="S2", status="UNDER_REPAIR",
                source="test", city="bengaluru", assigned_worker=worker,
            )
            task = MaintenanceTask(
                id="TASK-1", alert=alert, assigned_worker=worker, status="IN_PROGRESS",
                priority="S2", source="test",
            )
            db.add_all([admin, worker, other, alert, task])
            db.commit()

        def token(user_id: str) -> dict[str, str]:
            value = jwt.encode({"sub": user_id, "type": "access"}, SECRET, algorithm="HS256")
            return {"Authorization": f"Bearer {value}"}

        return app, TestClient(app), token, upload_path

    return _make


def upload(client: TestClient, headers: dict[str, str], *, content: bytes | None = None):
    content = png_bytes() if content is None else content
    return client.post(
        "/api/tasks/TASK-1/evidence",
        headers=headers,
        data={"evidence_type": "repair", "notes": "Repair completed"},
        files={"file": ("repair.png", content, "image/png")},
    )


def test_review_migrations_preserve_existing_records(tmp_path, monkeypatch):
    database_path = tmp_path / "migration-test.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))

    command.upgrade(config, "4b7c1a2d9e31")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        now = "2026-10-26T00:00:00+00:00"
        connection.execute(text("""
            INSERT INTO users (id, name, email, role, approval_status, is_active, source, created_at, updated_at)
            VALUES ('WORKER-1', 'Worker', 'worker@example.test', 'worker', 'approved', 1, 'test', :now, :now)
        """), {"now": now})
        connection.execute(text("""
            INSERT INTO alerts (id, defect, severity, status, source, city, assigned_worker_user_id, created_at, updated_at)
            VALUES ('ALERT-1', 'Rail crack', 'S2', 'UNDER_REPAIR', 'test', 'bengaluru', 'WORKER-1', :now, :now)
        """), {"now": now})
        connection.execute(text("""
            INSERT INTO maintenance_tasks
                (id, alert_id, assigned_worker_user_id, status, priority, source, created_at, updated_at)
            VALUES ('TASK-1', 'ALERT-1', 'WORKER-1', 'IN_PROGRESS', 'S2', 'test', :now, :now)
        """), {"now": now})

    command.upgrade(config, "head")
    inspector = inspect(engine)
    task_columns = {column["name"] for column in inspector.get_columns("maintenance_tasks")}
    assert {"review_status", "review_notes", "review_requested_at"} <= task_columns
    assert inspector.has_table("task_evidence")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM maintenance_tasks WHERE id='TASK-1'")).scalar_one() == "IN_PROGRESS"
        assert connection.execute(text("SELECT status FROM alerts WHERE id='ALERT-1'")).scalar_one() == "UNDER_REPAIR"
        assert connection.execute(text("SELECT COUNT(*) FROM users WHERE id='WORKER-1'")).scalar_one() == 1
    engine.dispose()


def test_worker_rework_fresh_evidence_and_admin_approval(workflow, tmp_path):
    app, client, token, upload_path = workflow(tmp_path)
    worker = token("WORKER-1")
    admin = token("ADMIN-1")
    try:
        missing = client.post("/api/tasks/TASK-1/submit", headers=worker, json={"notes": "Done"})
        assert missing.status_code == 409
        assert missing.json()["error"]["code"] == "repair_evidence_required"

        evidence = upload(client, worker)
        assert evidence.status_code == 201
        evidence_data = evidence.json()
        assert evidence_data["evidence_type"] == "repair"
        assert evidence_data["original_filename"] == "repair.png"
        assert evidence_data["created_at"]
        assert (upload_path / evidence_data["filename"]).is_file()
        image_path = evidence_data["url"].removeprefix("/api")
        assert client.get(image_path, headers=token("WORKER-2")).status_code == 403
        image_response = client.get(image_path, headers=admin)
        assert image_response.status_code == 200
        assert image_response.content == png_bytes()

        submitted = client.post("/api/tasks/TASK-1/submit", headers=worker, json={"notes": "Ready"})
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "AWAITING_REVIEW"
        assert submitted.json()["evidence"][0]["id"] == evidence_data["id"]

        rework = client.post(
            "/api/tasks/TASK-1/review", headers=admin,
            json={"decision": "request_changes", "notes": "Add a close-up repair photo"},
        )
        assert rework.status_code == 200
        assert rework.json()["status"] == "IN_PROGRESS"
        assert rework.json()["review_status"] == "REWORK"

        stale = client.post("/api/tasks/TASK-1/submit", headers=worker, json={})
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "repair_evidence_required"

        fresh_evidence = upload(client, worker)
        assert fresh_evidence.status_code == 201
        resubmitted = client.post("/api/tasks/TASK-1/submit", headers=worker, json={})
        assert resubmitted.status_code == 200
        assert resubmitted.json()["status"] == "AWAITING_REVIEW"

        approved = client.post("/api/tasks/TASK-1/review", headers=admin, json={"decision": "approve"})
        assert approved.status_code == 200
        body = approved.json()
        assert body["status"] == "COMPLETED"
        assert body["review_status"] == "APPROVED"
        assert len(body["evidence"]) == 2
        assert [item["action"] for item in body["review_history"]] == [
            "maintenance_task_submitted_for_review",
            "maintenance_task_changes_requested",
            "maintenance_task_submitted_for_review",
            "maintenance_task_approved",
        ]
        with app.state.session_factory() as db:
            assert db.get(Alert, "ALERT-1").status == "RESOLVED"
    finally:
        client.close()
        app.state.engine.dispose()


def test_evidence_and_review_enforce_identity_and_validation(workflow, tmp_path):
    app, client, token, _upload_path = workflow(tmp_path)
    worker = token("WORKER-1")
    other = token("WORKER-2")
    admin = token("ADMIN-1")
    try:
        bad_type = client.post(
            "/api/tasks/TASK-1/evidence", headers=worker,
            files={"file": ("not-image.txt", b"text", "text/plain")},
        )
        assert bad_type.status_code == 415

        oversized = upload(client, worker, content=png_bytes() + (b"x" * 2048))
        assert oversized.status_code == 413

        wrong_owner = upload(client, other)
        assert wrong_owner.status_code == 403

        no_token = client.post("/api/tasks/TASK-1/review", json={"decision": "approve"})
        assert no_token.status_code == 401

        worker_review = client.post(
            "/api/tasks/TASK-1/review", headers=worker, json={"decision": "approve"},
        )
        assert worker_review.status_code == 403

        invalid_decision = client.post(
            "/api/tasks/TASK-1/review", headers=admin,
            json={"decision": "complete"},
        )
        assert invalid_decision.status_code == 422

        missing_rework_notes = client.post(
            "/api/tasks/TASK-1/review", headers=admin,
            json={"decision": "request_changes", "notes": "  "},
        )
        assert missing_rework_notes.status_code == 422
    finally:
        client.close()
        app.state.engine.dispose()
