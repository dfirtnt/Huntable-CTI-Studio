"""Dependency contracts for role-specific Docker runtime environments."""

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]


def test_langfuse_is_available_to_the_web_runtime():
    """The web image installs base dependencies without the workflow group."""
    with (_REPO / "pyproject.toml").open("rb") as fh:
        project = tomllib.load(fh)

    dependencies = set(project["project"]["dependencies"])
    workflow_dependencies = set(project["dependency-groups"]["workflow"])

    langfuse_pins = {d for d in dependencies if d.startswith("langfuse==")}
    assert langfuse_pins, f"langfuse must be pinned in base dependencies, got {dependencies}"
    assert not {d for d in workflow_dependencies if d.startswith("langfuse==")}
