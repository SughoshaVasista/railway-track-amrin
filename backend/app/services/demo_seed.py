"""Idempotent development-only sample records. No sample is live telemetry."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

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

DEMO_SOURCE = "demo"


def _add_if_missing(session: Session, model, public_id: str, **values) -> bool:
    if session.get(model, public_id) is not None:
        return False
    session.add(model(id=public_id, **values))
    return True


def seed_demo(session: Session) -> dict[str, int]:
    """Insert stable sample records once; caller owns the surrounding transaction."""
    counts: dict[str, int] = {}
    now = utc_now()

    counts["users"] = int(_add_if_missing(
        session,
        User,
        "worker-01",
        worker_id="worker-01",
        name="Maintenance Worker",
        email="worker-01@demo.invalid",
        username="worker-01",
        password_hash=None,
        role="worker",
        approval_status="approved",
        city="bengaluru",
        is_active=True,
        source=DEMO_SOURCE,
    ))
    counts["admin"] = int(_add_if_missing(
        session,
        User,
        "demo-admin",
        worker_id=None,
        name="Demo Administrator",
        email="demo-admin@demo.invalid",
        username=None,
        password_hash=None,
        role="admin",
        approval_status="approved",
        city=None,
        is_active=True,
        source=DEMO_SOURCE,
    ))
    # Do not seed a fake pending signup: approval queues should only contain
    # real registration requests. Retire the legacy placeholder on existing DBs.
    pending_demo_user = session.get(User, "demo-pending-worker")
    if pending_demo_user is not None:
        pending_demo_user.approval_status = "rejected"
        pending_demo_user.is_active = False
    counts["devices"] = int(_add_if_missing(
        session,
        Device,
        "device-01",
        name="AMRIN-DEMO-01",
        platform="Raspberry Pi 5 (demo record)",
        status="ONLINE",
        city="bengaluru",
        uptime="DEMO 3d 04h",
        network_status="ONLINE",
        pi_status="ONLINE",
        diagnostics={"source": DEMO_SOURCE, "checks": [{"name": "Demo sensor bus", "status": "PASS"}]},
        source=DEMO_SOURCE,
    ))
    counts["esp32_device"] = int(_add_if_missing(
        session, Device, "esp32-cam-01", name="ESP32 camera (demo)", platform="ESP32-CAM demo feed",
        status="ONLINE", city="bengaluru", uptime="SIMULATED DEMO", network_status="ONLINE",
        diagnostics={"source": DEMO_SOURCE, "simulated": True}, source=DEMO_SOURCE,
    ))
    sample_devices = {
        "device-01": ("AMRIN-DEMO-01", "Raspberry Pi 5 (demo record)"),
        "esp32-cam-01": ("ESP32 camera (demo)", "ESP32-CAM demo feed"),
    }
    for sample_id, (sample_name, sample_platform) in sample_devices.items():
        sample_device = session.get(Device, sample_id)
        if sample_device is not None:
            sample_device.name = sample_name
            sample_device.platform = sample_platform
            sample_device.status = "ONLINE"
            sample_device.city = "bengaluru"
            sample_device.network_status = "ONLINE"
            sample_device.source = DEMO_SOURCE
            if sample_id == "esp32-cam-01":
                sample_device.uptime = "SIMULATED DEMO"
                sample_device.diagnostics = {**(sample_device.diagnostics or {}), "source": DEMO_SOURCE, "simulated": True}
    counts["tracks"] = sum([
        _add_if_missing(session, Track, "track-a", name="Track A", status="OPEN", occupancy="CLEAR", max_speed="80 km/h", severity="S3", city="bengaluru", source=DEMO_SOURCE, geometry={"type": "LineString", "coordinates": [[77.5928, 12.9708], [77.5960, 12.9730], [77.5990, 12.9752]]}),
        _add_if_missing(session, Track, "track-b", name="Track B", status="OPEN", occupancy="OCCUPIED", max_speed="60 km/h", severity="S2", city="bengaluru", source=DEMO_SOURCE, geometry={"type": "LineString", "coordinates": [[77.5928, 12.9698], [77.5960, 12.9720], [77.5990, 12.9742]]}),
    ])
    counts["trains"] = int(_add_if_missing(
        session,
        Train,
        "train-demo-01",
        latitude=12.9713,
        longitude=77.5938,
        speed="42 km/h",
        destination="KSR Bengaluru",
        next_switch="switch-01",
        distance="680 m",
        gps_metadata={"accuracy": 3.1, "satellites": 8, "fix_type": "3D"},
        city="bengaluru",
        source=DEMO_SOURCE,
        measured_at=now,
    ))
    session.flush()

    # Replace only the old sample alert/task set. Live alerts, tasks, sensor
    # records, and other non-demo data are left untouched.
    old_demo_alerts = session.scalars(select(Alert).where(Alert.source == DEMO_SOURCE)).all()
    old_alert_ids = {alert.id for alert in old_demo_alerts}
    old_demo_tasks = session.scalars(
        select(MaintenanceTask).where(
            (MaintenanceTask.source == DEMO_SOURCE)
            | MaintenanceTask.alert_id.in_(old_alert_ids or {"__no_demo_alert__"})
        )
    ).all()
    old_task_ids = {task.id for task in old_demo_tasks}
    for task in old_demo_tasks:
        session.delete(task)
    session.flush()
    if old_alert_ids:
        for history in session.scalars(select(AlertHistory).where(AlertHistory.alert_id.in_(old_alert_ids))).all():
            session.delete(history)
        for inference_event in session.scalars(select(MlOriginEvent).where(MlOriginEvent.alert_id.in_(old_alert_ids))).all():
            inference_event.alert_id = None
        for event in session.scalars(select(EventLog).where(EventLog.object_id.in_(old_alert_ids | old_task_ids))).all():
            session.delete(event)
        for alert in old_demo_alerts:
            session.delete(alert)
        session.flush()
    for event_id in ("EVT-DEMO-002", "EVT-DEMO-ALERT-106", "EVT-DEMO-ALERT-107", "EVT-DEMO-ALERT-108", "EVT-DEMO-ALERT-109",
                     "EVT-DEMO-TASK-006", "EVT-DEMO-TASK-007", "EVT-DEMO-TASK-008", "EVT-DEMO-TASK-009"):
        stale_event = session.get(EventLog, event_id)
        if stale_event is not None:
            session.delete(stale_event)
    session.flush()

    alert_rows = [
        ("ALT-106", "Rail Crack", "S3", "ACKNOWLEDGED", "Track A", "KM 12/4", 12.9719, 77.5942, 0.96),
        ("ALT-107", "Rail Crack", "S2", "ACKNOWLEDGED", "Track B", "KM 13/2", 12.9732, 77.5961, 0.89),
        ("ALT-108", "Rail Crack", "S1", "ACKNOWLEDGED", "Track A", "KM 13/8", 12.9745, 77.5980, 0.82),
    ]
    counts["alerts"] = 0
    for index, (public_id, defect, severity, status, track, chainage, lat, lng, confidence) in enumerate(alert_rows):
        counts["alerts"] += int(_add_if_missing(
            session,
            Alert,
            public_id,
            defect=defect,
            severity=severity,
            status=status,
            confidence=confidence,
            track=track,
            chainage=chainage,
            latitude=lat,
            longitude=lng,
            gps_metadata={"accuracy": 3.0, "fix_type": "3D"},
            sensors=[
                {"name": "Camera", "status": "DEMO ONLY", "detection": "sample rail crack"},
                {"name": "Ultrasonic", "status": "DEMO ONLY"},
            ],
            source=DEMO_SOURCE,
            city="bengaluru",
            assigned_worker_user_id=None,
            detected_at=now - timedelta(minutes=5 * (index + 1)),
        ))
        sample_alert = session.get(Alert, public_id)
        if sample_alert is not None and sample_alert.source == DEMO_SOURCE:
            sample_alert.defect = defect
            sample_alert.severity = severity
            sample_alert.status = status
            sample_alert.confidence = confidence
            sample_alert.track = track
            sample_alert.chainage = chainage
            sample_alert.latitude = lat
            sample_alert.longitude = lng
            sample_alert.city = "bengaluru"
            sample_alert.assigned_worker_user_id = None
    session.flush()

    task_rows = [
        ("TASK-006", "ALT-106", "ASSIGNED", "S3", "Inspect and secure the cracked rail section."),
        ("TASK-007", "ALT-107", "ASSIGNED", "S2", "Inspect and repair the cracked rail section."),
        ("TASK-008", "ALT-108", "ASSIGNED", "S1", "Inspect and repair the cracked rail section."),
    ]
    counts["tasks"] = 0
    counts["alert_history"] = 0
    for task_id, alert_id, task_status, severity, notes in task_rows:
        session.add(MaintenanceTask(
            id=task_id,
            alert_id=alert_id,
            assigned_worker_user_id=None,
            status=task_status,
            priority=severity,
            admin_notes=notes,
            source=DEMO_SOURCE,
        ))
        counts["tasks"] += 1
        alert = session.get(Alert, alert_id)
        session.add(AlertHistory(
            id=f"HIST-DEMO-{task_id[-3:]}",
            alert_id=alert_id,
            actor_user_id="demo-admin",
            action="DEMO_TASK_ASSIGNED",
            old_status="ACKNOWLEDGED",
            new_status=alert.status if alert else "ASSIGNED",
            changes={"task_id": task_id, "source": DEMO_SOURCE},
            notes=notes,
            timestamp=now - timedelta(minutes=int(task_id[-1]) * 4),
            source=DEMO_SOURCE,
        ))
        counts["alert_history"] += 1
        session.add(EventLog(
            id=f"EVT-DEMO-TASK-{task_id[-3:]}",
            actor_user_id="demo-admin",
            action="demo_task_assigned",
            object_type="task",
            object_id=task_id,
            summary=f"DEMO: {task_id} assigned for {alert.defect if alert else 'track maintenance'} ({severity}).",
            details={"alert_id": alert_id, "severity": severity, "source": DEMO_SOURCE},
            source=DEMO_SOURCE,
            timestamp=now - timedelta(minutes=int(task_id[-1]) * 4),
        ))
    for alert_id, defect, severity, *_ in alert_rows:
        session.add(EventLog(
            id=f"EVT-DEMO-ALERT-{alert_id[-3:]}",
            actor_user_id=None,
            action="demo_alert_detected",
            object_type="alert",
            object_id=alert_id,
            summary=f"DEMO: {severity} {defect} detected on the track.",
            details={"severity": severity, "source": DEMO_SOURCE},
            source=DEMO_SOURCE,
            timestamp=now - timedelta(minutes=int(alert_id[-1]) * 5),
        ))
    seed_event = session.get(EventLog, "EVT-DEMO-001")
    if seed_event is not None:
        seed_event.summary = "Development sample data refreshed; alerts and tasks are simulated."
    counts["sensor_readings"] = 0
    sensor_rows = [
        {"name": "Camera", "status": "ONLINE", "text_value": "SIMULATED FRAME 18420", "interpreted_value": "SIMULATED demo camera heartbeat"},
        {"name": "Ultrasonic", "status": "ONLINE", "numeric_value": 18.4, "unit": "mm gap", "interpreted_value": "Demo gap reading"},
        {"name": "Accelerometer", "status": "DEGRADED", "numeric_value": 0.42, "x": 0.12, "y": 0.08, "z": 0.42, "vibration": "DEMO ABNORMAL", "anomaly_score": 0.72},
        {"name": "Temperature", "status": "ONLINE", "numeric_value": 34.6, "unit": "C", "interpreted_value": "Demo reading"},
        {"name": "GPS", "status": "ONLINE", "latitude": 12.9724, "longitude": 77.5950, "gps_accuracy": 2.8, "satellites": 8, "fix_type": "3D"},
    ]
    for sensor in sensor_rows:
        exists = session.scalar(select(SensorReading.id).where(
            SensorReading.device_id == "device-01",
            SensorReading.name == sensor["name"],
            SensorReading.source == DEMO_SOURCE,
        ).limit(1))
        if not exists:
            session.add(SensorReading(device_id="device-01", recorded_at=now, source=DEMO_SOURCE, **sensor))
            counts["sensor_readings"] += 1
    counts["decision_states"] = int(_add_if_missing(
        session,
        DecisionState,
        "demo-latest",
        status="READY",
        action="MAINTAIN",
        action_level="WARNING",
        train_id="train-demo-01",
        switch_id="switch-01",
        target_track="Track A",
        confidence=0.78,
        reason="Demo recommendation only; no hardware is controlled.",
        latitude=12.9720,
        longitude=77.5954,
        rules_checked=[
            {"rule": "Target track is not occupied", "passed": True},
            {"rule": "No S3 defect on target track", "passed": True},
            {"rule": "Switch mechanism is available", "passed": True},
            {"rule": "Train is not too close to switch", "passed": True},
        ],
        raw_scores={"A": 0.78, "B": 0.42},
        payload={"demo": True},
        source=DEMO_SOURCE,
    ))
    counts["event_log"] = int(_add_if_missing(
        session,
        EventLog,
        "EVT-DEMO-001",
        action="DEMO_SEED_CREATED",
        object_type="system",
        object_id="demo-seed",
        summary="Development sample data; not live telemetry.",
        details={"source": DEMO_SOURCE},
        source=DEMO_SOURCE,
        timestamp=now,
    ))
    counts["ai_demo_snapshot"] = 0
    device = session.get(Device, "esp32-cam-01")
    if device is not None:
        diagnostics = dict(device.diagnostics or {})
        if not isinstance(diagnostics.get("latest_inference"), dict):
            diagnostics["latest_inference"] = {
                "device_id": device.id, "camera_status": "CONNECTED", "inference_status": "DEMO_ONLY",
                "model_loaded": False, "model_name": "DEMO DATA", "model_version": "SIMULATED",
                "class_count": 1, "input_size": 960, "inference_ms": 0,
                "captured_at": now.isoformat(), "processed_at": now.isoformat(),
                "image_width": 640, "image_height": 480,
                "boxes": [{"class": "demo crack", "confidence": 0.82, "box": [160, 140, 390, 205], "severity": "S2"}],
                "source": DEMO_SOURCE, "demo": True, "image_url": None,
            }
            device.diagnostics = diagnostics
            counts["ai_demo_snapshot"] = 1
    counts["demo_history"] = 0
    if not session.scalar(select(EventLog.id).where(EventLog.source == DEMO_SOURCE, EventLog.id == "EVT-DEMO-003")):
        session.add(EventLog(id="EVT-DEMO-003", action="DEMO_TRAIN_PASSAGE", object_type="train", object_id="train-demo-01", summary="DEMO: Sample train passing Track A at 42 km/h.", details={"source": DEMO_SOURCE, "demo": True}, source=DEMO_SOURCE, timestamp=now - timedelta(minutes=8)))
        counts["demo_history"] += 1
    session.flush()
    return counts
