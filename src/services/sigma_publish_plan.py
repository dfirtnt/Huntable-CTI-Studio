"""Publish readiness for a batch of queued Sigma rules: normalized YAML plus destination path.

Used by the submit-pr preflight (dry run), by submit-pr itself (which persists the
normalized YAML to the queue row before the CI-parity check, so what is checked is what is
published), and by :class:`~src.services.sigma_pr_service.SigmaPRService` to place files.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from src.services.sigma_publish_layout import (
    RuleLayout,
    RuleLayoutError,
    RulePlacement,
    assign_filenames,
    index_repository_filenames,
    load_rule_layout,
    place_rule,
)
from src.services.sigma_publish_normalizer import normalize_rule_yaml


@dataclass(frozen=True)
class PublishCandidate:
    key: Any  # queue id (or any caller key)
    rule_yaml: str
    origin: str = "generated"
    attribution: str | None = None


@dataclass
class PublishAssessment:
    key: Any
    rule_yaml: str
    changes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    relative_path: PurePosixPath | None = None
    sigma_id: str | None = None
    title: str | None = None

    @property
    def ready(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.key,
            "title": self.title,
            "path": str(self.relative_path) if self.relative_path else None,
            "changes": self.changes,
            "problems": self.problems,
            "warnings": self.warnings,
        }


def _placement(rule: dict[str, Any], layout: RuleLayout) -> tuple[RulePlacement | None, str | None]:
    try:
        return place_rule(rule, layout), None
    except RuleLayoutError as exc:
        return None, str(exc)


def assess_for_publish(
    candidates: Iterable[PublishCandidate],
    repo_path: Path,
    *,
    canonical_author: str,
    normalize: bool = True,
    today: date | None = None,
    layout: RuleLayout | None = None,
) -> list[PublishAssessment]:
    """Normalize (optionally) and place every candidate. Nothing is written anywhere."""
    layout = layout or load_rule_layout(repo_path)
    assessments: list[PublishAssessment] = []
    placements: dict[str, RulePlacement] = {}
    owners: dict[str, PublishAssessment] = {}
    for candidate in candidates:
        if normalize:
            result = normalize_rule_yaml(
                candidate.rule_yaml,
                origin=candidate.origin,
                canonical_author=canonical_author,
                attribution=candidate.attribution,
                today=today,
            )
            assessment = PublishAssessment(
                candidate.key, result.rule_yaml, changes=result.changes, problems=list(result.problems)
            )
            rule = result.rule
        else:
            assessment = PublishAssessment(candidate.key, candidate.rule_yaml)
            try:
                loaded = yaml.safe_load(candidate.rule_yaml)
            except yaml.YAMLError as exc:
                loaded = None
                assessment.problems.append(f"YAML does not parse: {str(exc).splitlines()[0]}")
            rule = loaded if isinstance(loaded, dict) else None
        assessments.append(assessment)
        if not isinstance(rule, dict):
            if not assessment.problems:
                assessment.problems.append("Expected exactly one Sigma rule mapping in the YAML")
            continue
        assessment.title = rule.get("title") if isinstance(rule.get("title"), str) else None
        sigma_id = rule.get("id")
        if not isinstance(sigma_id, str) or not sigma_id.strip():
            assessment.problems.append("Rule has no id")
            continue
        assessment.sigma_id = sigma_id.strip()
        placement, error = _placement(rule, layout)
        if error or placement is None:
            assessment.problems.append(error or "Rule placement could not be determined")
            continue
        assessment.warnings.extend(placement.warnings)
        if assessment.sigma_id in owners:
            assessment.problems.append(
                f"Rule id {assessment.sigma_id} is also used by queued rule {owners[assessment.sigma_id].key}"
            )
            continue
        owners[assessment.sigma_id] = assessment
        if assessment.ready:
            placements[assessment.sigma_id] = placement

    if placements:
        existing = index_repository_filenames(repo_path, layout)
        try:
            paths = assign_filenames(placements, existing)
        except RuleLayoutError as exc:
            for sigma_id in placements:
                owners[sigma_id].problems.append(str(exc))
        else:
            for sigma_id, path in paths.items():
                owners[sigma_id].relative_path = path
    return assessments
