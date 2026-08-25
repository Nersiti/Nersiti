"""Пароль входа в приложение. Хранится только SHA-256, не открытый текст."""
from __future__ import annotations

import hashlib
import hmac


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_password(password: str, expected_sha256: str) -> bool:
    return hmac.compare_digest(hash_password(password), expected_sha256.lower())
