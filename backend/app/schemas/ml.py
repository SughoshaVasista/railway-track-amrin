from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MlEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    source_event_id: str = Field(min_length=1, max_length=160)
    detected_at: datetime
    source: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=1, max_length=64)
    defect: str = Field(min_length=1, max_length=120)
    severity: Literal["S1", "S2", "S3"]
    confidence: float = Field(ge=0, le=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=100000)
    chainage: str | None = Field(default=None, max_length=80)
    track: str | None = Field(default=None, max_length=80)
    boxes: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    sensor_fusion: dict[str, Any] | None = None
    model_version: str | None = Field(default=None, max_length=120)
    inference_ms: float | None = Field(default=None, ge=0, le=600000)
    city: str | None = Field(default=None, max_length=80)

    @field_validator("detected_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("detected_at must include a UTC offset")
        return value

    @field_validator("source", "source_event_id", "device_id", "defect")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()
