from datetime import datetime, timezone
from typing import Any

from app.models import (
    Alert,
    AlertHistory,
    DecisionState,
    Device,
    EventLog,
    MaintenanceTask,
    SensorReading,
    TaskEvidence,
    Track,
    Train,
    User,
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_user(user: User) -> dict[str, Any]:
    """Serialize public account data without exposing password_hash."""
    return {
        "id": user.id,
        "worker_id": user.worker_id,
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "approval_status": user.approval_status,
        "status": "ACTIVE" if user.is_active else "INACTIVE",
        "city": user.city,
        "source": user.source,
        "created_at": _iso(user.created_at),
        "updated_at": _iso(user.updated_at),
    }


def serialize_alert(alert: Alert) -> dict[str, Any]:
    gps = dict(alert.gps_metadata or {})
    if alert.latitude is not None:
        gps["lat"] = alert.latitude
    if alert.longitude is not None:
        gps["lng"] = alert.longitude
    return {
        "id": alert.id,
        "defect": alert.defect,
        "type": alert.defect,
        "severity": alert.severity,
        "priority": alert.severity,
        "confidence": alert.confidence,
        "status": alert.status,
        "track": alert.track,
        "chainage": alert.chainage,
        "latitude": alert.latitude,
        "longitude": alert.longitude,
        "gps": gps or None,
        "gps_accuracy": gps.get("accuracy"),
        "sensors": alert.sensors,
        "image_url": alert.image_url,
        "city": alert.city,
        "assigned_worker_id": alert.assigned_worker.worker_id if alert.assigned_worker else None,
        "source": alert.source,
        "demo": alert.source == "demo",
        "source_event_id": alert.source_event_id,
        "detected_at": _iso(alert.detected_at),
        "created_at": _iso(alert.created_at),
        "updated_at": _iso(alert.updated_at),
    }


def serialize_alert_history(item: AlertHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "alert_id": item.alert_id,
        "actor": item.actor.name if item.actor else "SYSTEM",
        "actor_user_id": item.actor_user_id,
        "action": item.action,
        "old_status": item.old_status,
        "new_status": item.new_status,
        "changes": item.changes,
        "notes": item.notes,
        "source": item.source,
        "timestamp": _iso(item.timestamp),
    }


def serialize_device(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "platform": device.platform,
        "status": device.status,
        "city": device.city,
        "uptime": device.uptime,
        "network_status": device.network_status,
        "pi_status": device.pi_status,
        "diagnostics": device.diagnostics,
        "source": device.source,
        "demo": device.source == "demo",
        "created_at": _iso(device.created_at),
        "updated_at": _iso(device.updated_at),
    }


def serialize_sensor_reading(reading: SensorReading) -> dict[str, Any]:
    if reading.numeric_value is not None:
        value: Any = reading.numeric_value
    elif reading.text_value is not None:
        value = reading.text_value
    else:
        value = reading.structured_value
    return {
        "id": reading.id,
        "device_id": reading.device_id,
        "name": reading.name,
        "status": reading.status,
        "value": value,
        "reading": value,
        "raw": value,
        "unit": reading.unit,
        "interpreted": reading.interpreted_value,
        "interpreted_value": reading.interpreted_value,
        "x": reading.x,
        "y": reading.y,
        "z": reading.z,
        "vibration": reading.vibration,
        "anomaly_score": reading.anomaly_score,
        "lat": reading.latitude,
        "lng": reading.longitude,
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "accuracy": reading.gps_accuracy,
        "satellites": reading.satellites,
        "fix_type": reading.fix_type,
        "timestamp": _iso(reading.recorded_at),
        "updated_at": _iso(reading.recorded_at),
        "source": reading.source,
        "demo": reading.source == "demo",
    }


def serialize_task_evidence(evidence: TaskEvidence) -> dict[str, Any]:
    return {
        "id": evidence.id,
        "task_id": evidence.task_id,
        "filename": evidence.stored_filename,
        "original_filename": evidence.original_filename,
        "mime_type": evidence.mime_type,
        "byte_size": evidence.byte_size,
        "evidence_type": evidence.evidence_type,
        "notes": evidence.notes,
        "uploaded_by_user_id": evidence.uploaded_by_user_id,
        "url": f"/api/tasks/{evidence.task_id}/evidence/{evidence.id}",
        "created_at": _iso(evidence.created_at),
    }


def serialize_task(task: MaintenanceTask) -> dict[str, Any]:
    alert = task.alert
    worker = task.assigned_worker
    review_actions = {
        "maintenance_task_submitted_for_review",
        "maintenance_task_approved",
        "maintenance_task_changes_requested",
    }
    review_history = [
        {
            "action": entry.action,
            "actor": entry.actor.name if entry.actor else "OFFICIAL",
            "notes": entry.notes,
            "timestamp": _iso(entry.timestamp),
        }
        for entry in alert.history
        if entry.action in review_actions and (entry.changes or {}).get("task_id") == task.id
    ]
    gps = dict(alert.gps_metadata or {})
    if alert.latitude is not None:
        gps["lat"] = alert.latitude
    if alert.longitude is not None:
        gps["lng"] = alert.longitude
    return {
        "id": task.id,
        "alert_id": task.alert_id,
        "worker_id": worker.worker_id if worker else None,
        "worker": {"id": worker.id, "worker_id": worker.worker_id, "name": worker.name, "email": worker.email, "city": worker.city} if worker else None,
        "status": task.status,
        "review_status": task.review_status,
        "review_notes": task.review_notes,
        "review_requested_at": _iso(task.review_requested_at),
        "review_history": review_history,
        "priority": task.priority or alert.severity,
        "severity": alert.severity,
        "defect": alert.defect,
        "type": alert.defect,
        "track": alert.track,
        "chainage": alert.chainage,
        "gps": gps or None,
        "image_url": alert.image_url,
        "thumbnail": alert.image_url,
        "sensors": alert.sensors,
        "notes": task.admin_notes,
        "admin_notes": task.admin_notes,
        "city": alert.city or (worker.city if worker else None),
        "source": task.source,
        "demo": task.source == "demo" or alert.source == "demo",
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "evidence": [serialize_task_evidence(item) for item in task.evidence],
    }


def serialize_track(track: Track) -> dict[str, Any]:
    return {
        "id": track.id,
        "name": track.name,
        "status": track.status,
        "occupancy": track.occupancy,
        "max_speed": track.max_speed,
        "severity": track.severity,
        "geometry": track.geometry,
        "city": track.city,
        "source": track.source,
        "demo": track.source == "demo",
        "created_at": _iso(track.created_at),
        "updated_at": _iso(track.updated_at),
    }


def serialize_train(train: Train) -> dict[str, Any]:
    gps = dict(train.gps_metadata or {})
    return {
        "id": train.id,
        "latitude": train.latitude,
        "longitude": train.longitude,
        "speed": train.speed,
        "destination": train.destination,
        "next_switch": train.next_switch,
        "distance": train.distance,
        "gps": gps or None,
        "city": train.city,
        "source": train.source,
        "demo": train.source == "demo",
        "measured_at": _iso(train.measured_at),
        "updated_at": _iso(train.updated_at),
    }


def serialize_decision(state: DecisionState) -> dict[str, Any]:
    payload = state.payload or {}
    return {
        "id": state.id,
        "status": state.status,
        "action": state.action,
        "action_level": state.action_level,
        "train_id": state.train_id or payload.get("train_id"),
        "switch_id": state.switch_id,
        "target_track": state.target_track,
        "confidence": state.confidence,
        "reason": state.reason,
        "latitude": state.latitude,
        "longitude": state.longitude,
        "rules_checked": state.rules_checked or [],
        "raw_scores": state.raw_scores or {},
        "payload": payload,
        "source": state.source,
        "demo": state.source == "demo",
        "updated_at": _iso(state.updated_at),
    }


def serialize_event_log(item: EventLog) -> dict[str, Any]:
    return {
        "id": item.id,
        "actor_user_id": item.actor_user_id,
        "action": item.action,
        "object_type": item.object_type,
        "object_id": item.object_id,
        "summary": item.summary,
        "message": item.summary,
        "actor": item.actor.name if item.actor else "SYSTEM",
        "details": item.details,
        "source": item.source,
        "demo": item.source == "demo",
        "timestamp": _iso(item.timestamp),
    }
