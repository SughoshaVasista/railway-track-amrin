from __future__ import annotations

import sys
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models import Device, User


def test_latest_frame_and_alert_photo_round_trip(tmp_path):
    secret = "camera-flow-test-secret-at-least-32-bytes"
    app = create_app(Settings(
        environment="test",
        demo_mode=False,
        jwt_secret_key=secret,
        ml_ingest_token="test-ml-token",
        database_url=f"sqlite:///{(tmp_path / 'camera.sqlite').as_posix()}",
        upload_folder=str(tmp_path / "uploads"),
    ))
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        db.add_all([
            User(id="ADMIN-1", name="Admin", email="admin@example.test", role="admin", approval_status="approved", is_active=True, source="test"),
            Device(id="pi-camera-1", name="Pi camera", status="UNKNOWN", source="test"),
        ])
        db.commit()
    token = jwt.encode({"sub": "ADMIN-1", "type": "access"}, secret, algorithm="HS256")
    admin = {"Authorization": f"Bearer {token}"}
    jpeg = b"\xff\xd8\xffcamera-test-frame"

    with TestClient(app) as client:
        snapshot = {
            "device_id": "pi-camera-1", "camera_status": "CONNECTED",
            "inference_status": "NO_DEFECT", "model_loaded": True,
            "captured_at": "2026-10-27T10:00:00+00:00",
            "processed_at": "2026-10-27T10:00:01+00:00",
            "image_width": 640, "image_height": 480, "boxes": [],
        }
        frame = client.post(
            "/api/integrations/ml/frames",
            data={"snapshot": __import__("json").dumps(snapshot)},
            files={"image": ("frame.jpg", jpeg, "image/jpeg")},
        )
        assert frame.status_code == 200, frame.text
        detection = client.get("/api/ai/detection", headers=admin)
        assert detection.status_code == 200
        assert detection.json()["detection"]["status"] == "NO_DEFECT"
        image_url = detection.json()["detection"]["image_url"]
        assert client.get(image_url, headers=admin).content == jpeg

        event = {
            "schema_version": "1.0", "source_event_id": "camera-event-1",
            "detected_at": "2026-10-27T10:01:00+00:00", "source": "railsafe-pi",
            "device_id": "pi-camera-1", "defect": "rail_crack", "severity": "S2",
            "confidence": 0.8, "latitude": None, "longitude": None,
            "boxes": [{"class": "crack", "confidence": 0.8, "box": [1, 2, 20, 30]}],
            "model_version": "best.pt", "inference_ms": 100,
        }
        uploaded = client.post(
            "/api/integrations/ml/events/with-image",
            data={"event": __import__("json").dumps(event)},
            files={"image": ("alert.jpg", jpeg, "image/jpeg")},
        )
        assert uploaded.status_code == 201, uploaded.text
        alert = uploaded.json()
        assert alert["image_url"] == f"/api/alerts/{alert['alert_id']}/image"
        assert client.get(alert["image_url"], headers=admin).content == jpeg
    app.state.engine.dispose()
