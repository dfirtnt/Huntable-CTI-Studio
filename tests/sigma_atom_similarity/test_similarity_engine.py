"""Similarity engine: full result shape, no_shared_atoms, determinism."""

import json

from sigma_similarity.similarity_engine import compare_rules


def test_full_result_shape(rule_windows_process_creation, rule_windows_process_creation_two):
    r1 = rule_windows_process_creation
    r2 = rule_windows_process_creation_two
    result = compare_rules(r1, r2)
    assert hasattr(result, "similarity")
    assert hasattr(result, "jaccard")
    assert hasattr(result, "containment_factor")
    assert hasattr(result, "filter_penalty")
    assert hasattr(result, "surface_score_a")
    assert hasattr(result, "surface_score_b")
    assert hasattr(result, "canonical_class")
    assert "reason_flags" in result.explanation
    assert "overlap_ratio_a" in result.explanation
    assert "overlap_ratio_b" in result.explanation
    assert 0 <= result.similarity <= 1
    assert result.surface_score_a >= 1
    assert result.surface_score_b >= 1


def test_no_shared_atoms_returns_full_result_with_reason():
    r1 = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"Image": "a.exe"}, "condition": "selection"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"Image": "b.exe"}, "condition": "selection"},
    }
    result = compare_rules(r1, r2)
    assert result.similarity == 0.0
    assert "no_shared_atoms" in result.explanation["reason_flags"]
    assert result.surface_score_a >= 1
    assert result.surface_score_b >= 1


def test_determinism_identical_json(rule_windows_process_creation, rule_with_and):
    r1 = rule_windows_process_creation
    r2 = rule_with_and
    a = compare_rules(r1, r2)
    b = compare_rules(r1, r2)
    out_a = json.dumps(a.to_dict(), sort_keys=True, separators=(",", ":"))
    out_b = json.dumps(b.to_dict(), sort_keys=True, separators=(",", ":"))
    assert out_a == out_b


# ── Regression: vssadmin shadow copy deletion (2026-04-08) ────────────────────
# The original bug report: Similarity Search returned zero for a vssadmin shadow
# copy deletion rule vs SigmaHQ's equivalent. Root cause was case-sensitive
# field resolution and value comparison in atom_extractor.


class TestVssadminRegressionCase:
    """End-to-end regression for the vssadmin similarity search bug."""

    @staticmethod
    def _vssadmin_proposed():
        """LLM-generated rule using lowercase fields (the bug trigger)."""
        return {
            "title": "Shadow Copy Deletion Using Vssadmin",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "parent_image|endswith": "\\cmd.exe",
                    "image|endswith": "\\vssadmin.exe",
                    "command_line|contains|all": ["Delete", "Shadows", "/all"],
                },
                "condition": "selection",
            },
        }

    @staticmethod
    def _vssadmin_sigmahq():
        """SigmaHQ-style rule using PascalCase fields and lowercase values."""
        return {
            "title": "Shadow Copies Deletion Via Vssadmin",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection_img": {
                    "Image|endswith": "\\vssadmin.exe",
                    "OriginalFileName": "VSSADMIN.EXE",
                },
                "selection_cli": {
                    "CommandLine|contains|all": ["delete", "shadows"],
                },
                "condition": "selection_img and selection_cli",
            },
        }

    def test_nonzero_similarity(self):
        """Proposed and SigmaHQ vssadmin rules MUST have positive similarity."""
        result = compare_rules(self._vssadmin_proposed(), self._vssadmin_sigmahq())
        assert result.similarity > 0, (
            f"Expected positive similarity, got {result.similarity}. "
            f"reason_flags={result.explanation.get('reason_flags')}"
        )

    def test_jaccard_above_threshold(self):
        """Jaccard must be >= 0.3 (shared: vssadmin.exe, delete, shadows)."""
        result = compare_rules(self._vssadmin_proposed(), self._vssadmin_sigmahq())
        assert result.jaccard >= 0.3, (
            f"Jaccard {result.jaccard} is too low — case-sensitive atom matching may have regressed"
        )

    def test_no_reason_flags(self):
        """Should not have class_mismatch or no_shared_atoms flags."""
        result = compare_rules(self._vssadmin_proposed(), self._vssadmin_sigmahq())
        flags = result.explanation.get("reason_flags", [])
        assert "canonical_class_mismatch" not in flags
        assert "no_shared_atoms" not in flags


class TestCaseMismatchRegression:
    """Rules differing only in field/value casing must produce identical similarity."""

    def test_identical_rules_different_field_casing(self):
        """Same detection logic, PascalCase vs snake_case fields."""
        pascal = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"Image|endswith": "\\cmd.exe", "CommandLine|contains": "whoami"},
                "condition": "selection",
            },
        }
        snake = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"image|endswith": "\\cmd.exe", "command_line|contains": "whoami"},
                "condition": "selection",
            },
        }
        result = compare_rules(pascal, snake)
        assert result.jaccard == 1.0, (
            f"Same detection in PascalCase vs snake_case should have Jaccard=1.0, got {result.jaccard}"
        )

    def test_identical_rules_different_value_casing(self):
        """Same detection logic, different value casing (Delete vs delete)."""
        upper = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"CommandLine|contains|all": ["Delete", "Shadows"]},
                "condition": "selection",
            },
        }
        lower = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"CommandLine|contains|all": ["delete", "shadows"]},
                "condition": "selection",
            },
        }
        result = compare_rules(upper, lower)
        assert result.jaccard == 1.0, (
            f"Same contains|all values with different casing should have Jaccard=1.0, got {result.jaccard}"
        )
