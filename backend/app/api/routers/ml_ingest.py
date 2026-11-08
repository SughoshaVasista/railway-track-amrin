import hashlib
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import AppError
from app.models import Alert, AlertHistory, Device, EventLog, MlOriginEvent, SensorReading
from app.models.entities import utc_now
from app.schemas.ml import MlEventRequest
from app.services.local_vision import InvalidCameraFrame, infer_camera_jpeg

router = APIRouter(prefix="/api/integrations/ml", tags=["ml-ingestion"])
log = logging.getLogger(__name__)


def _store_detection_image(request: Request, alert_id: str, image: bytes) -> str:
    if not image.startswith(b"\xff\xd8\xff"):
        raise AppError(422, "invalid_image", "Detection evidence must be a JPEG image")
    if len(image) > request.app.state.settings.max_content_length:
        raise AppError(413, "image_too_large", "Detection image exceeds the configured upload limit")
    folder = Path(request.app.state.settings.upload_folder).resolve() / "ml-alerts"
    folder.mkdir(parents=True, exist_ok=True)
    # Generated alert IDs contain only safe characters; write atomically so readers
    # never see a partially uploaded frame.
    destination = folder / f"{alert_id}.jpg"
    temporary = folder / f".{alert_id}.{os.getpid()}.tmp"
    temporary.write_bytes(image)
    temporary.replace(destination)
    return f"/api/alerts/{alert_id}/image"


@router.post("/events", status_code=201)
def ingest_event(
    payload: MlEventRequest,
    request: Request,
    db: Session = Depends(get_db),
):

    namespace = hashlib.sha256(f"{payload.source}:{payload.device_id}".encode()).hexdigest()
    existing = db.scalar(select(MlOriginEvent).where(
        MlOriginEvent.source_namespace == namespace,
        MlOriginEvent.source_event_id == payload.source_event_id,
    ))
    if existing:
        return {"event_id": existing.id, "alert_id": existing.alert_id, "duplicate": True}

    device = db.get(Device, payload.device_id)
    if device is None:
        raise AppError(422, "unknown_device", "device_id must refer to a registered device")

    alert_id = f"ALT-{uuid4().hex}"
    alert_source_event_id = hashlib.sha256(f"{namespace}:{payload.source_event_id}".encode()).hexdigest()
    detected_at = payload.detected_at.astimezone(timezone.utc)
    evidence = payload.model_dump(mode="json", exclude_none=True)
    gps = {"accuracy_m": payload.gps_accuracy_m} if payload.gps_accuracy_m is not None else None
    try:
        alert = Alert(
            id=alert_id,
            defect=payload.defect,
            severity=payload.severity,
            status="DETECTED",
            confidence=payload.confidence,
            track=payload.track,
            chainage=payload.chainage,
            latitude=payload.latitude,
            longitude=payload.longitude,
            gps_metadata=gps,
            sensors=payload.sensor_fusion,
            source="ml_backend",
            source_event_id=alert_source_event_id,
            city=payload.city or device.city,
            detected_at=detected_at,
        )
        event = MlOriginEvent(
            id=f"MLE-{uuid4().hex}",
            source_namespace=namespace,
            source_event_id=payload.source_event_id,
            device_id=device.id,
            alert_id=alert_id,
            model_version=payload.model_version,
            inference_ms=payload.inference_ms,
            payload={"schema_version": payload.schema_version, "detection": evidence},
            detected_at=detected_at,
        )
        db.add_all([
            alert,
            event,
            AlertHistory(
                alert_id=alert_id,
                action="ml_detection_ingested",
                new_status="DETECTED",
                changes={"source": "ml_backend", "source_event_id": payload.source_event_id},
                source="ml_backend",
                timestamp=utc_now(),
            ),
            EventLog(
                action="ml_detection_ingested",
                object_type="alert",
                object_id=alert_id,
                summary=f"ML detection recorded: {payload.defect} ({payload.severity})",
                details={"source": payload.source, "device_id": device.id, "event_id": payload.source_event_id},
                source="ml_backend",
                timestamp=utc_now(),
            ),
        ])
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(MlOriginEvent).where(
            MlOriginEvent.source_namespace == namespace,
            MlOriginEvent.source_event_id == payload.source_event_id,
        ))
        if existing:
            return {"event_id": existing.id, "alert_id": existing.alert_id, "duplicate": True}
        raise AppError(500, "ml_event_persist_failed", "The ML event could not be persisted") from None
    except Exception:
        db.rollback()
        raise
    return {"event_id": event.id, "alert_id": alert_id, "duplicate": False}


@router.post("/camera/frame", status_code=200)
async def infer_camera_frame(
    device_id: str = Form(..., min_length=1, max_length=64),
    image: UploadFile = File(...),
    captured_at: str | None = Form(default=None, max_length=48),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Run the local YOLO model on an ESP32 camera frame and persist its result."""
    device = db.get(Device, device_id.strip())
    if device is None:
        raise AppError(422, "unknown_device", "device_id must refer to a registered device")

    settings = request.app.state.settings
    image_bytes = await image.read(settings.max_content_length + 1)
    if len(image_bytes) > settings.max_content_length:
        raise AppError(413, "image_too_large", "Camera frame exceeds the configured upload limit")
    if not image_bytes.startswith(b"\xff\xd8\xff"):
        raise AppError(422, "invalid_image", "Camera frame must be a JPEG image")

    try:
        vision = await run_in_threadpool(
            infer_camera_jpeg,
            image_bytes,
            settings.ml_model_path,
            settings.ml_confidence,
            settings.ml_iou,
            settings.ml_image_size,
        )
    except InvalidCameraFrame as exc:
        raise AppError(422, "invalid_image", str(exc)) from exc
    except FileNotFoundError as exc:
        raise AppError(503, "ml_model_not_found", "The configured local YOLO model is unavailable") from exc
    except ImportError as exc:
        raise AppError(503, "ml_dependencies_missing", "Install backend/requirements-vision.txt to enable local camera inference") from exc

    now = utc_now()
    if captured_at:
        try:
            captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError(422, "invalid_camera_timestamp", "captured_at must be an ISO 8601 timestamp") from exc
    else:
        captured_at = now
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)
    safe_id = hashlib.sha256(device.id.encode()).hexdigest()
    frame_dir = Path(settings.upload_folder).resolve() / "ml-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frame_dir / f"{safe_id}.jpg"
    temporary = frame_dir / f".{safe_id}.{os.getpid()}.tmp"
    temporary.write_bytes(image_bytes)
    temporary.replace(frame_path)

    boxes = vision.boxes
    snapshot = {
        "device_id": device.id,
        "camera_status": "CONNECTED",
        "inference_status": "DETECTED" if boxes else "NO_DEFECT",
        "model_loaded": True,
        "model_name": Path(settings.ml_model_path).name,
        "model_version": Path(settings.ml_model_path).name,
        "class_count": 1,
        "input_size": settings.ml_image_size,
        "confidence_threshold": settings.ml_confidence,
        "inference_ms": vision.inference_ms,
        "captured_at": captured_at.isoformat(),
        "processed_at": now.isoformat(),
        "image_width": vision.image_width,
        "image_height": vision.image_height,
        "boxes": boxes,
        "source": "local_backend",
        "image_url": f"/api/devices/{device.id}/camera/latest",
    }
    diagnostics = dict(device.diagnostics or {})
    diagnostics["latest_inference"] = snapshot
    device.diagnostics = diagnostics
    device.status = "ONLINE"
    device.network_status = "ONLINE"
    device.source = "esp32"

    alert_id = None
    duplicate = False
    alert_image_url = None
    if boxes:
        recent_readings = db.scalars(
            select(SensorReading)
            .where(SensorReading.device_id == device.id)
            .order_by(SensorReading.recorded_at.desc(), SensorReading.id.desc())
            .limit(20)
        ).all()
        sensor_fusion = {
            "readings": {
                reading.name: {
                    "value": reading.numeric_value if reading.numeric_value is not None else reading.text_value if reading.text_value is not None else reading.structured_value,
                    "unit": reading.unit,
                    "status": reading.status,
                    "recorded_at": reading.recorded_at.isoformat(),
                }
                for reading in recent_readings
            }
        }
        if latitude is None or longitude is None:
            gps_reading = next((reading for reading in recent_readings if reading.name.lower() == "gps"), None)
            latitude = latitude if latitude is not None else (gps_reading.latitude if gps_reading else None)
            longitude = longitude if longitude is not None else (gps_reading.longitude if gps_reading else None)

        top_box = max(boxes, key=lambda item: item["confidence"])
        cooldown = max(1, settings.ml_alert_cooldown_seconds)
        bucket = int(now.timestamp() // cooldown)
        class_key = hashlib.sha256(top_box["class"].encode()).hexdigest()[:12]
        event_payload = MlEventRequest(
            schema_version="1.0",
            source_event_id=f"camera-{class_key}-{bucket}",
            detected_at=captured_at,
            source="local-yolo",
            device_id=device.id,
            defect=top_box["class"],
            severity="S2",
            confidence=top_box["confidence"],
            latitude=latitude,
            longitude=longitude,
            boxes=boxes,
            sensor_fusion=sensor_fusion,
            model_version=Path(settings.ml_model_path).name,
            inference_ms=vision.inference_ms,
            city=device.city,
        )
        ingested = ingest_event(event_payload, request, db)
        alert_id = ingested.get("alert_id")
        duplicate = bool(ingested.get("duplicate"))
        if alert_id:
            alert = db.get(Alert, alert_id)
            if alert is not None and duplicate:
                alert_image_url = alert.image_url
            elif alert is not None:
                alert_image_url = _store_detection_image(request, alert_id, vision.annotated_jpeg)
                alert.image_url = alert_image_url
                db.commit()
    else:
        db.commit()

    return {
        "device_id": device.id,
        "inference_status": snapshot["inference_status"],
        "detections": boxes,
        "detection_count": len(boxes),
        "image_width": vision.image_width,
        "image_height": vision.image_height,
        "confidence": max((box["confidence"] for box in boxes), default=None),
        "severity": db.get(Alert, alert_id).severity if alert_id and db.get(Alert, alert_id) else None,
        "alert_id": alert_id,
        "duplicate": duplicate,
        "image_url": snapshot["image_url"],
        "alert_image_url": alert_image_url,
        "inference_ms": vision.inference_ms,
        "processed_at": now.isoformat(),
    }


@router.post("/events/with-image", status_code=201)
async def ingest_event_with_image(
    event: str = Form(...),
    image: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Accept a positive ML event and its annotated JPEG evidence in one request."""
    try:
        payload = MlEventRequest.model_validate_json(event)
    except Exception as exc:
        raise AppError(422, "invalid_ml_event", "The event form field must contain a valid ML event") from exc
    raw_image = await image.read(request.app.state.settings.max_content_length + 1)
    if len(raw_image) > request.app.state.settings.max_content_length:
        raise AppError(413, "image_too_large", "Detection image exceeds the configured upload limit")
    if not raw_image.startswith(b"\xff\xd8\xff"):
        raise AppError(422, "invalid_image", "Detection evidence must be a JPEG image")
    response = ingest_event(payload, request, db)
    if response.get("duplicate"):
        return response
    alert = db.get(Alert, response["alert_id"])
    if alert is None:
        raise AppError(404, "alert_not_found", "Recorded alert was not found")
    try:
        alert.image_url = _store_detection_image(request, alert.id, raw_image)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Could not save ML alert image for %s", alert.id)
        raise AppError(500, "image_persist_failed", "The detection was recorded but its image could not be saved") from None
    response["image_url"] = alert.image_url
    return response


@router.post("/frames", status_code=200)
async def ingest_latest_frame(
    snapshot: str = Form(...),
    image: UploadFile | None = File(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Replace one latest per-device frame/state snapshot; never stores every frame."""
    try:
        state = json.loads(snapshot)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AppError(422, "invalid_frame_snapshot", "snapshot must be valid JSON") from exc
    if not isinstance(state, dict) or not isinstance(state.get("device_id"), str):
        raise AppError(422, "invalid_frame_snapshot", "snapshot must contain a device_id")
    device = db.get(Device, state["device_id"])
    if device is None:
        raise AppError(422, "unknown_device", "device_id must refer to a registered device")
    image_url = None
    frame_bytes = await image.read(request.app.state.settings.max_content_length + 1) if image else b""
    if len(frame_bytes) > request.app.state.settings.max_content_length:
        raise AppError(413, "image_too_large", "Camera frame exceeds the configured upload limit")
    if frame_bytes:
        if not frame_bytes.startswith(b"\xff\xd8\xff"):
            raise AppError(422, "invalid_image", "Camera frame must be a JPEG image")
        frame_dir = Path(request.app.state.settings.upload_folder).resolve() / "ml-frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        safe_id = hashlib.sha256(device.id.encode()).hexdigest()
        destination = frame_dir / f"{safe_id}.jpg"
        temporary = frame_dir / f".{safe_id}.{os.getpid()}.tmp"
        temporary.write_bytes(frame_bytes)
        temporary.replace(destination)
        image_url = f"/api/devices/{device.id}/camera/latest"
    state["image_url"] = image_url
    state["frame_url"] = image_url
    state["received_at"] = utc_now().isoformat()
    diagnostics = dict(device.diagnostics or {})
    diagnostics["latest_inference"] = state
    device.diagnostics = diagnostics
    device.status = "ONLINE" if state.get("camera_status") == "CONNECTED" else "DEGRADED"
    device.pi_status = device.status
    device.source = "raspberry_pi"
    db.commit()
    return {"device_id": device.id, "image_url": image_url, "inference_status": state.get("inference_status"), "received_at": state["received_at"]}
