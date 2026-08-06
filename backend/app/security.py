from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from .config import settings


PBKDF2_ITERATIONS = 390_000


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), _b64_decode(salt), int(iterations)
        )
        return hmac.compare_digest(_b64_encode(digest), expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + settings.token_expire_hours * 3600,
    }
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64_encode(signature)}"


def decode_token(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64_encode(expected), signature):
            return None
        payload = json.loads(_b64_decode(body))
        if int(payload["exp"]) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None

