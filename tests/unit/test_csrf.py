"""Unit tests for signed CSRF token issue/validation (Chunk B Task 4)."""

import pytest

from src.web.security.csrf import issue_csrf_token, validate_csrf_token

pytestmark = pytest.mark.unit

SECRET = "test-secret-key-which-is-long-enough-1234"


def test_issued_token_validates_for_same_subject():
    token = issue_csrf_token(SECRET, "user-1")
    assert validate_csrf_token(SECRET, token, "user-1") is True


def test_token_rejected_for_different_subject():
    token = issue_csrf_token(SECRET, "user-1")
    assert validate_csrf_token(SECRET, token, "user-2") is False


def test_token_rejected_with_wrong_secret():
    token = issue_csrf_token(SECRET, "user-1")
    assert validate_csrf_token("other-secret-key-also-long-enough-00", token, "user-1") is False


def test_tampered_token_rejected():
    token = issue_csrf_token(SECRET, "user-1")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert validate_csrf_token(SECRET, tampered, "user-1") is False


def test_malformed_tokens_rejected():
    for bad in ("", "not-a-token", "a.b.c", "v1.only.two"):
        assert validate_csrf_token(SECRET, bad, "user-1") is False


def test_expired_token_rejected_but_valid_within_window():
    token = issue_csrf_token(SECRET, "user-1", issued_at=1000)
    assert validate_csrf_token(SECRET, token, "user-1", max_age_seconds=60, now=2000) is False
    assert validate_csrf_token(SECRET, token, "user-1", max_age_seconds=5000, now=2000) is True


def test_subject_with_special_chars_roundtrips():
    subject = "user@example.com|groups=a,b"
    token = issue_csrf_token(SECRET, subject)
    assert validate_csrf_token(SECRET, token, subject) is True


def test_empty_secret_never_validates():
    token = issue_csrf_token(SECRET, "user-1")
    assert validate_csrf_token("", token, "user-1") is False
