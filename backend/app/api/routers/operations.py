from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.errors import AppError
from app.models import Alert, AlertHistory, EventLog, MaintenanceTask, TaskEvidence, User
from app.models.entities import utc_now
from app.schemas.operations import (
    ActionNotes,
    AlertPriorityRequest,
    AssignAlertRequest,
    CreateTaskRequest,
    TaskReviewRequest,
    TaskStatusRequest,
)
from app.schemas.serializers import serialize_alert, serialize_alert_history, serialize_task, serialize_task_evidence
from app.security.dependencies import require_roles

router = APIRouter(prefix="/api", tags=["operations"])
admin_user = require_roles("admin")
any_user = require_roles("admin", "worker")

ALERT_OPEN_STATES = {"DETECTED", "VERIFIED", "ACKNOWLEDGED", "ASSIGNED", "UNDER_REPAIR", "ACTIVE", "REOPENED"}
ALERT_TRANSITIONS = {
    "DETECTED": {"VERIFIED", "ACKNOWLEDGED", "FALSE_POSITIVE"},
    "VERIFIED": {"ACKNOWLEDGED", "FALSE_POSITIVE"},
    "ACKNOWLEDGED": {"ASSIGNED", "FALSE_POSITIVE"},
    "ASSIGNED": {"UNDER_REPAIR", "FALSE_POSITIVE"},
    "UNDER_REPAIR": {"RESOLVED", "FALSE_POSITIVE"},
    "RESOLVED": {"REOPENED"},
    "FALSE_POSITIVE": {"REOPENED"},
    "REOPENED": {"VERIFIED", "ACKNOWLEDGED", "FALSE_POSITIVE"},
    "ACTIVE": {"VERIFIED", "ACKNOWLEDGED", "FALSE_POSITIVE"},
}
TASK_TRANSITIONS = {
    "ASSIGNED": {"ACCEPTED"},
    "ACCEPTED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"AWAITING_REVIEW"},
    "AWAITING_REVIEW": set(),
    "COMPLETED": set(),
}
IMAGE_TYPES = {
    "image/jpeg": ("jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": ("png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/gif": ("gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    "image/webp": ("webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
}


def _admin(user: User) -> bool:
    return user.role == "admin"


def _reject_demo_write(user: User) -> None:
    if user.source == "demo":
        raise AppError(403, "demo_read_only", "Demo data is read-only. No changes were saved.")


def _visible_task(task: MaintenanceTask, user: User) -> None:
    if not _admin(user) and task.assigned_worker_user_id != user.id:
        raise AppError(403, "forbidden", "This task is assigned to another worker")


def _get_alert(db: Session, alert_id: str, user: User | None = None) -> Alert:
    alert = db.scalar(
        select(Alert).options(joinedload(Alert.assigned_worker)).where(Alert.id == alert_id)
    )
    if alert is None:
        raise AppError(404, "alert_not_found", "Alert was not found")
    if user is not None and user.source == "demo" and alert.source != "demo":
        raise AppError(404, "alert_not_found", "Alert was not found")
    if user is not None and not _admin(user):
        if alert.assigned_worker_user_id != user.id and (not user.city or alert.city != user.city):
            raise AppError(404, "alert_not_found", "Alert was not found")
    return alert


def _get_task(db: Session, task_id: str, user: User | None = None) -> MaintenanceTask:
    task = db.scalar(
        select(MaintenanceTask)
        .options(
            selectinload(MaintenanceTask.alert).selectinload(Alert.history).joinedload(AlertHistory.actor),
            joinedload(MaintenanceTask.assigned_worker),
            joinedload(MaintenanceTask.evidence),
        )
        .where(MaintenanceTask.id == task_id)
    )
    if task is None:
        raise AppError(404, "task_not_found", "Task was not found")
    if user is not None and user.source == "demo" and task.source != "demo":
        raise AppError(404, "task_not_found", "Task was not found")
    return task


def _audit_alert_change(
    db: Session,
    alert: Alert,
    actor: User,
    action: str,
    new_status: str | None,
    notes: str | None = None,
    changes: dict | None = None,
) -> None:
    old_status = alert.status
    if new_status is not None:
        alert.status = new_status
    alert.updated_at = utc_now()
    db.add(AlertHistory(
        alert_id=alert.id,
        actor_user_id=actor.id,
        action=action,
        old_status=old_status,
        new_status=alert.status,
        changes=changes,
        notes=notes,
        source="api",
    ))
    db.add(EventLog(
        actor_user_id=actor.id,
        action=action,
        object_type="alert",
        object_id=alert.id,
        summary=f"{action.replace('_', ' ').capitalize()} alert {alert.id}",
        details={"old_status": old_status, "new_status": alert.status, **(changes or {})},
        source="api",
    ))


def _ensure_transition(alert: Alert, target: str) -> None:
    if target not in ALERT_TRANSITIONS.get(alert.status, set()):
        raise AppError(
            409,
            "invalid_alert_transition",
            f"Alert cannot move from {alert.status} to {target}",
            {"current_status": alert.status, "requested_status": target},
        )


def _resolve_worker(db: Session, worker_id: str) -> User:
    worker = db.scalar(
        select(User).where(
            or_(User.id == worker_id, User.worker_id == worker_id),
            User.role == "worker",
            User.approval_status == "approved",
            User.is_active.is_(True),
        )
    )
    if worker is None:
        raise AppError(404, "worker_not_found", "An approved active worker with that ID was not found")
    return worker


def _commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "operation_conflict", message) from exc


def _has_current_repair_evidence(task: MaintenanceTask) -> bool:
    repair_evidence = [item for item in task.evidence if item.evidence_type in {"repair", "after"}]
    if task.review_status == "REWORK" and task.review_requested_at is not None:
        return any(item.created_at > task.review_requested_at for item in repair_evidence)
    return bool(repair_evidence)


@router.get("/alerts")
def list_alerts(
    severity: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    track: str | None = None,
    defect_type: str | None = Query(default=None, alias="type"),
    city: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict]]:
    statement = select(Alert).options(joinedload(Alert.assigned_worker))
    if user.source == "demo":
        statement = statement.where(Alert.source == "demo")
    if not _admin(user):
        if user.city:
            statement = statement.where(or_(func.lower(Alert.city) == user.city.lower(), Alert.assigned_worker_user_id == user.id, Alert.source == "demo"))
        else:
            statement = statement.where(or_(Alert.assigned_worker_user_id == user.id, Alert.source == "demo"))
    elif user.source == "demo":
        statement = statement.where(Alert.source == "demo")
    if severity and severity.upper() not in {"ALL", "ANY"}:
        normalized = severity.upper()
        if normalized not in {"S1", "S2", "S3"}:
            raise AppError(422, "invalid_severity", "Severity must be S1, S2, or S3")
        statement = statement.where(Alert.severity == normalized)
    if status_filter and status_filter.upper() not in {"ALL", "ANY"}:
        normalized = status_filter.upper()
        if normalized not in ALERT_TRANSITIONS and normalized not in {"FALSE_POSITIVE", "RESOLVED"}:
            raise AppError(422, "invalid_status", "Alert status is not supported")
        statement = statement.where(Alert.status == normalized)
    if track:
        statement = statement.where(Alert.track.ilike(f"%{track.strip()}%"))
    if defect_type:
        statement = statement.where(Alert.defect.ilike(f"%{defect_type.strip()}%"))
    if city:
        statement = statement.where(or_(Alert.city.ilike(city.strip()), Alert.source == "demo"))
    if from_:
        statement = statement.where(Alert.detected_at >= from_)
    if to:
        statement = statement.where(Alert.detected_at <= to)
    rows = db.scalars(statement.order_by(Alert.detected_at.desc(), Alert.id).offset(offset).limit(limit)).unique().all()
    return {"items": [serialize_alert(alert) for alert in rows]}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, user: User = Depends(any_user), db: Session = Depends(get_db)) -> dict:
    return serialize_alert(_get_alert(db, alert_id, user))


@router.get("/alerts/{alert_id}/image")
def get_alert_image(
    alert_id: str,
    request: Request,
    user: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    alert = _get_alert(db, alert_id, user)
    if not alert.image_url:
        raise AppError(404, "alert_image_not_found", "This alert has no stored image")
    root = (Path(request.app.state.settings.upload_folder).resolve() / "ml-alerts").resolve()
    path = (root / f"{alert.id}.jpg").resolve()
    if path.parent != root or not path.is_file():
        raise AppError(404, "alert_image_not_found", "Alert image was not found")
    return FileResponse(path, media_type="image/jpeg", filename=f"{alert.id}.jpg")


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    body: ActionNotes | None = None,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    alert = _get_alert(db, alert_id)
    _ensure_transition(alert, "ACKNOWLEDGED")
    _audit_alert_change(db, alert, actor, "alert_acknowledged", "ACKNOWLEDGED", body.notes if body else None)
    _commit_or_conflict(db, "Alert could not be acknowledged")
    return serialize_alert(_get_alert(db, alert_id))


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    body: ActionNotes | None = None,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    alert = _get_alert(db, alert_id)
    _ensure_transition(alert, "RESOLVED")
    _audit_alert_change(db, alert, actor, "alert_resolved", "RESOLVED", body.notes if body else None)
    _commit_or_conflict(db, "Alert could not be resolved")
    return serialize_alert(_get_alert(db, alert_id))


@router.post("/alerts/{alert_id}/false-positive")
def false_positive_alert(
    alert_id: str,
    body: ActionNotes | None = None,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    alert = _get_alert(db, alert_id)
    _ensure_transition(alert, "FALSE_POSITIVE")
    _audit_alert_change(db, alert, actor, "alert_marked_false_positive", "FALSE_POSITIVE", body.notes if body else None)
    _commit_or_conflict(db, "Alert could not be marked as a false positive")
    return serialize_alert(_get_alert(db, alert_id))


@router.post("/alerts/{alert_id}/assign")
def assign_alert(
    alert_id: str,
    body: AssignAlertRequest,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    alert = _get_alert(db, alert_id)
    worker = _resolve_worker(db, body.worker_id)
    if alert.status == "ACKNOWLEDGED":
        _ensure_transition(alert, "ASSIGNED")
    elif alert.status == "ASSIGNED":
        pass
    else:
        raise AppError(409, "invalid_alert_transition", "Only acknowledged or assigned alerts can be assigned")
    previous_worker = alert.assigned_worker_user_id
    alert.assigned_worker = worker
    open_task = db.scalar(
        select(MaintenanceTask).where(
            MaintenanceTask.alert_id == alert.id,
            MaintenanceTask.status != "COMPLETED",
        )
    )
    if open_task is not None:
        open_task.assigned_worker_user_id = worker.id
        open_task.updated_at = utc_now()
    _audit_alert_change(
        db, alert, actor, "alert_assigned", "ASSIGNED", body.notes,
        {
            "assigned_worker_user_id": {"old": previous_worker, "new": worker.id},
            "worker_id": worker.worker_id,
            **({"task_id": open_task.id} if open_task else {}),
        },
    )
    _commit_or_conflict(db, "Alert assignment conflicts with an existing record")
    return serialize_alert(_get_alert(db, alert_id))


@router.post("/alerts/{alert_id}/priority")
def change_alert_priority(
    alert_id: str,
    body: AlertPriorityRequest,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    alert = _get_alert(db, alert_id)
    if alert.status not in ALERT_OPEN_STATES:
        raise AppError(409, "invalid_alert_transition", "Priority cannot be changed on a closed alert")
    previous = alert.severity
    alert.severity = body.severity
    _audit_alert_change(db, alert, actor, "alert_priority_changed", None, changes={"severity": {"old": previous, "new": body.severity}})
    _commit_or_conflict(db, "Alert priority could not be changed")
    return serialize_alert(_get_alert(db, alert_id))


@router.get("/alerts/{alert_id}/history")
def get_alert_history(
    alert_id: str,
    user: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict]]:
    _get_alert(db, alert_id, user)
    entries = db.scalars(
        select(AlertHistory)
        .options(joinedload(AlertHistory.actor))
        .where(AlertHistory.alert_id == alert_id)
        .order_by(AlertHistory.timestamp.desc(), AlertHistory.id.desc())
        .limit(200)
    ).unique().all()
    return {"items": [serialize_alert_history(entry) for entry in entries]}


@router.get("/tasks")
def list_tasks(
    worker_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict]]:
    statement = select(MaintenanceTask).options(
        selectinload(MaintenanceTask.alert).selectinload(Alert.history).joinedload(AlertHistory.actor),
        joinedload(MaintenanceTask.assigned_worker),
        joinedload(MaintenanceTask.evidence),
    )
    if not _admin(user):
        statement = statement.where(MaintenanceTask.assigned_worker_user_id == user.id)
        if user.source == "demo":
            statement = statement.where(MaintenanceTask.source == "demo")
    elif user.source == "demo":
        statement = statement.where(MaintenanceTask.source == "demo")
    elif worker_id:
        worker = db.scalar(select(User).where(or_(User.id == worker_id, User.worker_id == worker_id)))
        if worker is None:
            return {"items": []}
        statement = statement.where(MaintenanceTask.assigned_worker_user_id == worker.id)
    if status_filter and status_filter.upper() != "ALL":
        normalized = status_filter.upper()
        if normalized not in TASK_TRANSITIONS:
            raise AppError(422, "invalid_task_status", "Task status is not supported")
        statement = statement.where(MaintenanceTask.status == normalized)
    rows = db.scalars(statement.order_by(MaintenanceTask.created_at.desc(), MaintenanceTask.id).offset(offset).limit(limit)).unique().all()
    return {"items": [serialize_task(task) for task in rows]}


def _create_task(db: Session, alert: Alert, worker: User, actor: User, notes: str | None) -> MaintenanceTask:
    if alert.status not in {"ACKNOWLEDGED", "ASSIGNED"}:
        raise AppError(409, "invalid_alert_transition", "Only acknowledged or assigned alerts can receive a maintenance task")
    existing = db.scalar(
        select(MaintenanceTask.id).where(
            MaintenanceTask.alert_id == alert.id,
            MaintenanceTask.status != "COMPLETED",
        )
    )
    if existing:
        raise AppError(409, "open_task_exists", "This alert already has an open maintenance task")
    task = MaintenanceTask(
        id=f"TASK-{uuid4().hex[:12].upper()}",
        alert=alert,
        assigned_worker=worker,
        status="ASSIGNED",
        priority=alert.severity,
        admin_notes=notes,
        source="api",
    )
    db.add(task)
    previous_worker = alert.assigned_worker_user_id
    alert.assigned_worker = worker
    _audit_alert_change(
        db, alert, actor, "maintenance_task_assigned", "ASSIGNED", notes,
        {"task_id": task.id, "assigned_worker_user_id": {"old": previous_worker, "new": worker.id}, "worker_id": worker.worker_id},
    )
    return task


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    body: CreateTaskRequest,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    alert = _get_alert(db, body.alert_id)
    worker = _resolve_worker(db, body.worker_id)
    task = _create_task(db, alert, worker, actor, body.notes)
    _commit_or_conflict(db, "A task for this alert already exists")
    return serialize_task(_get_task(db, task.id))


@router.post("/tasks/{task_id}/assignment")
def assign_existing_task(
    task_id: str,
    body: AssignAlertRequest,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    task = _get_task(db, task_id, actor)
    if task.status != "ASSIGNED":
        raise AppError(409, "task_already_started", "Only tasks that have not been accepted can be reassigned")
    worker = _resolve_worker(db, body.worker_id)
    if (task.source == "demo") != (worker.source == "demo"):
        raise AppError(404, "worker_not_found", "Choose an active worker from the same data set as this task")
    previous_worker_id = task.assigned_worker_user_id
    previous_alert_status = task.alert.status
    task.assigned_worker = worker
    task.updated_at = utc_now()
    task.alert.assigned_worker = worker
    if task.alert.status == "ACKNOWLEDGED":
        task.alert.status = "ASSIGNED"
    task.alert.updated_at = utc_now()
    db.add(AlertHistory(
        alert_id=task.alert_id,
        actor_user_id=actor.id,
        action="maintenance_task_reassigned",
        old_status=previous_alert_status,
        new_status=task.alert.status,
        changes={"task_id": task.id, "assigned_worker_user_id": {"old": previous_worker_id, "new": worker.id}, "worker_id": worker.worker_id},
        notes=body.notes,
        source="api",
    ))
    db.add(EventLog(
        actor_user_id=actor.id,
        action="maintenance_task_reassigned",
        object_type="task",
        object_id=task.id,
        summary=f"Task {task.id} assigned to {worker.worker_id}",
        details={"previous_worker_user_id": previous_worker_id, "worker_user_id": worker.id, "alert_id": task.alert_id},
        source="api",
    ))
    _commit_or_conflict(db, "Task assignment could not be saved")
    return serialize_task(_get_task(db, task.id))


@router.delete("/tasks/{task_id}/assignment")
def unassign_task(
    task_id: str,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    task = _get_task(db, task_id, actor)
    if task.status != "ASSIGNED":
        raise AppError(409, "task_already_started", "Only tasks that have not been accepted can be unassigned")
    if task.assigned_worker_user_id is None:
        return serialize_task(task)
    previous_worker_id = task.assigned_worker_user_id
    task.assigned_worker = None
    task.updated_at = utc_now()
    task.alert.assigned_worker = None
    if task.alert.status == "ASSIGNED":
        task.alert.status = "ACKNOWLEDGED"
    task.alert.updated_at = utc_now()
    db.add(AlertHistory(
        alert_id=task.alert_id,
        actor_user_id=actor.id,
        action="maintenance_task_unassigned",
        old_status="ASSIGNED",
        new_status=task.alert.status,
        changes={"task_id": task.id, "assigned_worker_user_id": {"old": previous_worker_id, "new": None}},
        source="api",
    ))
    db.add(EventLog(
        actor_user_id=actor.id,
        action="maintenance_task_unassigned",
        object_type="task",
        object_id=task.id,
        summary=f"Task {task.id} unassigned",
        details={"previous_worker_user_id": previous_worker_id, "alert_id": task.alert_id},
        source="api",
    ))
    _commit_or_conflict(db, "Task could not be unassigned")
    return serialize_task(_get_task(db, task.id))


@router.put("/tasks/{task_id}/status")
def update_task_status(
    task_id: str,
    body: TaskStatusRequest,
    actor: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    task = _get_task(db, task_id)
    _visible_task(task, actor)
    if body.status == "COMPLETED":
        raise AppError(409, "admin_review_required", "A task can only be completed after an administrator approves it")
    if body.status not in TASK_TRANSITIONS.get(task.status, set()):
        raise AppError(
            409,
            "invalid_task_transition",
            f"Task cannot move from {task.status} to {body.status}",
            {"current_status": task.status, "requested_status": body.status},
        )
    old_task_status = task.status
    task.status = body.status
    task.updated_at = utc_now()
    previous_alert_status = task.alert.status
    next_alert_status = "UNDER_REPAIR" if body.status == "IN_PROGRESS" else None
    if next_alert_status and task.alert.status != next_alert_status:
        _ensure_transition(task.alert, next_alert_status)
        _audit_alert_change(
            db, task.alert, actor, "task_status_changed", next_alert_status, body.notes,
            {"task_id": task.id, "task_status": {"old": old_task_status, "new": body.status}},
        )
    else:
        db.add(AlertHistory(
            alert_id=task.alert_id,
            actor_user_id=actor.id,
            action="task_status_changed",
            old_status=previous_alert_status,
            new_status=previous_alert_status,
            changes={"task_id": task.id, "task_status": {"old": old_task_status, "new": body.status}},
            notes=body.notes,
            source="api",
        ))
        task.alert.updated_at = utc_now()
    db.add(EventLog(
        actor_user_id=actor.id,
        action="task_status_changed",
        object_type="task",
        object_id=task.id,
        summary=f"Task {task.id} moved to {body.status}",
        details={"old_status": old_task_status, "new_status": body.status, "alert_id": task.alert_id},
        source="api",
    ))
    _commit_or_conflict(db, "Task status conflicts with current alert state")
    return serialize_task(_get_task(db, task_id))


@router.post("/tasks/{task_id}/submit")
def submit_task_for_review(
    task_id: str,
    body: ActionNotes | None = None,
    actor: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    task = _get_task(db, task_id)
    _visible_task(task, actor)
    if actor.role != "worker":
        raise AppError(403, "worker_action_required", "Only the assigned worker can submit work for review")
    if task.status != "IN_PROGRESS":
        raise AppError(409, "invalid_task_transition", "Only in-progress work can be submitted for review")
    if not _has_current_repair_evidence(task):
        raise AppError(409, "repair_evidence_required", "Upload a repair or after photo before requesting review")

    task.status = "AWAITING_REVIEW"
    task.review_status = "PENDING"
    task.review_notes = None
    task.review_requested_at = None
    task.updated_at = utc_now()
    task.alert.updated_at = utc_now()
    db.add(AlertHistory(
        alert_id=task.alert_id,
        actor_user_id=actor.id,
        action="maintenance_task_submitted_for_review",
        old_status=task.alert.status,
        new_status=task.alert.status,
        changes={"task_id": task.id, "task_status": {"old": "IN_PROGRESS", "new": "AWAITING_REVIEW"}},
        notes=body.notes if body else None,
        source="api",
    ))
    db.add(EventLog(
        actor_user_id=actor.id,
        action="maintenance_task_submitted_for_review",
        object_type="task",
        object_id=task.id,
        summary=f"Task {task.id} submitted for official review",
        details={"alert_id": task.alert_id, "worker_user_id": actor.id},
        source="api",
    ))
    _commit_or_conflict(db, "Task could not be submitted for review")
    return serialize_task(_get_task(db, task_id))


@router.post("/tasks/{task_id}/review")
def review_task(
    task_id: str,
    body: TaskReviewRequest,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    task = _get_task(db, task_id)
    if task.status != "AWAITING_REVIEW":
        raise AppError(409, "task_not_awaiting_review", "Only submitted tasks can be reviewed")
    notes = (body.notes or "").strip()
    if body.decision == "request_changes" and not notes:
        raise AppError(422, "review_notes_required", "Add instructions describing the work still needed")

    previous_alert_status = task.alert.status
    old_status = task.status
    if body.decision == "approve":
        if not _has_current_repair_evidence(task):
            raise AppError(409, "repair_evidence_required", "Repair evidence is required before approval")
        _ensure_transition(task.alert, "RESOLVED")
        task.status = "COMPLETED"
        task.review_status = "APPROVED"
        action = "maintenance_task_approved"
        task.alert.status = "RESOLVED"
    else:
        task.status = "IN_PROGRESS"
        task.review_status = "REWORK"
        task.review_notes = notes
        task.review_requested_at = utc_now()
        action = "maintenance_task_changes_requested"

    task.updated_at = utc_now()
    task.alert.updated_at = utc_now()
    db.add(AlertHistory(
        alert_id=task.alert_id,
        actor_user_id=actor.id,
        action=action,
        old_status=previous_alert_status,
        new_status=task.alert.status,
        changes={"task_id": task.id, "task_status": {"old": old_status, "new": task.status}, "review_status": task.review_status},
        notes=notes or None,
        source="api",
    ))
    db.add(EventLog(
        actor_user_id=actor.id,
        action=action,
        object_type="task",
        object_id=task.id,
        summary=f"Task {task.id} {'approved as finished' if body.decision == 'approve' else 'returned for more work'}",
        details={"alert_id": task.alert_id, "worker_user_id": task.assigned_worker_user_id, "task_status": task.status, "review_status": task.review_status},
        source="api",
    ))
    _commit_or_conflict(db, "Task review could not be saved")
    return serialize_task(_get_task(db, task_id))


@router.post("/tasks/{task_id}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_task_evidence(
    task_id: str,
    request: Request,
    file: UploadFile = File(...),
    notes: str | None = Form(default=None, max_length=4000),
    evidence_type: str = Form(default="repair"),
    actor: User = Depends(require_roles("worker")),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(actor)
    task = _get_task(db, task_id)
    _visible_task(task, actor)
    if task.status != "IN_PROGRESS":
        raise AppError(409, "invalid_task_transition", "Evidence can only be uploaded while a task is in progress")
    if evidence_type not in {"before", "after", "repair", "other"}:
        raise AppError(422, "invalid_evidence_type", "Evidence type must be before, after, repair, or other")
    mime_type = (file.content_type or "").lower().split(";", 1)[0].strip()
    if mime_type not in IMAGE_TYPES:
        raise AppError(415, "unsupported_media_type", "Evidence must be a JPEG, PNG, GIF, or WebP image")
    max_bytes = request.app.state.settings.max_content_length
    content = await file.read(max_bytes + 1)
    if not content:
        raise AppError(400, "empty_upload", "Evidence image is empty")
    if len(content) > max_bytes:
        raise AppError(413, "upload_too_large", f"Evidence image exceeds the {max_bytes}-byte limit")
    extension, signature_check = IMAGE_TYPES[mime_type]
    if not signature_check(content):
        raise AppError(415, "invalid_image_content", "The uploaded file does not match its image content type")

    upload_root = Path(request.app.state.settings.upload_folder).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}.{extension}"
    destination = upload_root / stored_filename
    original_filename = Path(file.filename or "evidence").name[:255]
    destination.write_bytes(content)
    evidence = TaskEvidence(
        task_id=task.id,
        stored_filename=stored_filename,
        original_filename=original_filename,
        mime_type=mime_type,
        byte_size=len(content),
        evidence_type=evidence_type,
        notes=notes,
        uploaded_by_user_id=actor.id,
    )
    db.add(evidence)
    db.add(EventLog(
        actor_user_id=actor.id,
        action="task_evidence_uploaded",
        object_type="task",
        object_id=task.id,
        summary=f"Evidence uploaded for task {task.id}",
        details={"evidence_type": evidence_type, "mime_type": mime_type, "byte_size": len(content)},
        source="api",
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    db.refresh(evidence)
    return serialize_task_evidence(evidence)


@router.get("/tasks/{task_id}/evidence/{evidence_id}")
def get_task_evidence_file(
    task_id: str,
    evidence_id: str,
    request: Request,
    actor: User = Depends(any_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    task = _get_task(db, task_id, actor)
    _visible_task(task, actor)
    evidence = db.scalar(
        select(TaskEvidence).where(TaskEvidence.id == evidence_id, TaskEvidence.task_id == task_id)
    )
    if evidence is None:
        raise AppError(404, "evidence_not_found", "Evidence was not found")
    filename = Path(evidence.stored_filename)
    if filename.name != evidence.stored_filename:
        raise AppError(404, "evidence_not_found", "Evidence was not found")
    upload_root = Path(request.app.state.settings.upload_folder).resolve()
    path = (upload_root / filename.name).resolve()
    if path.parent != upload_root or not path.is_file():
        raise AppError(404, "evidence_not_found", "Evidence file is unavailable")
    return FileResponse(
        path,
        media_type=evidence.mime_type,
        filename=evidence.original_filename or "evidence",
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )
