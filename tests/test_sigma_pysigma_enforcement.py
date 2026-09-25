"""Differential regression tests for the pySigma enforcement boundary."""

import pytest

from src.services.sigma_validator import validate_sigma_rule

pytestmark = pytest.mark.unit


def _rule(detection: str, *, category: str = "process_creation", metadata: str = "") -> str:
    # id/status are required by the SigmaHQ blocking layer (identifier_existence,
    # sigmahq_status_existence), which runs after pySigma parses the rule.
    return f"""title: pySigma enforcement regression rule
id: 0b6c1f2a-3d4e-4f50-8a9b-1c2d3e4f5a6b
status: experimental
description: A sufficiently descriptive rule for the Huntable policy layer
logsource:
  category: {category}
detection:
{detection}
level: medium
{metadata}"""


@pytest.mark.parametrize(
    ("name", "detection", "error_type"),
    [
        (
            "unknown_modifier",
            "  selection:\n    Image|definitelynotreal: cmd.exe\n  condition: selection",
            "SigmaModifierError",
        ),
        (
            "malformed_condition",
            "  selection:\n    Image: cmd.exe\n  condition: selection and",
            "SigmaConditionError",
        ),
        (
            "undefined_selection",
            "  selection:\n    Image: cmd.exe\n  condition: missing_selection",
            "SigmaConditionError",
        ),
    ],
)
def test_pysigma_rejects_semantic_detection_errors(name, detection, error_type):
    result = validate_sigma_rule(_rule(detection))

    assert not result.is_valid, name
    assert result.metadata["pysigma"]["valid"] is False
    assert result.metadata["pysigma"]["errors"][0]["type"] == error_type
    assert result.errors[0].startswith(f"pySigma {error_type}:")


def test_pysigma_rejects_invalid_metadata_type():
    result = validate_sigma_rule(
        _rule(
            "  selection:\n    Image: cmd.exe\n  condition: selection",
            metadata="level: 5",
        )
    )

    assert not result.is_valid
    assert result.metadata["pysigma"]["valid"] is False
    assert result.metadata["pysigma"]["errors"][0]["type"] == "AttributeError"


def test_pysigma_allows_webserver_category_then_runs_policy_layer():
    result = validate_sigma_rule(
        _rule(
            "  selection:\n    cs-method: POST\n  condition: selection",
            category="webserver",
        )
    )

    assert result.is_valid, result.errors
    assert result.metadata["pysigma"] == {"valid": True, "errors": []}


def test_huntable_policy_remains_a_separate_quality_gate():
    result = validate_sigma_rule(
        """title: Short
logsource:
  category: webserver
detection:
  selection:
    cs-method: POST
  condition: selection
level: medium
"""
    )

    assert not result.is_valid
    assert result.metadata["pysigma"] == {"valid": True, "errors": []}
    assert any(error.startswith("Title is too short") for error in result.errors)
    assert "Rule has no description" in result.errors
