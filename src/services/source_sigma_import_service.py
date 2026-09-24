"""Deterministic import of publisher-authored Sigma rules from article content.

The source text is data, never a prompt. This module never calls an LLM and never
repairs, formats, deduplicates, or otherwise rewrites a publisher rule.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database.models import ArticleTable, SigmaRuleQueueTable
from src.services.sigma_matching_service import SigmaMatchingService

logger = logging.getLogger(__name__)

POLICY_RELATIVE_PATH = Path(".huntable/source-rule-license-policy.yml")
SOURCE_ORIGIN = "source_provided"
LOCAL_REVIEW_ONLY = "local_review_only"

_TITLE_LINE = re.compile(r"(?m)^title:[ \t]*\S.*$")
_LICENSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "CC-BY-NC-4.0",
        re.compile(
            r"(?i)\b(?:CC[- ]BY[- ]NC(?:[- ](?:SA[- ]?)?4\.0)?|Creative Commons Attribution[- ]NonCommercial(?:[- ]ShareAlike)?(?: 4\.0)?)\b"
        ),
    ),
    (
        "CC-BY-4.0",
        re.compile(r"(?i)\b(?:CC[- ]BY[- ]4\.0|Creative Commons Attribution 4\.0(?: International)?)\b"),
    ),
)


@dataclass(frozen=True)
class SourceSigmaCandidate:
    """One byte-preserved Sigma mapping found in an article."""

    yaml_text: str
    parsed: dict[str, Any]
    start: int
    end: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.yaml_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceSigmaRejection:
    """One title-led candidate that could not be accepted as complete Sigma."""

    start: int
    end: int
    reason: str


@dataclass(frozen=True)
class SourceSigmaScanResult:
    """Accepted rules and auditable rejection reasons from one article."""

    candidates: tuple[SourceSigmaCandidate, ...]
    rejections: tuple[SourceSigmaRejection, ...]


@dataclass(frozen=True)
class LicenseEvidence:
    license_id: str | None
    evidence: str | None
    start: int | None
    end: int | None


@dataclass(frozen=True)
class DeliveryDecision:
    eligible: bool
    reason: str
    basis: str


@dataclass(frozen=True)
class ImportResult:
    discovered: int
    imported: int
    duplicates: int
    rejected: int
    queue_ids: tuple[int, ...]


def _is_sigma_mapping(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        return False
    if not isinstance(value.get("logsource"), dict) or not value["logsource"]:
        return False
    detection = value.get("detection")
    return isinstance(detection, dict) and isinstance(detection.get("condition"), str)


def _sigma_rejection_reason(value: Any) -> str:
    if not isinstance(value, dict):
        return "non_mapping_document"
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        return "missing_title"
    if not isinstance(value.get("logsource"), dict) or not value["logsource"]:
        return "invalid_or_missing_logsource"
    detection = value.get("detection")
    if not isinstance(detection, dict):
        return "invalid_or_missing_detection"
    if not isinstance(detection.get("condition"), str):
        return "missing_detection_condition"
    return "ambiguous_or_incomplete_document"


def scan_sigma_rules_with_diagnostics(content: str) -> SourceSigmaScanResult:
    """Return exact Sigma substrings plus one rejection reason per failed title block.

    Articles commonly place unfenced YAML between prose paragraphs. For each
    top-level ``title:`` line, test newline boundaries up to the next title and
    retain the longest prefix that parses as exactly one valid Sigma mapping.
    This deliberately rejects fragments, sequences/scalars, and multi-document
    blocks while retaining optional fields after ``detection`` such as ``level``.
    """
    if not content:
        return SourceSigmaScanResult((), ())
    starts = [match.start() for match in _TITLE_LINE.finditer(content)]
    candidates: list[SourceSigmaCandidate] = []
    rejections: list[SourceSigmaRejection] = []
    for index, start in enumerate(starts):
        limit = starts[index + 1] if index + 1 < len(starts) else len(content)
        newline_ends = [match.end() for match in re.finditer(r"\r?\n", content[start:limit])]
        endpoints = [start + relative_end for relative_end in newline_ends]
        if limit not in endpoints:
            endpoints.append(limit)

        best: SourceSigmaCandidate | None = None
        parsed_values: list[Any] = []
        for end in endpoints:
            raw = content[start:end]
            try:
                parsed = yaml.safe_load(raw)
            except yaml.YAMLError:
                continue
            parsed_values.append(parsed)
            if _is_sigma_mapping(parsed):
                best = SourceSigmaCandidate(raw, parsed, start, end)
        if best is not None:
            candidates.append(best)
        else:
            reason = _sigma_rejection_reason(parsed_values[-1]) if parsed_values else "invalid_or_incomplete_yaml"
            rejections.append(SourceSigmaRejection(start=start, end=limit, reason=reason))
    return SourceSigmaScanResult(tuple(candidates), tuple(rejections))


def scan_sigma_rules(content: str) -> list[SourceSigmaCandidate]:
    """Compatibility wrapper returning only accepted source Sigma rules."""
    return list(scan_sigma_rules_with_diagnostics(content).candidates)


def detect_license(content: str, candidate: SourceSigmaCandidate) -> LicenseEvidence:
    """Classify explicit license evidence, preferring rule-local evidence."""
    windows = ((candidate.yaml_text, candidate.start), (content, 0))
    for window, base in windows:
        for license_id, pattern in _LICENSE_PATTERNS:
            match = pattern.search(window)
            if match:
                return LicenseEvidence(license_id, match.group(0), base + match.start(), base + match.end())
    return LicenseEvidence(None, None, None, None)


def load_destination_license_allowlist(repo_path: Path) -> set[str]:
    """Load the destination's explicit redistribution allowlist; fail closed."""
    policy_path = Path(repo_path) / POLICY_RELATIVE_PATH
    try:
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Source-rule license policy unavailable at %s: %s", policy_path, exc)
        return set()
    entries = policy.get("allowed_licenses", []) if isinstance(policy, dict) else []
    allowed: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            allowed.add(entry.strip().upper())
        elif isinstance(entry, dict) and entry.get("id"):
            allowed.add(str(entry["id"]).strip().upper())
    return allowed


def evaluate_source_rule_delivery(rule: SigmaRuleQueueTable, repo_path: Path) -> DeliveryDecision:
    """Re-evaluate source delivery permission immediately before approval/PR."""
    if getattr(rule, "rule_origin", "generated") != SOURCE_ORIGIN:
        return DeliveryDecision(True, "Generated rule follows the existing delivery workflow.", "generated")
    if (
        getattr(rule, "source_permission_granted_by", None)
        and getattr(rule, "source_permission_basis", None)
        and getattr(rule, "source_permission_granted_at", None)
    ):
        return DeliveryDecision(True, "Source-specific permission is recorded.", "source_permission")
    license_id = (getattr(rule, "declared_license", None) or "").strip().upper()
    if not license_id:
        return DeliveryDecision(False, "No explicit source license or permission is recorded.", "missing_license")
    if license_id.startswith("CC-BY-NC"):
        return DeliveryDecision(False, "Non-commercial source licenses are local-review only.", "noncommercial")
    if license_id in load_destination_license_allowlist(Path(repo_path)):
        return DeliveryDecision(True, f"{license_id} is allowlisted by the destination repository.", "allowlist")
    return DeliveryDecision(False, f"{license_id} is not allowlisted by the destination repository.", "not_allowlisted")


def _similarity_context(db_session: Session, rule: dict[str, Any]) -> dict[str, Any]:
    """Compute reviewer-only similarity context without gating the import."""
    result = SigmaMatchingService(db_session).assess_rule_novelty(proposed_rule=rule, threshold=0.0)
    matches = result.get("matches", [])
    scores = [float(match.get("similarity", 0.0)) for match in matches]
    return {
        "similarity_scores": matches[:10],
        "max_similarity": max(scores) if scores else 0.0,
        "behavioral_matches_found": result.get("behavioral_matches_found", 0),
        "total_candidates_evaluated": result.get("total_candidates_evaluated", 0),
        "canonical_class": result.get("canonical_class"),
    }


def import_source_sigma_rules(
    db_session: Session,
    article: ArticleTable,
    repo_path: Path,
    *,
    commit: bool = True,
) -> ImportResult:
    """Import every valid source rule from one article, idempotently."""
    scan = scan_sigma_rules_with_diagnostics(article.content)
    candidates = scan.candidates
    imported_ids: list[int] = []
    duplicates = 0
    rejected = len(scan.rejections)
    for rejection in scan.rejections:
        logger.warning(
            "Rejected source Sigma candidate in article %s at %d:%d: %s",
            article.id,
            rejection.start,
            rejection.end,
            rejection.reason,
        )
    for candidate in candidates:
        source_rule_id = candidate.parsed.get("id")
        if not isinstance(source_rule_id, str) or not source_rule_id.strip():
            rejected += 1
            logger.warning("Rejected source Sigma candidate in article %s: missing string id", article.id)
            continue
        existing = (
            db_session.query(SigmaRuleQueueTable)
            .filter(
                (SigmaRuleQueueTable.source_content_sha256 == candidate.sha256)
                | (
                    (SigmaRuleQueueTable.source_url == article.canonical_url)
                    & (SigmaRuleQueueTable.source_rule_id == source_rule_id.strip())
                )
            )
            .first()
        )
        if existing:
            duplicates += 1
            continue

        license_evidence = detect_license(article.content, candidate)
        metadata = {
            "title": candidate.parsed.get("title"),
            "description": candidate.parsed.get("description"),
            "tags": candidate.parsed.get("tags", []),
            "level": candidate.parsed.get("level"),
            "status": candidate.parsed.get("status", "experimental"),
            "source_yaml_immutable": True,
        }
        similarity = _similarity_context(db_session, candidate.parsed)
        metadata["canonical_class"] = similarity["canonical_class"]
        metadata["logsource_unresolved"] = similarity["canonical_class"] is None
        metadata["logsource_lint_failures"] = ["unresolved_logsource"] if similarity["canonical_class"] is None else []

        provisional = SigmaRuleQueueTable(
            article_id=article.id,
            workflow_execution_id=None,
            rule_yaml=candidate.yaml_text,
            rule_metadata=metadata,
            rule_origin=SOURCE_ORIGIN,
            source_url=article.canonical_url,
            source_rule_id=source_rule_id.strip(),
            source_content_sha256=candidate.sha256,
            source_extraction_start=candidate.start,
            source_extraction_end=candidate.end,
            declared_license=license_evidence.license_id,
            license_evidence=license_evidence.evidence,
            license_evidence_start=license_evidence.start,
            license_evidence_end=license_evidence.end,
            attribution=str(candidate.parsed.get("author") or ", ".join(article.authors or []) or "Publisher"),
            similarity_scores=similarity["similarity_scores"],
            max_similarity=similarity["max_similarity"],
            behavioral_matches_found=similarity["behavioral_matches_found"],
            total_candidates_evaluated=similarity["total_candidates_evaluated"],
            status="pending",
        )
        decision = evaluate_source_rule_delivery(provisional, repo_path)
        provisional.status = "pending" if decision.eligible else LOCAL_REVIEW_ONLY
        metadata["delivery_eligibility_reason"] = decision.reason
        metadata["delivery_eligibility_basis"] = decision.basis
        try:
            with db_session.begin_nested():
                db_session.add(provisional)
                db_session.flush()
        except IntegrityError:
            duplicates += 1
            continue
        imported_ids.append(provisional.id)
    if commit:
        db_session.commit()
    return ImportResult(len(candidates), len(imported_ids), duplicates, rejected, tuple(imported_ids))
