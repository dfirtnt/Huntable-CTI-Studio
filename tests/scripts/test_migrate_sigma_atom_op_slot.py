"""Tests for scripts/migrate_sigma_atom_op_slot.py.

The script is a one-shot operator tool; its SQL path is verified via
``--dry-run`` against a real Postgres instance. These tests pin the pure-logic
surface that is most likely to regress: the ``strip_op_slot`` string transform
that rewrites legacy 4-slot atom identities (``field|op|modifier_chain|value``)
to the 3-slot form (``field|modifier_chain|value``).

The three legacy shapes observed in the live corpus are covered explicitly:

- ``field|op|op|value``          single modifier (e.g. process.image|endswith|endswith|/env)
- ``field|op|op|mod2|value``     multi modifier  (e.g. scriptblocktext|contains|contains|all|-foo)
- ``field|eq||value``            default eq      (e.g. process_name|eq||powershell.exe)

Idempotency is asserted: re-running the transform on already-3-slot strings is
a no-op, so the migration is safe to re-run.

These are unit tests — no DB, no network.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_sigma_atom_op_slot.py"


def _load_script_module():
    """Import the migration script as a module without executing main()."""
    spec = importlib.util.spec_from_file_location("migrate_sigma_atom_op_slot", SCRIPT_PATH)
    assert spec and spec.loader, f"Cannot load script spec from {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    module = _load_script_module()
    yield module
    sys.modules.pop("migrate_sigma_atom_op_slot", None)


# ---------------------------------------------------------------------------
# strip_op_slot: legacy 4-slot -> 3-slot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "legacy,expected",
    [
        # single modifier: op duplicated in slot 1 and 2
        ("process.image|endswith|endswith|/env", "process.image|endswith|endswith|/env".replace("|endswith|endswith|", "|endswith|")),
        ("process.command_line|contains|contains|apached", "process.command_line|contains|apached"),
        # multi-modifier chain: op duplicates the first chain token
        ("scriptblocktext|contains|contains|all|-path", "scriptblocktext|contains|all|-path"),
        # default eq with empty modifier chain
        ("process_name|eq||powershell.exe", "process_name||powershell.exe"),
        ("eventid|eq||4698", "eventid||4698"),
    ],
)
def test_strip_op_slot_rewrites_legacy(script, legacy, expected):
    assert script.strip_op_slot(legacy) == expected


def test_strip_op_slot_single_mod_explicit(script):
    # spell out the canonical single-modifier case rather than via .replace()
    assert script.strip_op_slot("process.image|endswith|endswith|/env") == "process.image|endswith|/env"


# ---------------------------------------------------------------------------
# strip_op_slot: already-3-slot strings are untouched (idempotency)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "already_3slot",
    [
        "process.image|endswith|/env",       # single modifier, new form
        "process_name||powershell.exe",      # default eq, new form
        "scriptblocktext|contains|all|-path",  # genuine multi-modifier, new form
        "c-uri|contains|/pwndrop/",
    ],
)
def test_strip_op_slot_leaves_3slot_unchanged(script, already_3slot):
    assert script.strip_op_slot(already_3slot) == already_3slot


def test_strip_op_slot_is_idempotent(script):
    """Re-running the transform on its own output must be a no-op."""
    for legacy in [
        "process.image|endswith|endswith|/env",
        "scriptblocktext|contains|contains|all|-path",
        "process_name|eq||powershell.exe",
    ]:
        once = script.strip_op_slot(legacy)
        twice = script.strip_op_slot(once)
        assert once == twice


# ---------------------------------------------------------------------------
# strip_op_slot: edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "atom",
    [
        "",
        "field",
        "field|value",            # 2 segments, nothing to strip
        "field|mod|value",        # 3 segments, new form
    ],
)
def test_strip_op_slot_short_strings_passthrough(script, atom):
    assert script.strip_op_slot(atom) == atom


def test_strip_op_slot_does_not_touch_genuine_multimod_new_form(script):
    # A real multi-modifier where op (slot1) != first chain token (slot2):
    # this is already new-form and must NOT be collapsed.
    assert script.strip_op_slot("field|cased|contains|value") == "field|cased|contains|value"


def test_strip_op_slot_value_with_pipes_unaffected_tail(script):
    # Values may contain '|'; the transform only edits the front of the string.
    legacy = "process.command_line|contains|contains|a|b|c"
    assert script.strip_op_slot(legacy) == "process.command_line|contains|a|b|c"


# ---------------------------------------------------------------------------
# migrate_atom_list: list handling + change counting
# ---------------------------------------------------------------------------


def test_migrate_atom_list_counts_changes(script):
    atoms = [
        "process.image|endswith|endswith|/env",   # changes
        "process_name|eq||powershell.exe",        # changes
        "c-uri|contains|/pwndrop/",               # already 3-slot, no change
    ]
    new_atoms, changed = script.migrate_atom_list(atoms)
    assert changed == 2
    assert new_atoms == [
        "process.image|endswith|/env",
        "process_name||powershell.exe",
        "c-uri|contains|/pwndrop/",
    ]


def test_migrate_atom_list_empty_and_none(script):
    assert script.migrate_atom_list([]) == ([], 0)
    assert script.migrate_atom_list(None) == (None, 0)


def test_migrate_atom_list_already_migrated_is_noop(script):
    atoms = ["process.image|endswith|/env", "process_name||powershell.exe"]
    new_atoms, changed = script.migrate_atom_list(atoms)
    assert changed == 0
    assert new_atoms == atoms


def test_migrate_atom_list_preserves_non_string_elements(script):
    atoms = ["process.image|endswith|endswith|/env", 42]
    new_atoms, changed = script.migrate_atom_list(atoms)
    assert changed == 1
    assert new_atoms == ["process.image|endswith|/env", 42]
