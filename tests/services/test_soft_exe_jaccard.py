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

    def test_mixed_case_field_is_recognized(self):
        """Mixed-case field names (e.g. PascalCase) should resolve via case-insensitive lookup.

        Regression guard for the same case-sensitivity class of bug fixed on the
        class-method fallback in ``SigmaNoveltyService.compute_atom_jaccard``
        (case-insensitive soft-exe jaccard, 2026-04-10). The module-level helper
        is sometimes invoked with non-normalized atoms (direct tests, future
        callers, legacy precomputed entries) and must not silently drop them.
        """
        assert _extract_exe_value("Image|endswith|endswith|/cmd.exe") == "/cmd.exe"
        assert _extract_exe_value("ParentImage|endswith|endswith|/powershell.exe") == "/powershell.exe"
        assert _extract_exe_value("CommandLine|contains|contains|whoami") == "whoami"
        assert _extract_exe_value("Process.Image|endswith|endswith|/vssadmin.exe") == "/vssadmin.exe"

    def test_mixed_case_non_process_field_still_returns_none(self):
        """Case-insensitive lookup must not over-match non-process fields."""
        assert _extract_exe_value("EventID|eq||4688") is None
        assert _extract_exe_value("LogName|eq||Security") is None


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

    def test_rundll32_deterministic_atoms_regression(self):
        """Regression: deterministic-path atoms for the rundll32 scenario.

        Reproduces the exact atom strings the deterministic engine would produce
        for the proposed rule (Image + ParentImage) vs the SigmaHQ rule (CommandLine).
        """
        A1 = {
            "process.parent_image|endswith|literal|\\services.exe",
            "process.image|endswith|literal|\\rundll32.exe",
        }
        A2 = {
            "process.command_line|endswith|literal|\\rundll32.exe",
            'process.command_line|endswith|literal|\\rundll32.exe"',
            "process.command_line|endswith|literal|\\rundll32",
        }
        union = A1 | A2
        result = _soft_exe_jaccard_from_atom_strings(A1, A2, union)
        # \rundll32.exe shared across process.image and process.command_line
        assert result > 0.0, "Rundll32 deterministic atoms must produce positive soft jaccard"
        assert result == pytest.approx((1 / 5) * 0.5)  # 1 shared / 5 union * 0.5 = 0.10

    def test_mixed_case_atoms_still_fire_soft_fallback(self):
        """Mixed-case precomputed atoms must still produce a soft match.

        Upstream ``_normalize_atom_identity`` normally lowercases atoms before
        they reach this helper, but a defensive case-insensitive field lookup
        inside ``_extract_exe_value`` keeps the soft fallback robust for any
        caller path that skips normalization (regression guard, 2026-04-10).
        """
        A1 = {"Image|endswith|endswith|/vssadmin.exe"}
        A2 = {"CommandLine|contains|contains|/vssadmin.exe"}
        union = A1 | A2
        result = _soft_exe_jaccard_from_atom_strings(A1, A2, union)
        assert result > 0.0, "Mixed-case fields must still produce a positive soft jaccard"
        assert result == pytest.approx((1 / 2) * 0.5)


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

    def test_rundll32_services_exe_regression(self):
        """Regression: the exact scenario from rule 282 that triggered this fix.

        Proposed rule: services.exe spawning rundll32.exe (Image + ParentImage + empty CommandLine).
        SigmaHQ rule: CommandLine ending with bare rundll32.exe path (CobaltStrike beacon pattern).

        These rules detect the same threat behavior (rundll32 with no args) but use
        completely different field/operator combinations. Before the soft matching fix,
        atom jaccard was 0.0. After, the shared '\\rundll32.exe' value across Image
        and CommandLine fields produces non-zero jaccard.
        """
        from src.services.sigma_novelty_service import SigmaNoveltyService

        service = SigmaNoveltyService()

        # Proposed rule from Hunter's Ledger (OpenStrike Expanded Toolkit)
        proposed = {
            "title": "Suspicious Rundll32 Execution Without Arguments via Services",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "ParentImage|endswith": "\\services.exe",
                    "Image|endswith": "\\rundll32.exe",
                    "CommandLine": "",
                },
                "condition": "selection",
            },
        }

        # SigmaHQ rule 1775e15e: Rundll32 Execution Without CommandLine Parameters
        sigmahq = {
            "title": "Rundll32 Execution Without CommandLine Parameters",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "CommandLine|endswith": [
                        "\\rundll32.exe",
                        '\\rundll32.exe"',
                        "\\rundll32",
                    ],
                },
                "filter": {
                    "ParentImage|contains": [
                        "\\AppData\\Local\\",
                        "\\Microsoft\\Edge\\",
                    ],
                },
                "condition": "selection and not filter",
            },
        }

        canon_proposed = service.build_canonical_rule(proposed)
        canon_candidate = service.build_canonical_rule(sigmahq)
        jaccard = service.compute_atom_jaccard(canon_proposed, canon_candidate)

        assert jaccard > 0.0, (
            f"Rundll32 rules with shared exe value across Image/CommandLine "
            f"must get non-zero jaccard via soft matching, got {jaccard}"
        )
        # Should be modest — cross-field dampened, and many unshared atoms
        assert jaccard < 0.25, f"Expected modest soft jaccard (<0.25) for cross-field match, got {jaccard}"

    def test_empty_commandline_atom_no_false_soft_match(self):
        """Empty CommandLine value ('') should not produce false soft matches.

        A rule with CommandLine: '' (detecting empty command lines) must not
        soft-match against a rule that also has an empty value in a different
        context. The empty string is not a meaningful executable name.
        """
        from src.services.sigma_novelty_service import SigmaNoveltyService

        service = SigmaNoveltyService()

        rule_a = {
            "title": "Empty CmdLine Rule",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"CommandLine": ""},
                "condition": "selection",
            },
        }
        rule_b = {
            "title": "Different Process Rule",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"Image|endswith": "\\svchost.exe"},
                "condition": "selection",
            },
        }

        canon_a = service.build_canonical_rule(rule_a)
        canon_b = service.build_canonical_rule(rule_b)
        jaccard = service.compute_atom_jaccard(canon_a, canon_b)

        assert jaccard == 0.0, f"Empty CommandLine value should not soft-match against a real exe, got {jaccard}"

    def test_non_process_fields_never_soft_match(self):
        """Rules using non-process fields (dns, registry, etc.) must never soft match."""
        from src.services.sigma_novelty_service import SigmaNoveltyService

        service = SigmaNoveltyService()

        rule_a = {
            "title": "DNS Rule",
            "logsource": {"category": "dns_query", "product": "windows"},
            "detection": {
                "selection": {"QueryName|endswith": ".evil.com"},
                "condition": "selection",
            },
        }
        rule_b = {
            "title": "Another DNS Rule",
            "logsource": {"category": "dns_query", "product": "windows"},
            "detection": {
                "selection": {"QueryName|contains": ".evil.com"},
                "condition": "selection",
            },
        }

        canon_a = service.build_canonical_rule(rule_a)
        canon_b = service.build_canonical_rule(rule_b)
        jaccard = service.compute_atom_jaccard(canon_a, canon_b)

        # These share the value ".evil.com" but QueryName is not a process-exe field,
        # so soft matching should NOT fire. Strict matching also fails (different ops).
        # Actually endswith vs contains → different atom keys → strict fails.
        # Soft match should also fail since QueryName not in _PROCESS_EXE_FIELDS.
        assert jaccard == 0.0, f"Non-process fields should never produce soft jaccard, got {jaccard}"
