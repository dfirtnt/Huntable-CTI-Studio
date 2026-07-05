"""Audit action vocabulary contract.

The enterprise-auth auditability spec enumerates the stable audit action names
("Initial stable action names" section). Several ACTION_* constants in
src/services/audit_service.py are reserved by that spec ahead of any emitter,
so a dead-code sweep must not remove them: this test makes the reservation
enforceable rather than comment-advisory (the 2026-07-05 cleanup kept them by
hand; this pins the decision).
"""

import re
from pathlib import Path

import pytest

from src.services import audit_service

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-06-17-enterprise-auth-auditability-build-spec.md"


def _spec_action_names() -> list[str]:
    text = SPEC.read_text(encoding="utf-8")
    marker = "## Audit Actions"
    assert marker in text, f"{SPEC.name} no longer has an '## Audit Actions' section"
    section = text.split(marker, 1)[1]
    end = section.find("\n## ")
    if end != -1:
        section = section[:end]
    names = re.findall(r"^- `([a-z_]+\.[a-z_]+)`", section, re.M)
    assert names, f"no action names parsed from {SPEC.name} '## Audit Actions' section"
    return names


def _code_action_values() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(audit_service).items()
        if name.startswith("ACTION_") and isinstance(value, str)
    }


def test_every_spec_reserved_action_name_is_defined_in_code() -> None:
    code_values = set(_code_action_values().values())
    missing = [name for name in _spec_action_names() if name not in code_values]
    assert not missing, (
        f"audit_service.py no longer defines spec-reserved action name(s) {missing}; "
        "these are stable vocabulary from the enterprise-auth auditability spec and "
        "must not be removed as dead code"
    )


def test_action_constant_values_are_unique() -> None:
    values = list(_code_action_values().values())
    duplicates = {v for v in values if values.count(v) > 1}
    assert not duplicates, f"duplicate audit action string(s): {duplicates}"
