from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=10, max_length=256)


class AdminPasswordResetRequest(BaseModel):
    password: str = Field(min_length=10, max_length=256)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    city: str | None = Field(default=None, max_length=80)
    role: Literal["worker", "operator", "admin"] = "worker"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("city")
    @classmethod
    def normalize_city(cls, value: str | None) -> str | None:
        return value.strip().lower() or None if value is not None else None


class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    worker_id: str | None
    name: str
    email: str
    username: str | None
    role: str
    approval_status: str
    status: str
    city: str | None


class LoginResponse(BaseModel):
    token: str
    role: Literal["admin", "worker"]
    name: str
    worker_id: str | None
    city: str | None
    source: str = "unknown"


class RegistrationResponse(BaseModel):
    message: str
    user: PublicUser


class CreateAdminRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("name")
    @classmethod
    def normalize_admin_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_admin_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) < 3:
            raise ValueError("Username must contain at least 3 characters")
        return value
