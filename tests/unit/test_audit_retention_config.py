"""Unit tests for AUDIT_RETENTION_DAYS resolution (Chunk C Task 6)."""

import pytest

from src.web.routes.audit import DEFAULT_AUDIT_RETENTION_DAYS, _default_retention_days

pytestmark = pytest.mark.unit


def test_default_is_365():
    assert DEFAULT_AUDIT_RETENTION_DAYS == 365


def test_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("AUDIT_RETENTION_DAYS", raising=False)
    assert _default_retention_days() == 365


def test_uses_valid_env_value(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")
    assert _default_retention_days() == 30


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "not-a-number")
    assert _default_retention_days() == 365


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_non_positive_env_falls_back_to_default(monkeypatch, bad):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", bad)
    assert _default_retention_days() == 365


def test_blank_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "")
    assert _default_retention_days() == 365
