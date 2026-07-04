"""Signed, stateless CSRF tokens for browser-originated unsafe requests (Chunk B).

Tokens are HMAC-SHA256 signed with ``SECRET_KEY``, bound to a subject (the
authenticated user id) and stamped with an issue time. This proves a request
originated from a page this app rendered for that user, without requiring a
server-side session store. Pure stdlib so it stays trivially unit-testable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

_VERSION = "v1"
_DEFAULT_MAX_AGE_SECONDS = 86_400  # 24h; pages re-issue a fresh token on render


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(secret_key: str, payload: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_csrf_token(secret_key: str, subject: str, *, issued_at: int | None = None) -> str:
    """Return a signed CSRF token bound to ``subject``."""
    ts = int(time.time()) if issued_at is None else int(issued_at)
    subject_b64 = _b64encode((subject or "").encode("utf-8"))
    nonce = secrets.token_hex(8)
    payload = f"{_VERSION}.{subject_b64}.{ts}.{nonce}"
    return f"{payload}.{_sign(secret_key, payload)}"


def validate_csrf_token(
    secret_key: str,
    token: str,
    subject: str,
    *,
    max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS,
    now: int | None = None,
) -> bool:
    """Return True when ``token`` is a valid, unexpired token for ``subject``."""
    if not secret_key or not token:
        return False
    parts = token.split(".")
    if len(parts) != 5:
        return False
    version, subject_b64, ts_raw, nonce, sig = parts
    if version != _VERSION:
        return False

    payload = f"{version}.{subject_b64}.{ts_raw}.{nonce}"
    expected_sig = _sign(secret_key, payload)
    if not hmac.compare_digest(sig, expected_sig):
        return False

    # Signature verified -> the embedded subject is authentic. Bind to caller.
    try:
        token_subject = _b64decode(subject_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    if not hmac.compare_digest(token_subject, subject or ""):
        return False

    try:
        issued_at = int(ts_raw)
    except ValueError:
        return False
    current = int(time.time()) if now is None else int(now)
    if current - issued_at > max_age_seconds:
        return False
    return True
