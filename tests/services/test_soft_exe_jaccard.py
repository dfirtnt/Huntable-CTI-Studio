"""Tests for soft cross-field Jaccard matching in sigma_novelty_service.

Covers _extract_exe_value, _soft_exe_jaccard_from_atom_strings, and the
fallback path inside compute_atom_jaccard (added 2026-04-09).
"""

import pytest

from src.services.sigma_novelty_service import (
    _PROCESS_EXE_CANONICAL_FIELDS,
    _extract_exe_value,
    _soft_exe_jaccard_from_atom_strings,
)

pytestmark = pytest.mark.unit


# ── _extract_exe_value ──────────────────────────────────────────────────────


class TestExtractExeValue:
    """Unit tests for _extract_exe_value."""

    def test_canonical_image_field(self):
        """Atom with process.image field returns the value segment."""
        atom = "process.image|endswith|endswith|/vssadmin.exe"
        assert _extract_exe_value(atom) == "/vssadmin.exe"

    def test_canonical_command_line_field(self):
        atom = "process.command_line|contains|contains|all|schtasks"
        assert _extract_exe_value(atom) == "schtasks"

    def test_legacy_image_field(self):
        atom = "image|endswith|endswith|/cmd.exe"
        assert _extract_exe_value(atom) == "/cmd.exe"

    def test_legacy_commandline_field(self):
        atom = "commandline|contains|contains|whoami"
        assert _extract_exe_value(atom) == "whoami"

    def test_parent_image_field(self):
        atom = "process.parent_image|endswith|endswith|/powershell.exe"
        assert _extract_exe_value(atom) == "/powershell.exe"

    def test_originalfilename_field(self):
        atom = "originalfilename|eq||vssadmin.exe"
        assert _extract_exe_value(atom) == "vssadmin.exe"

    def test_non_process_field_returns_none(self):
        """Fields outside the process-exe set should return None."""
        atom = "eventid|eq||4688"
        assert _extract_exe_value(atom) is None

    def test_no_pipe_separator_returns_none(self):
        """Atom with no pipe should return None."""
        assert _extract_exe_value("justafieldname") is None

    def test_single_pipe_returns_none(self):
        """Atom with only one pipe (field|rest) but < 3 segments returns None."""
        atom = "process.image|/vssadmin.exe"
        assert _extract_exe_value(atom) is None

    def test_empty_string_returns_none(self):
        assert _extract_exe_value("") is None

    def test_all_canonical_fields_recognized(self):
        """Every field in _PROCESS_EXE_CANONICAL_FIELDS must be extractable."""
        for field in _PROCESS_EXE_CANONICAL_FIELDS:
            atom = f"{field}|op|mod|testvalue"
            result = _extract_exe_value(atom)
            assert result == "testvalue", (
                f"Field {field!r} should be recognized but _extract_exe_value returned {result!r}"
            )


# ── _soft_exe_jaccard_from_atom_strings ─────────────────────────────────────


class TestSoftExeJaccard:
    """Unit tests for _soft_exe_jaccard_from_atom_strings."""

    def test_shared_exe_value_across_fields(self):
        """Same exe in different fields should produce positive soft jaccard."""
        # Rule A detects vssadmin via Image
        A1 = {"process.image|endswith|endswith|/vssadmin.exe"}
        # Rule B detects vssadmin via CommandLine
        A2 = {"process.command_line|contains|contains|/vssadmin.exe"}
        union = A1 | A2
        result = _soft_exe_jaccard_from_atom_strings(A1, A2, union)
        assert result > 0.0, "Cross-field shared exe value must produce positive soft jaccard"
        assert result <= 0.5, "Soft jaccard should be dampened by 0.5"

    def test_no_shared_values(self):
        """Different exe values should return 0."""
        A1 = {"process.image|endswith|endswith|/vssadmin.exe"}
        A2 = {"process.image|endswith|endswith|/cmd.exe"}
        union = A1 | A2
        assert _soft_exe_jaccard_from_atom_strings(A1, A2, union) == 0.0

    def test_no_process_exe_atoms(self):
        """If neither set has process-exe atoms, return 0."""
        A1 = {"eventid|eq||4688"}
        A2 = {"eventid|eq||4689"}
        union = A1 | A2
        assert _soft_exe_jaccard_from_atom_strings(A1, A2, union) == 0.0

    def test_one_side_empty(self):
        """If one side has no process-exe atoms, return 0."""
        A1 = {"process.image|endswith|endswith|/cmd.exe"}
        A2 = {"eventid|eq||4688"}
        union = A1 | A2
        assert _soft_exe_jaccard_from_atom_strings(A1, A2, union) == 0.0

    def test_dampening_factor(self):
        """Soft jaccard = (shared / union) * 0.5, capped at 1.0."""
        # Both have vssadmin.exe, union is 2 atoms
        A1 = {"process.image|endswith|endswith|/vssadmin.exe"}
        A2 = {"process.command_line|contains|contains|/vssadmin.exe"}
        union = A1 | A2
        expected = (1 / 2) * 0.5  # 0.25
        assert _soft_exe_jaccard_from_atom_strings(A1, A2, union) == pytest.approx(expected)

    def test_multiple_shared_values(self):
        """Multiple shared exe values increase the numerator."""
        A1 = {
            "process.image|endswith|endswith|/vssadmin.exe",
            "process.command_line|contains|contains|/cmd.exe",
        }
        A2 = {
            "process.parent_image|endswith|endswith|/vssadmin.exe",
            "process.parent_command_line|contains|contains|/cmd.exe",
        }
        union = A1 | A2
        # 2 shared values / 4 union atoms * 0.5 = 0.25
        result = _soft_exe_jaccard_from_atom_strings(A1, A2, union)
        assert result == pytest.approx(0.25)

    def test_mixed_process_and_non_process_atoms(self):
        """Non-process atoms shouldn't affect exe extraction but appear in union."""
        A1 = {
            "process.image|endswith|endswith|/vssadmin.exe",
            "eventid|eq||4688",
        }
        A2 = {
            "process.command_line|contains|contains|/vssadmin.exe",
            "logname|eq||security",
        }
        union = A1 | A2  # 4 atoms
        # 1 shared value / 4 union atoms * 0.5 = 0.125
        result = _soft_exe_jaccard_from_atom_strings(A1, A2, union)
        assert result == pytest.approx(0.125)

    def test_both_sides_empty(self):
        """Both empty sets should return 0."""
        A1: set[str] = set()
        A2: set[str] = set()
        union: set[str] = set()
        # Avoid division by zero
        assert _soft_exe_jaccard_from_atom_strings(A1, A2, union) == 0.0


# ── Integration: soft fallback in compute_atom_jaccard ──────────────────────


class TestSoftJaccardFallbackInNoveltyService:
    """Integration test: compute_atom_jaccard falls back to soft exe matching."""

    def test_cross_field_detection_gets_nonzero_jaccard(self):
        """compute_atom_jaccard returns positive for same exe value in different fields.

        Both rules use endswith with the same value so atoms share the same exe
        value. The fields differ (Image vs ParentImage), so strict atom intersection
        is 0 but the soft exe fallback should fire.
        """
        from src.services.sigma_novelty_service import SigmaNoveltyService

        service = SigmaNoveltyService()

        # Proposed: detects vssadmin.exe via ParentImage
        proposed = {
            "title": "Vssadmin via ParentImage",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "ParentImage|endswith": "\\vssadmin.exe",
                },
                "condition": "selection",
            },
        }

        # Candidate: detects vssadmin.exe via Image (different field, same value)
        candidate = {
            "title": "Vssadmin via Image",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "Image|endswith": "\\vssadmin.exe",
                },
                "condition": "selection",
            },
        }

        canon_proposed = service.build_canonical_rule(proposed)
        canon_candidate = service.build_canonical_rule(candidate)
        jaccard = service.compute_atom_jaccard(canon_proposed, canon_candidate)

        assert jaccard > 0.0, (
            f"Cross-field exe detection should produce positive jaccard via soft fallback, got {jaccard}"
        )
        # Soft jaccard is dampened by 0.5, so should be less than what a direct match gives
        assert jaccard <= 0.5, f"Soft jaccard should be <= 0.5 due to dampening, got {jaccard}"

    def test_exact_field_match_preferred_over_soft(self):
        """When exact atoms intersect, soft fallback should not activate (jaccard > 0.5)."""
        from src.services.sigma_novelty_service import SigmaNoveltyService

        service = SigmaNoveltyService()

        # Both use Image field — exact atom match
        proposed = {
            "title": "Test Exact Match",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"Image|endswith": "\\cmd.exe"},
                "condition": "selection",
            },
        }
        candidate = {
            "title": "Same Image Field",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"Image|endswith": "\\cmd.exe"},
                "condition": "selection",
            },
        }

        canon_proposed = service.build_canonical_rule(proposed)
        canon_candidate = service.build_canonical_rule(candidate)
        jaccard = service.compute_atom_jaccard(canon_proposed, canon_candidate)

        assert jaccard > 0.5, f"Exact atom match should give high jaccard, got {jaccard}"

    def test_no_shared_exe_value_returns_zero(self):
        """Different executables in different fields should return 0 jaccard."""
        from src.services.sigma_novelty_service import SigmaNoveltyService

        service = SigmaNoveltyService()

        rule_a = {
            "title": "Rule A",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"Image|endswith": "\\cmd.exe"},
                "condition": "selection",
            },
        }
        rule_b = {
            "title": "Rule B",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"ParentImage|endswith": "\\powershell.exe"},
                "condition": "selection",
            },
        }

        canon_a = service.build_canonical_rule(rule_a)
        canon_b = service.build_canonical_rule(rule_b)
        jaccard = service.compute_atom_jaccard(canon_a, canon_b)

        assert jaccard == 0.0, f"Different exe values in different fields should give 0 jaccard, got {jaccard}"
