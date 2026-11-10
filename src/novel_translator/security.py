"""Adapter hash mật khẩu bằng argon2 (argon2-cffi). Chỉ được nối trong container.py/CLI."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def is_valid_hash(password_hash: str) -> bool:
    return password_hash.startswith("$argon2")
