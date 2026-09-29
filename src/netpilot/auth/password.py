"""Argon2id password hashing and verification."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_HASHER = PasswordHasher(type=Type.ID)
_DUMMY_HASH = _HASHER.hash("netpilot-nonexistent-user-dummy-password")


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Use a dummy hash for unknown users to avoid a trivial timing oracle."""

    try:
        valid = _HASHER.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return bool(valid and password_hash is not None)
