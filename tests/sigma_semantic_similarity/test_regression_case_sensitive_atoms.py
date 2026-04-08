"""
Regression tests for case-sensitive atom matching bug (2026-04-08).

Bug: Similarity Search returned zero results for all queued rules.
Root cause: atom_extractor.py had two case-sensitivity bugs:
  1. FIELD_ALIAS_MAP lookup was exact-match only — LLM-generated rules using
     lowercase/snake_case fields (image, command_line) resolved to different
     namespaces than SigmaHQ's PascalCase atoms (process.image, process.command_line).
  2. _normalize_value() never lowercased string values — Sigma's case-insensitive
     operators (contains, endswith, startswith, eq) treated 'Delete' and 'delete'
     as different atoms.

Fix: sigma_semantic_similarity/sigma_similarity/atom_extractor.py
     src/services/sigma_novelty_service.py

Solution doc: docs/solutions/logic-errors/sigma-similarity-case-sensitive-atom-matching-2026-04-08.md

These tests reproduce the EXACT failure from the bug report. If any test here
fails, the case-sensitive atom matching bug has regressed.
"""

import pytest
from sigma_similarity.ast_builder import AtomNode, build_ast
from sigma_similarity.atom_extractor import (
    _resolve_field,
    atom_identity,
    extract_positive_atoms,
)
from sigma_similarity.detection_normalizer import normalize_detection
from sigma_similarity.dnf_normalizer import ast_to_dnf
from sigma_similarity.similarity_engine import compare_rules

# Mark all tests in this file as regression tests
pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Regression #1: _resolve_field must be case-insensitive
#
# Before the fix, _resolve_field("image") returned "image" (not in map),
# while _resolve_field("Image") returned "process.image" (in map).
# This caused ZERO atom overlap between LLM-generated and SigmaHQ rules.
# ---------------------------------------------------------------------------


class TestResolveFieldCaseInsensitive:
    """_resolve_field MUST return the same canonical name regardless of input casing."""

    def test_image_lowercase(self):
        assert _resolve_field("image") == "process.image"

    def test_image_pascalcase(self):
        assert _resolve_field("Image") == "process.image"

    def test_commandline_lowercase(self):
        assert _resolve_field("commandline") == "process.command_line"

    def test_commandline_pascalcase(self):
        assert _resolve_field("CommandLine") == "process.command_line"

    def test_command_line_snake_case(self):
        assert _resolve_field("command_line") == "process.command_line"

    def test_parentimage_lowercase(self):
        assert _resolve_field("parentimage") == "process.parent_image"

    def test_parentimage_pascalcase(self):
        assert _resolve_field("ParentImage") == "process.parent_image"

    def test_parent_image_snake_case(self):
        assert _resolve_field("parent_image") == "process.parent_image"


# ---------------------------------------------------------------------------
# Regression #2: atom_identity must case-fold values for CI operators
#
# Before the fix, atom_identity produced different strings for
# AtomNode("CommandLine", "contains", "contains|all", "Delete") vs
# AtomNode("CommandLine", "contains", "contains|all", "delete").
# Sigma's |contains| is case-insensitive — these MUST produce the same atom.
# ---------------------------------------------------------------------------


class TestAtomIdentityValueCaseFolding:
    """atom_identity MUST produce identical output for values differing only in case
    when the operator is case-insensitive (contains, endswith, startswith, eq)."""

    def test_contains_delete_vs_delete(self):
        """The EXACT atoms from the bug report."""
        a = atom_identity(AtomNode("CommandLine", "contains", "contains|all", "Delete"))
        b = atom_identity(AtomNode("CommandLine", "contains", "contains|all", "delete"))
        assert a == b, f"contains|all 'Delete' vs 'delete' must match: {a!r} != {b!r}"

    def test_contains_shadows_vs_shadows(self):
        """The EXACT atoms from the bug report."""
        a = atom_identity(AtomNode("CommandLine", "contains", "contains|all", "Shadows"))
        b = atom_identity(AtomNode("CommandLine", "contains", "contains|all", "shadows"))
        assert a == b, f"contains|all 'Shadows' vs 'shadows' must match: {a!r} != {b!r}"

    def test_endswith_vssadmin(self):
        a = atom_identity(AtomNode("Image", "endswith", "endswith", "\\VSSADMIN.EXE"))
        b = atom_identity(AtomNode("Image", "endswith", "endswith", "\\vssadmin.exe"))
        assert a == b

    def test_eq_originalfilename(self):
        a = atom_identity(AtomNode("OriginalFileName", "eq", "", "VSSADMIN.EXE"))
        b = atom_identity(AtomNode("OriginalFileName", "eq", "", "vssadmin.exe"))
        assert a == b

    def test_regex_NOT_folded(self):
        """Regex is the one operator that MUST preserve case."""
        a = atom_identity(AtomNode("CommandLine", "re", "re", "(?i)Delete"))
        b = atom_identity(AtomNode("CommandLine", "re", "re", "(?i)delete"))
        assert a != b, "Regex patterns must preserve case"


# ---------------------------------------------------------------------------
# Regression #3: end-to-end — the EXACT bug report scenario
#
# Queue #247: "Shadow Copy Deletion Using Vssadmin" (LLM-generated, snake_case)
# vs SigmaHQ: "Shadow Copies Deletion Using Operating Systems Utilities"
#
# Before the fix: Jaccard=0.0, similarity=0.0, no_shared_atoms
# After the fix:  Jaccard>0, similarity>0, shared atoms include vssadmin+delete
# ---------------------------------------------------------------------------


class TestBugReportScenarioEndToEnd:
    """Reproduce the EXACT scenario from the bug report end-to-end."""

    PROPOSED_RULE = {
        "title": "Shadow Copy Deletion Using Vssadmin",
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {
            "selection": {
                "parent_image|endswith": "\\cmd.exe",  # snake_case field
                "image|endswith": "\\vssadmin.exe",  # snake_case field
                "command_line|contains|all": [  # snake_case field
                    "Delete",  # uppercase value
                    "Shadows",  # uppercase value
                    "/all",
                ],
            },
            "condition": "selection",
        },
    }

    SIGMAHQ_RULE = {
        "title": "Shadow Copies Deletion Via Vssadmin",
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {
            "selection_img": {
                "Image|endswith": "\\vssadmin.exe",  # PascalCase field
                "OriginalFileName": "VSSADMIN.EXE",
            },
            "selection_cli": {
                "CommandLine|contains|all": [  # PascalCase field
                    "delete",  # lowercase value
                    "shadows",  # lowercase value
                ],
            },
            "condition": "selection_img and selection_cli",
        },
    }

    def test_similarity_is_not_zero(self):
        """THE bug: similarity was 0.0. It must never be zero for these rules."""
        result = compare_rules(self.PROPOSED_RULE, self.SIGMAHQ_RULE)
        assert result.similarity > 0, (
            f"REGRESSION: similarity is {result.similarity} "
            f"(reason_flags={result.explanation.get('reason_flags')}). "
            "Case-sensitive atom matching bug has returned."
        )

    def test_no_shared_atoms_flag_absent(self):
        """THE bug produced 'no_shared_atoms'. It must not appear for these rules."""
        result = compare_rules(self.PROPOSED_RULE, self.SIGMAHQ_RULE)
        flags = result.explanation.get("reason_flags", [])
        assert "no_shared_atoms" not in flags, (
            "REGRESSION: 'no_shared_atoms' flag present. Field alias or value normalization is broken."
        )

    def test_shared_atoms_exist(self):
        """Directly verify that atoms from both rules overlap."""
        norm_a = normalize_detection(self.PROPOSED_RULE["detection"])
        norm_b = normalize_detection(self.SIGMAHQ_RULE["detection"])
        dnf_a = ast_to_dnf(build_ast(norm_a))
        dnf_b = ast_to_dnf(build_ast(norm_b))
        atoms_a = extract_positive_atoms(dnf_a)
        atoms_b = extract_positive_atoms(dnf_b)
        shared = atoms_a & atoms_b
        assert len(shared) >= 2, (
            f"REGRESSION: only {len(shared)} shared atoms (expected >= 2). "
            f"A={sorted(atoms_a)}, B={sorted(atoms_b)}, shared={sorted(shared)}"
        )

    def test_vssadmin_atom_shared(self):
        """The vssadmin.exe endswith atom must be shared (field + value normalized)."""
        norm_a = normalize_detection(self.PROPOSED_RULE["detection"])
        norm_b = normalize_detection(self.SIGMAHQ_RULE["detection"])
        dnf_a = ast_to_dnf(build_ast(norm_a))
        dnf_b = ast_to_dnf(build_ast(norm_b))
        atoms_a = extract_positive_atoms(dnf_a)
        atoms_b = extract_positive_atoms(dnf_b)
        shared = atoms_a & atoms_b
        vssadmin_atoms = [a for a in shared if "vssadmin" in a]
        assert vssadmin_atoms, (
            f"REGRESSION: no vssadmin atom in shared set. "
            f"A has: {[a for a in atoms_a if 'vssadmin' in a]}, "
            f"B has: {[a for a in atoms_b if 'vssadmin' in a]}"
        )

    def test_delete_atom_shared(self):
        """The 'delete' contains|all atom must be shared (value case-folded)."""
        norm_a = normalize_detection(self.PROPOSED_RULE["detection"])
        norm_b = normalize_detection(self.SIGMAHQ_RULE["detection"])
        dnf_a = ast_to_dnf(build_ast(norm_a))
        dnf_b = ast_to_dnf(build_ast(norm_b))
        atoms_a = extract_positive_atoms(dnf_a)
        atoms_b = extract_positive_atoms(dnf_b)
        shared = atoms_a & atoms_b
        delete_atoms = [a for a in shared if "delete" in a]
        assert delete_atoms, (
            f"REGRESSION: no 'delete' atom in shared set. "
            f"Value case-folding may be broken. "
            f"A has: {[a for a in atoms_a if 'elete' in a.lower()]}, "
            f"B has: {[a for a in atoms_b if 'elete' in a.lower()]}"
        )
