import hmac
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from pathlib import Path
import hashlib
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.errors import AppError
from app.models import (
    Alert,
    AlertHistory,
    DecisionState,
    Device,
    EventLog,
    MlOriginEvent,
    MaintenanceTask,
    SensorReading,
    Track,
    Train,
    User,
)
from app.models.entities import utc_now
from app.schemas.serializers import (
    _iso,
    serialize_alert,
    serialize_decision,
    serialize_device,
    serialize_event_log,
    serialize_sensor_reading,
    serialize_track,
    serialize_train,
)
from app.schemas.telemetry import DeviceRegistration, SensorReadingsBatch, SwitchDecisionRequest
from app.security.dependencies import require_roles

router = APIRouter(prefix="/api", tags=["telemetry and dashboard"])
admin_user = require_roles("admin")
map_user = require_roles("admin", "worker")
device_user = require_roles("admin")
dashboard_user = require_roles("admin")
WINDOWS = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
ACTIVE_ALERT_STATES = ("ACTIVE", "DETECTED", "VERIFIED", "ACKNOWLEDGED", "ASSIGNED", "UNDER_REPAIR", "REOPENED")


@router.post("/integrations/sensors/readings", status_code=201)
def ingest_sensor_readings(
    payload: SensorReadingsBatch,
    request: Request,
    x_sensor_api_key: str | None = Header(default=None, alias="X-Sensor-API-Key"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    configured_token = request.app.state.settings.sensor_ingest_token
    if not configured_token:
        raise AppError(503, "sensor_ingestion_not_configured", "Sensor ingestion is disabled until SENSOR_INGEST_TOKEN is configured")
    if not x_sensor_api_key or not hmac.compare_digest(x_sensor_api_key, configured_token):
        raise AppError(401, "invalid_sensor_api_key", "A valid sensor API key is required")
    device = db.get(Device, payload.device_id)
    if device is None:
        raise AppError(422, "unknown_device", "device_id must refer to a registered device")

    now = utc_now()
    rows = []
    for item in payload.readings:
        recorded_at = item.recorded_at or now
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        recorded_at = recorded_at.astimezone(timezone.utc)
        if recorded_at > now + timedelta(minutes=1):
            raise AppError(422, "invalid_sensor_timestamp", "Sensor timestamps cannot be more than one minute in the future")
        value = item.value
        numeric_value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        text_value = value if isinstance(value, str) else None
        structured_value = value if isinstance(value, (dict, list, bool)) or value is None else None
        rows.append(SensorReading(
            device_id=device.id,
            name=item.name.strip(),
            status=item.status.upper(),
            numeric_value=numeric_value,
            text_value=text_value,
            structured_value=structured_value,
            unit=item.unit,
            interpreted_value=item.interpreted_value,
            latitude=item.latitude,
            longitude=item.longitude,
            source=payload.source,
            recorded_at=recorded_at,
        ))
    device.status = "ONLINE"
    device.pi_status = "ONLINE" if payload.source == "raspberry_pi" else None
    device.network_status = "ONLINE"
    device.source = payload.source
    db.add_all(rows)
    db.commit()
    return {"device_id": device.id, "accepted": len(rows), "latest_recorded_at": max(row.recorded_at for row in rows).isoformat()}


@router.post("/devices", status_code=201)
def register_device(
    payload: DeviceRegistration,
    _user: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if _user.source == "demo":
        raise AppError(403, "demo_read_only", "Demo data is read-only. No changes were saved.")
    device_id = payload.id.strip()
    name = payload.name.strip()
    if not device_id or not name:
        raise AppError(422, "invalid_device", "Device ID and name cannot be blank")
    if db.get(Device, device_id) is not None:
        raise AppError(409, "device_already_registered", "A device with this ID is already registered")
    device = Device(id=device_id, name=name, platform=payload.platform, city=payload.city, status="UNKNOWN", source="hardware")
    db.add(device)
    db.commit()
    db.refresh(device)
    return serialize_device(device)


@router.get("/devices")
def list_devices(_user: User = Depends(device_user), db: Session = Depends(get_db)) -> dict[str, list[dict]]:
    statement = select(Device)
    if _user.source == "demo":
        statement = statement.where(Device.source == "demo")
    devices = db.scalars(statement.order_by(Device.city, Device.name, Device.id).limit(500)).all()
    return {"items": [serialize_device(item) for item in devices]}


@router.get("/devices/{device_id}/sensors")
def get_device_sensors(
    device_id: str,
    history: bool = False,
    window: str = "24h",
    _user: User = Depends(device_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict]]:
    device = db.get(Device, device_id)
    if device is None:
        raise AppError(404, "device_not_found", "Device was not found")
    if _user.source == "demo" and device.source != "demo":
        raise AppError(404, "device_not_found", "Device was not found")
    if history and window not in WINDOWS:
        raise AppError(422, "invalid_window", "Window must be one of 1h, 6h, 24h, 7d, or 30d")
    statement = select(SensorReading).where(SensorReading.device_id == device_id)
    if _user.source == "demo":
        statement = statement.where(SensorReading.source == "demo")
    if history:
        statement = statement.where(SensorReading.recorded_at >= utc_now() - WINDOWS[window])
    rows = db.scalars(statement.order_by(SensorReading.recorded_at.desc(), SensorReading.id.desc()).limit(1000)).all()
    if history:
        return {"items": [serialize_sensor_reading(row) for row in reversed(rows)]}
    latest: dict[str, SensorReading] = {}
    for reading in rows:
        latest.setdefault(reading.name, reading)
    # Demo telemetry is intentionally simulated and clearly labeled. Advance it
    # on read so the dashboard walkthrough stays live without physical hardware.
    if device.source == "demo" or any(reading.source == "demo" for reading in latest.values()):
        now = utc_now()
        for reading in latest.values():
            reading.recorded_at = now
            if reading.name.lower() == "ultrasonic" and reading.numeric_value is not None:
                reading.numeric_value = round(16.0 + 5.0 * ((now.second % 20) / 20), 1)
                reading.interpreted_value = "SIMULATED demo distance"
            elif reading.name.lower() == "temperature" and reading.numeric_value is not None:
                reading.numeric_value = round(27.0 + 2.0 * ((now.second % 30) / 30), 1)
                reading.interpreted_value = "SIMULATED demo temperature"
            elif reading.name.lower() in {"accelerometer", "accel"} and reading.numeric_value is not None:
                reading.numeric_value = round(0.1 + 0.05 * ((now.second % 10) / 10), 3)
                reading.x = round(0.1 + 0.02 * ((now.second % 8) / 8), 3)
                reading.y = round(0.06 + 0.02 * ((now.second % 12) / 12), 3)
                reading.z = reading.numeric_value
                reading.vibration = "SIMULATED normal"
                reading.anomaly_score = 0.08
                reading.status = "ONLINE"
                reading.interpreted_value = "SIMULATED demo vibration"
            elif reading.name.lower() == "gps" and reading.latitude is not None and reading.longitude is not None:
                reading.latitude = round(12.9724 + 0.0001 * ((now.second % 5) / 5), 6)
                reading.longitude = round(77.5950 + 0.0001 * ((now.second % 7) / 7), 6)
                reading.interpreted_value = "SIMULATED demo position"
            elif reading.name.lower() == "camera":
                reading.text_value = f"SIMULATED FRAME {now.strftime('%H%M%S')}"
                reading.interpreted_value = "SIMULATED demo camera heartbeat"
        device.status = "ONLINE"
        device.network_status = "ONLINE"
        device.uptime = "SIMULATED DEMO"
        device.updated_at = now
        db.commit()
        for reading in latest.values():
            db.refresh(reading)
    return {"items": [serialize_sensor_reading(latest[name]) for name in sorted(latest)]}


@router.get("/devices/{device_id}/diagnostics")
def get_device_diagnostics(
    device_id: str,
    _user: User = Depends(device_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    device = db.get(Device, device_id)
    if device is None:
        raise AppError(404, "device_not_found", "Device was not found")
    if _user.source == "demo" and device.source != "demo":
        raise AppError(404, "device_not_found", "Device was not found")
    diagnostic = device.diagnostics or {}
    checks = diagnostic.get("checks", [])
    if isinstance(checks, dict):
        checks = [{"name": name, "status": value} for name, value in checks.items()]
    return {
        "device_id": device.id,
        "status": device.status,
        "pi_status": device.pi_status or diagnostic.get("pi_status"),
        "network_status": device.network_status or diagnostic.get("network_status"),
        "uptime": device.uptime or diagnostic.get("uptime"),
        "updated_at": _iso(device.updated_at),
        "checks": checks if isinstance(checks, list) else [],
        "source": device.source,
        "demo": device.source == "demo",
    }


@router.get("/devices/{device_id}/camera/latest")
def get_latest_camera_frame(
    device_id: str,
    request: Request,
    _user: User = Depends(device_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    device = db.get(Device, device_id)
    if device is None:
        raise AppError(404, "device_not_found", "Device was not found")
    if _user.source == "demo" and device.source != "demo":
        raise AppError(404, "device_not_found", "Device was not found")
    safe_id = hashlib.sha256(device.id.encode()).hexdigest()
    root = (Path(request.app.state.settings.upload_folder).resolve() / "ml-frames").resolve()
    path = (root / f"{safe_id}.jpg").resolve()
    if path.parent != root or not path.is_file():
        raise AppError(404, "camera_frame_not_found", "No camera frame has been uploaded for this device")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/tracks")
def list_tracks(
    city: str | None = None,
    user: User = Depends(map_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict]]:
    statement = select(Track)
    if user.source == "demo":
        statement = statement.where(Track.source == "demo")
    if user.role == "worker":
        if not user.city:
            statement = statement.where(Track.source == "demo")
        else:
            city = user.city
    if city and city.lower() not in {"all", "any"}:
        statement = statement.where(or_(func.lower(Track.city) == city.strip().lower(), Track.source == "demo"))
    tracks = db.scalars(statement.order_by(Track.city, Track.name, Track.id).limit(1000)).all()
    return {"items": [serialize_track(item) for item in tracks]}


@router.get("/trains")
def list_trains(
    city: str | None = None,
    user: User = Depends(map_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict]]:
    statement = select(Train)
    if user.source == "demo":
        statement = statement.where(Train.source == "demo")
    if user.role == "worker":
        if not user.city:
            statement = statement.where(Train.source == "demo")
        else:
            city = user.city
    if city and city.lower() not in {"all", "any"}:
        statement = statement.where(or_(func.lower(Train.city) == city.strip().lower(), Train.source == "demo"))
    trains = db.scalars(statement.order_by(Train.updated_at.desc(), Train.id).limit(500)).all()
    return {"items": [serialize_train(item) for item in trains]}


@router.get("/switch/status")
def get_switch_status(_user: User = Depends(map_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    statement = select(DecisionState)
    if _user.source == "demo":
        statement = statement.where(DecisionState.source == "demo")
    decision = db.scalar(statement.order_by(DecisionState.updated_at.desc(), DecisionState.id).limit(1))
    if decision is None:
        return {
            "status": "NO_DATA",
            "action": None,
            "action_level": None,
            "train_id": None,
            "switch_id": None,
            "target_track": None,
            "confidence": None,
            "reason": "No decision-support data has been recorded.",
            "latitude": None,
            "longitude": None,
            "rules_checked": [],
            "raw_scores": {},
            "source": "none",
            "demo": False,
        }
    return serialize_decision(decision)


@router.post("/switch/decision")
def record_switch_decision(
    payload: SwitchDecisionRequest,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if actor.source == "demo":
        raise AppError(403, "demo_read_only", "Demo data is read-only. No changes were saved.")
    raw = payload.model_dump(mode="json", exclude_none=True)
    train_id = payload.train_id
    train = db.get(Train, train_id) if train_id else None
    position = {"latitude": payload.latitude, "longitude": payload.longitude}
    if train is not None:
        position["latitude"] = train.latitude
        position["longitude"] = train.longitude
    row = db.get(DecisionState, "latest")
    if row is None:
        row = DecisionState(id="latest", source="simulation")
        db.add(row)
    row.status = "READY" if payload.action != "EMERGENCY_STOP" else "ALERT"
    row.action = payload.action
    row.action_level = payload.action_level
    row.train_id = train.id if train else None
    row.switch_id = payload.switch_id
    row.target_track = payload.target_track
    row.confidence = payload.confidence
    row.reason = payload.reason
    row.latitude = position["latitude"]
    row.longitude = position["longitude"]
    row.rules_checked = [rule.model_dump() for rule in payload.rules_checked]
    row.raw_scores = payload.raw_scores
    row.payload = raw
    row.source = "simulation"
    row.updated_at = utc_now()
    db.add(EventLog(
        actor_user_id=actor.id,
        action="simulation_decision_recorded",
        object_type="decision",
        object_id=row.id,
        summary=f"Simulation decision recorded: {payload.action}",
        details={"train_id": payload.train_id, "action": payload.action, "target_track": payload.target_track},
        source="simulation",
    ))
    db.commit()
    db.refresh(row)
    return serialize_decision(row)


@router.get("/dashboard/summary")
def get_dashboard_summary(
    city: str | None = None,
    _user: User = Depends(dashboard_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    alert_query = select(Alert).where(Alert.status.in_(ACTIVE_ALERT_STATES))
    task_count_query = select(func.count(MaintenanceTask.id)).where(MaintenanceTask.status != "COMPLETED")
    device_count_query = select(func.count(Device.id))
    online_device_query = select(func.count(Device.id)).where(Device.status == "ONLINE")
    if _user.source == "demo":
        alert_query = alert_query.where(Alert.source == "demo")
        task_count_query = task_count_query.where(MaintenanceTask.source == "demo")
        device_count_query = device_count_query.where(Device.source == "demo")
        online_device_query = online_device_query.where(Device.source == "demo")
    if city and city.lower() not in {"all", "any"}:
        normalized_city = city.strip().lower()
        alert_query = alert_query.where(or_(func.lower(Alert.city) == normalized_city, Alert.source == "demo"))
        task_count_query = task_count_query.join(MaintenanceTask.alert).where(or_(func.lower(Alert.city) == normalized_city, Alert.source == "demo", MaintenanceTask.source == "demo"))
        device_count_query = device_count_query.where(or_(func.lower(Device.city) == normalized_city, Device.source == "demo"))
        online_device_query = online_device_query.where(or_(func.lower(Device.city) == normalized_city, Device.source == "demo"))
    active_alerts = db.scalars(alert_query).all()
    pending_tasks = db.scalar(task_count_query)
    online_devices = db.scalar(online_device_query)
    total_devices = db.scalar(device_count_query)
    alert_sync_query = select(func.max(Alert.updated_at))
    task_sync_query = select(func.max(MaintenanceTask.updated_at)).join(MaintenanceTask.alert)
    device_sync_query = select(func.max(Device.updated_at))
    if _user.source == "demo":
        alert_sync_query = alert_sync_query.where(Alert.source == "demo")
        task_sync_query = task_sync_query.where(MaintenanceTask.source == "demo")
        device_sync_query = device_sync_query.where(Device.source == "demo")
    if city and city.lower() not in {"all", "any"}:
        normalized_city = city.strip().lower()
        alert_sync_query = alert_sync_query.where(or_(func.lower(Alert.city) == normalized_city, Alert.source == "demo"))
        task_sync_query = task_sync_query.where(or_(func.lower(Alert.city) == normalized_city, Alert.source == "demo", MaintenanceTask.source == "demo"))
        device_sync_query = device_sync_query.where(or_(func.lower(Device.city) == normalized_city, Device.source == "demo"))
    timestamps = [db.scalar(alert_sync_query), db.scalar(task_sync_query), db.scalar(device_sync_query)]
    last_sync = max((timestamp for timestamp in timestamps if timestamp is not None), default=None)
    return {
        "active_alerts": len(active_alerts),
        "s3_alerts": sum(1 for item in active_alerts if item.severity == "S3"),
        "s2_alerts": sum(1 for item in active_alerts if item.severity == "S2"),
        "s1_alerts": sum(1 for item in active_alerts if item.severity == "S1"),
        "pending_tasks": pending_tasks or 0,
        "online_devices": online_devices or 0,
        "total_devices": total_devices or 0,
        "last_sync": _iso(last_sync),
        "city": city or "all",
        "demo_mode": _user.source == "demo",
    }


@router.get("/dashboard/event-log")
def get_dashboard_event_log(
    since: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    _user: User = Depends(dashboard_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = select(EventLog).options(joinedload(EventLog.actor))
    if _user.source == "demo":
        statement = statement.where(EventLog.source == "demo")
    if since:
        statement = statement.where(EventLog.timestamp >= since)
    entries = db.scalars(statement.order_by(EventLog.timestamp.desc(), EventLog.id).limit(limit)).unique().all()
    if not entries and db.get(EventLog, "EVT-DEMO-001") is not None:
        entries = db.scalars(select(EventLog).options(joinedload(EventLog.actor)).where(EventLog.source == "demo").order_by(EventLog.timestamp.desc(), EventLog.id).limit(limit)).unique().all()
    return {"items": [serialize_event_log(item) for item in entries], "generated_at": utc_now().isoformat(), "demo_mode": _user.source == "demo"}


@router.get("/model/status")
def get_model_status(_user: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    statement = select(Device)
    if _user.source == "demo":
        statement = statement.where(Device.source == "demo")
    devices = db.scalars(statement.order_by(Device.source == "demo", Device.updated_at.desc()).limit(100)).all()
    snapshots = [(device, (device.diagnostics or {}).get("latest_inference")) for device in devices]
    snapshots = [(device, state) for device, state in snapshots if isinstance(state, dict)]
    if snapshots:
        device, latest = snapshots[0]
        age = (utc_now() - device.updated_at.replace(tzinfo=timezone.utc) if device.updated_at.tzinfo is None else utc_now() - device.updated_at).total_seconds()
        fresh = age < 30
        demo = bool(latest.get("demo") or device.source == "demo")
        return {"model": {"loaded": bool(latest.get("model_loaded", False)), "inference_active": fresh and latest.get("inference_status") not in {"ERROR", "CAMERA_DISCONNECTED"}, "name": latest.get("model_name"), "version": latest.get("model_version"), "class_count": latest.get("class_count"), "input_size": latest.get("input_size"), "inference_ms": latest.get("inference_ms"), "device": device.id, "source": latest.get("source", device.source), "demo": demo, "camera_status": latest.get("camera_status"), "status": latest.get("inference_status", "NO DATA") if fresh else "STALE", "updated_at": latest.get("processed_at") or latest.get("captured_at"), "stale": not fresh}}
    return {
        "model": {
            "loaded": False,
            "inference_active": False,
            "name": None,
            "version": None,
            "class_count": None,
            "input_size": None,
            "inference_ms": None,
            "device": None,
            "source": "none",
            "status": "NO ML SERVICE CONNECTED",
                "message": "No machine-learning service has reported a model status.",
                "demo": bool(db.get(Device, "esp32-cam-01") and (db.get(Device, "esp32-cam-01").diagnostics or {}).get("latest_inference", {}).get("demo")),
        }
    }


@router.get("/ai/detection")
def get_ai_detection(_user: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    statement = select(Device)
    if _user.source == "demo":
        statement = statement.where(Device.source == "demo")
    devices = db.scalars(statement.order_by(Device.source == "demo", Device.updated_at.desc()).limit(100)).all()
    for device in devices:
        latest = (device.diagnostics or {}).get("latest_inference")
        if isinstance(latest, dict):
            age = (utc_now() - device.updated_at.replace(tzinfo=timezone.utc) if device.updated_at.tzinfo is None else utc_now() - device.updated_at).total_seconds()
            is_demo = bool(latest.get("demo") or device.source == "demo")
            return {"detection": {**latest, "device_id": device.id, "source": latest.get("source", device.source), "status": "DEMO ONLY" if is_demo else (latest.get("inference_status", "NO DATA") if age < 30 else "STALE"), "demo": is_demo, "stale": age >= 30, "updated_at": latest.get("processed_at") or latest.get("captured_at")}}
    if db.get(Device, "esp32-cam-01") is not None:
        demo = (db.get(Device, "esp32-cam-01").diagnostics or {}).get("latest_inference")
        if isinstance(demo, dict) and demo.get("demo"):
            return {"detection": {**demo, "device_id": "esp32-cam-01", "status": "DEMO ONLY", "source": "demo", "demo": True, "stale": False, "updated_at": demo.get("processed_at") or demo.get("captured_at")}}
    event = db.scalar(select(MlOriginEvent).options(joinedload(MlOriginEvent.alert)).order_by(MlOriginEvent.detected_at.desc(), MlOriginEvent.id).limit(1))
    if event is None:
        return {
            "detection": {
                "status": "NO ML DETECTION",
                "source": "none",
                "image_url": None,
                "frame_url": None,
                "class": None,
                "defect": None,
                "confidence": None,
                "severity": None,
                "boxes": [],
                "sensor_fusion": None,
                "fusion": None,
                "final_confidence": None,
                "updated_at": None,
                "demo": False,
            }
        }
    payload = event.payload.get("detection", event.payload)
    alert = event.alert
    return {
        "detection": {
            **payload,
            "status": "DETECTION RECORDED",
            "source": event.source_namespace,
            "image_url": alert.image_url if alert else None,
            "class": payload.get("class") or (alert.defect if alert else None),
            "defect": payload.get("defect") or (alert.defect if alert else None),
            "confidence": payload.get("confidence") if payload.get("confidence") is not None else (alert.confidence if alert else None),
            "severity": payload.get("severity") or (alert.severity if alert else None),
            "timestamp": _iso(event.detected_at),
            "updated_at": _iso(event.detected_at),
            "demo": bool(alert and alert.source == "demo"),
        }
    }
