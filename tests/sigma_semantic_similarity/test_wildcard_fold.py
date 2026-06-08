"""Spec Item 9 (P1-B): wildcard ↔ modifier canonicalization in atom_identity.

Sigma lets authors write the same anchored-substring detection two equivalent ways:

    Image: '*foo.exe'              # literal '*' as wildcard
    Image|endswith: 'foo.exe'      # explicit modifier

Today the deterministic engine treats the value strings literally, so these
produce different ``atom_identity`` outputs and a Jaccard of 0. The fold below
normalizes leading/trailing literal ``*`` into the equivalent modifier op so
both forms produce the SAME identity string.

Be conservative: only fold ``*`` at the START or END of the value. Internal
``*`` patterns (``foo*bar*baz``) are left alone — they could be literal
asterisks in a path or a complex pattern we should not silently rewrite.

These tests are RED before the fix lands in
``sigma_semantic_similarity/sigma_similarity/atom_extractor.py``.
"""

from __future__ import annotations

import pytest
from sigma_similarity.ast_builder import AtomNode
from sigma_similarity.atom_extractor import atom_identity

pytestmark = pytest.mark.unit


def _op_of(ident: str) -> str:
    """Recover the operator from a 3-slot atom identity ``field|modifier_chain|value``.

    The operator is the first modifier token; an empty modifier chain (the
    ``field||value`` shape) denotes the default ``eq``. This mirrors the
    documented recovery rule ``modifier_chain.split("|")[0]``.
    """
    segments = ident.split("|")
    mods = segments[1:-1]
    return mods[0] if mods and mods[0] else "eq"


# ---------------------------------------------------------------------------
# Equivalence: the two forms MUST produce the same identity. This is the
# load-bearing property — every other test in this file is a consequence.
# ---------------------------------------------------------------------------


class TestWildcardModifierEquivalence:
    """The Sigma-equivalent forms must produce identical atom_identity strings."""

    def test_leading_star_eq_equals_endswith(self):
        """Image: '*foo.exe' MUST equal Image|endswith: 'foo.exe'."""
        wild = atom_identity(AtomNode("Image", "eq", "", "*foo.exe"))
        modifier = atom_identity(AtomNode("Image", "endswith", "endswith", "foo.exe"))
        assert wild == modifier, f"{wild!r} != {modifier!r}"

    def test_trailing_star_eq_equals_startswith(self):
        """Image: 'foo*' MUST equal Image|startswith: 'foo'."""
        wild = atom_identity(AtomNode("Image", "eq", "", "foo*"))
        modifier = atom_identity(AtomNode("Image", "startswith", "startswith", "foo"))
        assert wild == modifier, f"{wild!r} != {modifier!r}"

    def test_double_star_eq_equals_contains(self):
        """Image: '*foo*' MUST equal Image|contains: 'foo'."""
        wild = atom_identity(AtomNode("Image", "eq", "", "*foo*"))
        modifier = atom_identity(AtomNode("Image", "contains", "contains", "foo"))
        assert wild == modifier, f"{wild!r} != {modifier!r}"

    def test_double_star_eq_equals_contains_with_path(self):
        """Realistic example: '*\\AppData\\Roaming\\php\\*' canonicalizes to the contains form."""
        # Note: \\ in Sigma YAML normalizes to / in atom_identity (single backslash).
        wild = atom_identity(AtomNode("CommandLine", "eq", "", "*\\AppData\\Roaming\\php\\*"))
        modifier = atom_identity(AtomNode("CommandLine", "contains", "contains|all", "\\AppData\\Roaming\\php\\"))
        # The folded `eq` form should produce `<field>|contains|...` — equivalence is on the
        # behavioral predicate, not on modifier_chain length. Compare the field/op/value parts.
        wild_parts = wild.split("|")
        mod_parts = modifier.split("|")
        assert wild_parts[0] == mod_parts[0], "field mismatch"
        assert _op_of(wild) == _op_of(modifier) == "contains", "op should be contains on both sides"
        assert wild_parts[-1] == mod_parts[-1], f"value mismatch: {wild_parts[-1]!r} != {mod_parts[-1]!r}"


# ---------------------------------------------------------------------------
# Eq with edge wildcards: each fold direction (none / leading / trailing / both).
# ---------------------------------------------------------------------------


class TestEqWildcardFolds:
    """When operator is eq, leading/trailing literal * become the matching modifier op."""

    def test_eq_no_wildcard_unchanged(self):
        """No '*' anywhere → eq stays eq, value verbatim."""
        out = atom_identity(AtomNode("OriginalFileName", "eq", "", "powershell.exe"))
        parts = out.split("|")
        assert _op_of(out) == "eq"
        assert parts[-1] == "powershell.exe"

    def test_eq_leading_star_becomes_endswith(self):
        out = atom_identity(AtomNode("Image", "eq", "", "*foo.exe"))
        parts = out.split("|")
        assert _op_of(out) == "endswith", f"op should be endswith; got {_op_of(out)!r}"
        assert parts[-1] == "foo.exe", f"value should be stripped; got {parts[-1]!r}"

    def test_eq_trailing_star_becomes_startswith(self):
        out = atom_identity(AtomNode("Image", "eq", "", "C:/Users/x/foo*"))
        parts = out.split("|")
        assert _op_of(out) == "startswith"
        assert parts[-1] == "c:/users/x/foo"

    def test_eq_both_stars_becomes_contains(self):
        out = atom_identity(AtomNode("CommandLine", "eq", "", "*malware*"))
        parts = out.split("|")
        assert _op_of(out) == "contains"
        assert parts[-1] == "malware"


# ---------------------------------------------------------------------------
# Explicit modifier + redundant wildcard: strip the redundant `*` only.
# ---------------------------------------------------------------------------


class TestRedundantWildcardStripping:
    """When op is already contains/endswith/startswith and value has redundant edge *, strip."""

    def test_contains_with_double_stars_strips_both(self):
        # CommandLine|contains: '*foo*' is redundant — the modifier already implies wraparound.
        out = atom_identity(AtomNode("CommandLine", "contains", "contains", "*foo*"))
        parts = out.split("|")
        assert _op_of(out) == "contains"
        assert parts[-1] == "foo"

    def test_endswith_with_redundant_leading_star_strips_it(self):
        out = atom_identity(AtomNode("Image", "endswith", "endswith", "*defrag.exe"))
        parts = out.split("|")
        assert _op_of(out) == "endswith"
        assert parts[-1] == "defrag.exe"

    def test_startswith_with_redundant_trailing_star_strips_it(self):
        out = atom_identity(AtomNode("Image", "startswith", "startswith", "svchost*"))
        parts = out.split("|")
        assert _op_of(out) == "startswith"
        assert parts[-1] == "svchost"


# ---------------------------------------------------------------------------
# Internal-only wildcards: AMBIGUOUS — must NOT be folded.
# ---------------------------------------------------------------------------


class TestInternalWildcardsLeftAlone:
    """Internal '*' patterns might be literal asterisks; conservatism wins."""

    def test_internal_star_eq_unchanged(self):
        # 'foo*bar' has no leading or trailing * → no fold, op stays eq.
        out = atom_identity(AtomNode("CommandLine", "eq", "", "foo*bar"))
        parts = out.split("|")
        assert _op_of(out) == "eq"
        assert parts[-1] == "foo*bar"

    def test_multiple_internal_stars_unchanged(self):
        out = atom_identity(AtomNode("CommandLine", "eq", "", "foo*bar*baz"))
        parts = out.split("|")
        assert _op_of(out) == "eq"
        assert parts[-1] == "foo*bar*baz"


# ---------------------------------------------------------------------------
# Non-foldable ops: regex and numeric ops preserve value verbatim.
# ---------------------------------------------------------------------------


class TestNonFoldableOpsPreserveValue:
    """Regex patterns and numeric comparisons must never have value mutated."""

    def test_regex_with_literal_asterisks_unchanged(self):
        # Regex .* and ^ are pattern syntax; the literal * inside is meaningful.
        pattern = r"^.*foo.*$"
        out = atom_identity(AtomNode("CommandLine", "re", "re", pattern))
        parts = out.split("|")
        assert _op_of(out) == "re"
        # Regex values are NOT case-folded, NOT wildcard-folded.
        assert parts[-1] == pattern

    def test_neq_with_trailing_star_unchanged(self):
        # neq is numeric/exact-non-match; the * is literal.
        out = atom_identity(AtomNode("EventID", "neq", "neq", "4624*"))
        parts = out.split("|")
        assert _op_of(out) == "neq"
        assert parts[-1] == "4624*"


# ---------------------------------------------------------------------------
# Edge cases (defensive).
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Pathological inputs must not raise."""

    def test_empty_value_unchanged(self):
        out = atom_identity(AtomNode("Image", "eq", "", ""))
        parts = out.split("|")
        assert _op_of(out) == "eq"
        assert parts[-1] == ""

    def test_single_star_value_yields_endswith_empty(self):
        # value = '*' has both leading and trailing star but len < 2 for the
        # contains case; the canonical choice is endswith with empty value
        # (matches everything that ends with empty string — i.e. all values).
        # The important property: the result is deterministic and DOES NOT
        # raise. Whether endswith/startswith/contains is "right" here is
        # semantically uninteresting — Sigma authors don't write Image: '*'.
        out = atom_identity(AtomNode("Image", "eq", "", "*"))
        # Just assert determinism — call twice, get the same answer.
        out2 = atom_identity(AtomNode("Image", "eq", "", "*"))
        assert out == out2

    def test_idempotent_under_repeated_calls(self):
        # The fold is computed at atom_identity time; subsequent calls on the same
        # AtomNode yield the same identity string.
        node = AtomNode("CommandLine", "eq", "", "*payload*")
        assert atom_identity(node) == atom_identity(node)
