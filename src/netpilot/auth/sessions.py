"""Opaque browser token generation; persist only its SHA-256 digest."""

from __future__ import annotations

import hashlib
import secrets


def create_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_session_token(token)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
