"""The Save-Anyway override is a two-sided contract; pin both sides together.

``PUT /api/workflow/config`` refuses a payload whose prompts would make an agent fail
silently at runtime. The escape hatch is a single field the browser sets only after the
operator confirms the warning dialog. Rename or drop it on either side and the failure is
quiet in the worst way: the confirm still appears, the operator still clicks "Save
Anyway", and the save comes back 400 -- or, worse, the field is accepted under a name the
server never checks and every save skips validation.

The API tests cover the server behavior. This covers the wiring between the two files,
which no browser-level test currently exercises.
"""

from pathlib import Path

import pytest

from src.web.routes.workflow_config import WorkflowConfigUpdate

pytestmark = pytest.mark.unit

_OVERRIDE_FIELD = "allow_prompt_warnings"
_CONFIG_JS = Path(__file__).resolve().parents[2] / "src" / "web" / "static" / "js" / "workflow" / "config.js"


def test_server_exposes_the_override_field_and_defaults_it_off():
    """Defaulting to True would silently disable the refusal for every caller."""
    field = WorkflowConfigUpdate.model_fields[_OVERRIDE_FIELD]

    assert field.default is False


def test_a_plain_save_does_not_set_the_override():
    """The field must be opt-in per save, never a constant on the payload."""
    assert WorkflowConfigUpdate().allow_prompt_warnings is False


def test_the_browser_sets_the_override_under_the_name_the_server_reads():
    source = _CONFIG_JS.read_text()

    assert f"formData.{_OVERRIDE_FIELD} = true" in source, (
        f"config.js no longer sets {_OVERRIDE_FIELD}; 'Save Anyway' will be refused with a 400"
    )


def test_the_override_is_set_only_after_the_operator_confirms():
    """It must sit inside the warnings branch, after the cancel early-return.

    Hoisting it above that return would send the override on every save, including the
    ones the operator cancelled.
    """
    source = _CONFIG_JS.read_text()

    cancel_return = source.index("Save cancelled - fix the prompt issues above")
    override = source.index(f"formData.{_OVERRIDE_FIELD} = true")

    assert override > cancel_return, "the override is set before the cancel branch returns"
