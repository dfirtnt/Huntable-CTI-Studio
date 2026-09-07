"""The required-check contexts in scripts/main_branch_protection.json must be real job names.

GitHub evaluates required status checks by *context string*, which for Actions
is the job's ``name:``. Renaming a job in a workflow silently un-gates it: the
old context never reports, and -- worse -- a PR to a locked-then-unlocked
``main`` blocks forever waiting for a check that no longer exists. This pins
every listed context to a job that still exists, and every gate-worthy job
to the list, so the two cannot drift apart unnoticed.

No server or network needed -- all assertions are against files on disk.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PROTECTION = REPO_ROOT / "scripts" / "main_branch_protection.json"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Jobs that never run on a pull_request event, so they can never be PR gates.
NOT_A_GATE = {
    "Deploy to GitHub Pages",  # docs.yml: push to main/europa-dev only
    "Pages smoke",  # docs-smoke.yml: workflow_run after the deploy
    "claude",  # claude.yml: issue / review-comment triggered
    "Verify tag consistency",  # release.yml: tag push
    "Create GitHub Release",  # release.yml: tag push
}


def _job_names() -> dict[str, str]:
    """job display name -> workflow file."""
    names: dict[str, str] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job_id, job in (doc.get("jobs") or {}).items():
            names[job.get("name") or job_id] = wf.name
    return names


def _contexts() -> list[str]:
    return json.loads(PROTECTION.read_text(encoding="utf-8"))["required_status_checks"]["contexts"]


def test_protection_json_shape():
    data = json.loads(PROTECTION.read_text(encoding="utf-8"))
    assert data["required_status_checks"]["strict"] is True
    assert data["enforce_admins"] is True
    assert data["allow_force_pushes"] is False
    assert data["allow_deletions"] is False
    assert "lock_branch" in data, "lock/unlock scripts toggle this key; it must exist"
    assert len(_contexts()) == len(set(_contexts())), "duplicate contexts"


def test_every_required_context_is_a_current_job_name():
    jobs = _job_names()
    missing = [c for c in _contexts() if c not in jobs]
    assert not missing, f"required contexts with no matching job name in .github/workflows: {missing}"


def test_every_pr_gate_job_is_required():
    """Adding a CI job without listing it here is the drift this exists to catch."""
    jobs = _job_names()
    unlisted = sorted(set(jobs) - set(_contexts()) - NOT_A_GATE)
    assert not unlisted, (
        f"jobs not in main_branch_protection.json and not in NOT_A_GATE: {unlisted} "
        "-- either add them as required contexts or list them in NOT_A_GATE with a reason"
    )
