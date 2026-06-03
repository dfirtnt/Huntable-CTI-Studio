"""Tests for scripts/mine_sigma_pair_candidates.py :: canon_atom().

canon_atom() is the engine-INDEPENDENT canonicalization used to identify pairs
the current novelty engine fails to match because of surface-syntax variation
(wildcard vs. modifier, redundant operator-in-chain, |all token). It is also
the reference spec for an upcoming fix to the engine's atom keying — so it
needs to behave EXACTLY as documented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.mine_sigma_pair_candidates import canon_atom  # noqa: E402

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# The 6 worked examples from the spec (these are the load-bearing cases).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stored, expected",
    [
        # Example 1: op duplicated in modifier_chain (the storage layer always
        # does this when a modifier is present) — collapse to one op token.
        (
            "process.image|endswith|endswith|/safetykatz.exe",
            "process.image|endswith|/safetykatz.exe",
        ),
        # Example 2: bare field (no modifier) -> op="eq" with empty middle slot.
        (
            "originalfilename|eq||powershell.exe",
            "originalfilename|eq|powershell.exe",
        ),
        # Example 3: |all token in modifier_chain — irrelevant to behavioral
        # identity; must be dropped.
        (
            "process.command_line|contains|contains|all|new-adserviceaccount",
            "process.command_line|contains|new-adserviceaccount",
        ),
        # Example 4: wildcard-on-value (rule author used wildcard instead of
        # modifier) — fold *X to op=endswith.
        (
            "process.image|eq||*/certutil.exe",
            "process.image|endswith|/certutil.exe",
        ),
        # Example 5: *X* with eq -> contains.
        (
            "process.command_line|eq||*http*",
            "process.command_line|contains|http",
        ),
        # Example 6: redundant contains modifier (already canonical-ish) -> same
        # key as Example 5. This is THE point: stored differently, same key.
        (
            "process.command_line|contains|contains|http",
            "process.command_line|contains|http",
        ),
    ],
)
def test_spec_examples(stored: str, expected: str) -> None:
    assert canon_atom(stored) == expected


def test_examples_5_and_6_collapse_to_same_key() -> None:
    """The whole reason canon_atom exists: these two MUST collapse identically."""
    a = canon_atom("process.command_line|eq||*http*")
    b = canon_atom("process.command_line|contains|contains|http")
    assert a == b == "process.command_line|contains|http"


# ---------------------------------------------------------------------------
# Wildcard folding edges (X* -> startswith; *X -> endswith; both -> contains).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stored, expected",
    [
        # startswith via trailing-only wildcard with eq.
        ("process.image|eq||cmd*", "process.image|startswith|cmd"),
        # endswith via leading-only wildcard with eq.
        ("process.image|eq||*cmd.exe", "process.image|endswith|cmd.exe"),
        # contains via both wildcards.
        ("process.image|eq||*cmd*", "process.image|contains|cmd"),
        # contains-modifier with redundant edge wildcards strips them.
        ("process.command_line|contains|contains|*foo*", "process.command_line|contains|foo"),
        # endswith-modifier with redundant leading wildcard strips it.
        (
            "process.image|endswith|endswith|*defrag.exe",
            "process.image|endswith|defrag.exe",
        ),
        # startswith-modifier with redundant trailing wildcard strips it.
        ("process.image|startswith|startswith|svchost*", "process.image|startswith|svchost"),
    ],
)
def test_wildcard_folding(stored: str, expected: str) -> None:
    assert canon_atom(stored) == expected


# ---------------------------------------------------------------------------
# Regex (re) and numeric ops MUST NOT have their value mutated.
# ---------------------------------------------------------------------------


def test_regex_preserves_value_verbatim() -> None:
    # A regex pattern with literal asterisks (quantifiers) must round-trip.
    stored = r"process.command_line|re|re|^.*foo\.exe.*$"
    assert canon_atom(stored) == r"process.command_line|re|^.*foo\.exe.*$"


def test_regex_with_modifier_chain_i_preserves_value() -> None:
    # re|i modifier chain (case-insensitive regex). Op is "re", value untouched.
    stored = r"process.command_line|re|re|i|^cmd.*"
    assert canon_atom(stored) == r"process.command_line|re|^cmd.*"


def test_neq_numeric_unchanged() -> None:
    assert canon_atom("event.id|neq|neq|4624") == "event.id|neq|4624"


# ---------------------------------------------------------------------------
# Idempotency: canon_atom(canon_atom(x)) == canon_atom(x).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stored",
    [
        "process.image|endswith|endswith|/safetykatz.exe",
        "process.command_line|contains|contains|all|new-adserviceaccount",
        "process.image|eq||*/certutil.exe",
        "process.command_line|eq||*http*",
        "originalfilename|eq||powershell.exe",
        r"process.command_line|re|re|^.*foo$",
    ],
)
def test_idempotent(stored: str) -> None:
    once = canon_atom(stored)
    twice = canon_atom(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Defensive: malformed inputs.
# ---------------------------------------------------------------------------


def test_single_segment_passes_through() -> None:
    # Not a real atom identity — should not raise.
    assert canon_atom("just_a_field") == "just_a_field"


def test_empty_value_eq() -> None:
    # field|eq||"" — pathological but should not raise; value stays empty.
    assert canon_atom("field|eq||") == "field|eq|"


def test_value_with_internal_pipe_is_lossy_but_does_not_raise() -> None:
    # Spec-acknowledged imprecision: a literal '|' in the value over-splits.
    # We assert behavior is deterministic (won't raise) — the human reviewer
    # catches semantic loss when inspecting the YAML.
    out = canon_atom("process.command_line|contains|contains|cmd | findstr")
    # last segment becomes the value.
    assert out == "process.command_line|contains| findstr"
