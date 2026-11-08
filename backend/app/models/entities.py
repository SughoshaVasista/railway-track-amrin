from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def event_id() -> str:
    return f"EVT-{uuid4().hex}"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'worker')", name="ck_users_role"),
        CheckConstraint("approval_status IN ('pending', 'approved', 'rejected')", name="ck_users_approval_status"),
        Index("ix_users_city_role_status", "city", "role", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(16), default="worker", nullable=False)
    approval_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)

    assigned_alerts: Mapped[list["Alert"]] = relationship(back_populates="assigned_worker")
    assigned_tasks: Mapped[list["MaintenanceTask"]] = relationship(back_populates="assigned_worker")
    uploaded_evidence: Mapped[list["TaskEvidence"]] = relationship(back_populates="uploaded_by")
    alert_history: Mapped[list["AlertHistory"]] = relationship(back_populates="actor")
    events: Mapped[list["EventLog"]] = relationship(back_populates="actor")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('S1', 'S2', 'S3')", name="ck_alerts_severity"),
        CheckConstraint(
            "status IN ('DETECTED', 'VERIFIED', 'ACKNOWLEDGED', 'ASSIGNED', 'UNDER_REPAIR', 'RESOLVED', 'FALSE_POSITIVE', 'REOPENED', 'ACTIVE')",
            name="ck_alerts_status",
        ),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_alerts_confidence_range"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_alerts_latitude_range"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_alerts_longitude_range"),
        UniqueConstraint("source", "source_event_id", name="uq_alerts_source_event"),
        Index("ix_alerts_status_severity_created", "status", "severity", "created_at"),
        Index("ix_alerts_city_status", "city", "status"),
        Index("ix_alerts_track_chainage", "track", "chainage"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    defect: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DETECTED", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    track: Mapped[str | None] = mapped_column(String(80))
    chainage: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    gps_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sensors: Mapped[list[Any] | dict[str, Any] | None] = mapped_column(JSON)
    image_url: Mapped[str | None] = mapped_column(String(1024))
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False, index=True)
    source_event_id: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    assigned_worker_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    assigned_worker: Mapped[User | None] = relationship(back_populates="assigned_alerts")
    history: Mapped[list["AlertHistory"]] = relationship(back_populates="alert", cascade="all, delete-orphan", order_by="AlertHistory.timestamp")
    tasks: Mapped[list["MaintenanceTask"]] = relationship(back_populates="alert")
    ml_events: Mapped[list["MlOriginEvent"]] = relationship(back_populates="alert")


class AlertHistory(Base):
    __tablename__ = "alert_history"
    __table_args__ = (Index("ix_alert_history_alert_time", "alert_id", "timestamp"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=event_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str | None] = mapped_column(String(24))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    alert: Mapped[Alert] = relationship(back_populates="history")
    actor: Mapped[User | None] = relationship(back_populates="alert_history")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("status IN ('ONLINE', 'DEGRADED', 'OFFLINE', 'ERROR', 'UNKNOWN')", name="ck_devices_status"),
        Index("ix_devices_city_status", "city", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="UNKNOWN", nullable=False)
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    uptime: Mapped[str | None] = mapped_column(String(80))
    network_status: Mapped[str | None] = mapped_column(String(24))
    pi_status: Mapped[str | None] = mapped_column(String(24))
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)

    readings: Mapped[list["SensorReading"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    ml_events: Mapped[list["MlOriginEvent"]] = relationship(back_populates="device")


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_readings_device_name_time", "device_id", "name", "recorded_at"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_sensor_readings_latitude_range"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_sensor_readings_longitude_range"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=event_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", nullable=False)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    text_value: Mapped[str | None] = mapped_column(String(256))
    structured_value: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32))
    interpreted_value: Mapped[str | None] = mapped_column(String(256))
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)
    vibration: Mapped[str | None] = mapped_column(String(32))
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    gps_accuracy: Mapped[float | None] = mapped_column(Float)
    satellites: Mapped[int | None] = mapped_column(Integer)
    fix_type: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    device: Mapped[Device] = relationship(back_populates="readings")


class MaintenanceTask(TimestampMixin, Base):
    __tablename__ = "maintenance_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('ASSIGNED', 'ACCEPTED', 'IN_PROGRESS', 'AWAITING_REVIEW', 'COMPLETED')", name="ck_tasks_status"),
        CheckConstraint("priority IS NULL OR priority IN ('S1', 'S2', 'S3')", name="ck_tasks_priority"),
        Index("ix_tasks_worker_status", "assigned_worker_user_id", "status"),
        Index("ix_tasks_alert_status", "alert_id", "status"),
        Index(
            "uq_maintenance_tasks_alert_open",
            "alert_id",
            unique=True,
            sqlite_where=text("status != 'COMPLETED'"),
            postgresql_where=text("status != 'COMPLETED'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False)
    assigned_worker_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ASSIGNED", nullable=False)
    priority: Mapped[str | None] = mapped_column(String(2))
    admin_notes: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str | None] = mapped_column(String(24))
    review_notes: Mapped[str | None] = mapped_column(Text)
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)

    alert: Mapped[Alert] = relationship(back_populates="tasks")
    assigned_worker: Mapped[User] = relationship(back_populates="assigned_tasks")
    evidence: Mapped[list["TaskEvidence"]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="TaskEvidence.created_at")


class TaskEvidence(Base):
    __tablename__ = "task_evidence"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="ck_task_evidence_byte_size_positive"),
        CheckConstraint("evidence_type IN ('before', 'after', 'repair', 'other')", name="ck_task_evidence_type"),
        Index("ix_task_evidence_task_created", "task_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=event_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(16), default="repair", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    task: Mapped[MaintenanceTask] = relationship(back_populates="evidence")
    uploaded_by: Mapped[User | None] = relationship(back_populates="uploaded_evidence")


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint("severity IS NULL OR severity IN ('S1', 'S2', 'S3')", name="ck_tracks_severity"),
        CheckConstraint("occupancy IN ('CLEAR', 'OCCUPIED', 'UNKNOWN')", name="ck_tracks_occupancy"),
        Index("ix_tracks_city_status", "city", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", nullable=False)
    occupancy: Mapped[str] = mapped_column(String(16), default="UNKNOWN", nullable=False)
    max_speed: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str | None] = mapped_column(String(2))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Train(Base):
    __tablename__ = "trains"
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_trains_latitude_range"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_trains_longitude_range"),
        Index("ix_trains_city_updated", "city", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    speed: Mapped[str | None] = mapped_column(String(32))
    destination: Mapped[str | None] = mapped_column(String(160))
    next_switch: Mapped[str | None] = mapped_column(String(64))
    distance: Mapped[str | None] = mapped_column(String(32))
    gps_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    decisions: Mapped[list["DecisionState"]] = relationship(back_populates="train")


class DecisionState(Base):
    __tablename__ = "decision_states"
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_decisions_confidence_range"),
        Index("ix_decisions_updated", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str | None] = mapped_column(String(32))
    action_level: Mapped[str | None] = mapped_column(String(32))
    train_id: Mapped[str | None] = mapped_column(ForeignKey("trains.id", ondelete="SET NULL"))
    switch_id: Mapped[str | None] = mapped_column(String(64))
    target_track: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    rules_checked: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    raw_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    train: Mapped[Train | None] = relationship(back_populates="decisions")


class EventLog(Base):
    __tablename__ = "event_log"
    __table_args__ = (Index("ix_event_log_timestamp", "timestamp"), Index("ix_event_log_object", "object_type", "object_id"))

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=event_id)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(String(512))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    actor: Mapped[User | None] = relationship(back_populates="events")


class MlOriginEvent(Base):
    __tablename__ = "ml_origin_events"
    __table_args__ = (
        UniqueConstraint("source_namespace", "source_event_id", name="uq_ml_origin_namespace_event"),
        Index("ix_ml_origin_device_detected", "device_id", "detected_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    alert_id: Mapped[str | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"))
    model_version: Mapped[str | None] = mapped_column(String(120))
    inference_ms: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    device: Mapped[Device | None] = relationship(back_populates="ml_events")
    alert: Mapped[Alert | None] = relationship(back_populates="ml_events")
