from datetime import datetime
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DecisionRule(BaseModel):
    rule: str = Field(min_length=1, max_length=240)
    passed: bool


class SwitchDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime | None = None
    train_id: str | None = Field(default=None, max_length=64)
    switch_id: str | None = Field(default=None, max_length=64)
    position: float | None = None
    action: Literal["MAINTAIN", "SWITCH", "EMERGENCY_STOP"]
    action_level: str | None = Field(default=None, max_length=32)
    target_track: str | None = Field(default=None, max_length=80)
    confidence: float = Field(ge=0, le=1)
    rules_checked: list[DecisionRule] = Field(default_factory=list, max_length=64)
    raw_scores: dict[str, float | None] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class SensorReadingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    value: Any
    status: str = Field(default="OK", max_length=24)
    unit: str | None = Field(default=None, max_length=32)
    interpreted_value: str | None = Field(default=None, max_length=256)
    recorded_at: datetime | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Sensor name cannot be blank")
        return value.strip()

    @field_validator("value")
    @classmethod
    def value_must_be_json_safe(cls, value: Any) -> Any:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Sensor value must be finite JSON data") from exc
        return value


class SensorReadingsBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=64)
    source: Literal["esp32", "hardware", "raspberry_pi"] = "esp32"
    readings: list[SensorReadingInput] = Field(min_length=1, max_length=100)


class DeviceRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    platform: str | None = Field(default="ESP32", max_length=120)
    city: str | None = Field(default=None, max_length=80)
