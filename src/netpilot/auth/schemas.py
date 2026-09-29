"""Public authentication requests and user response schema."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from netpilot.auth.models import UserRecord


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: SecretStr
    nickname: str | None = Field(default=None, max_length=40)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError("用户名须为 3–32 位字母、数字、下划线或连字符。")
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        plain = value.get_secret_value()
        if not 8 <= len(plain) <= 128 or not plain.strip():
            raise ValueError("密码须为 8–128 个非空白字符。")
        return value

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("昵称不能包含控制字符。")
        return normalized


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: SecretStr

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: SecretStr
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: SecretStr) -> SecretStr:
        return RegisterRequest.validate_password(value)


class UserView(BaseModel):
    id: UUID
    username: str
    nickname: str | None
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_record(cls, record: UserRecord) -> "UserView":
        return cls(
            id=record.id,
            username=record.username,
            nickname=record.nickname,
            created_at=record.created_at,
            last_login_at=record.last_login_at,
        )
