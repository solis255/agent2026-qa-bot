"""Internal authentication records; password hashes never enter API schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, repr=False)
class UserRecord:
    id: UUID
    username: str
    password_hash: str
    nickname: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
