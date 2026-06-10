"""
API routes for SIGMA rule A/B pairwise comparison.

Provides POST /api/sigma-ab-test/compare and /compare-to-repository.
"""

import logging
import re
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.database.manager import DatabaseManager
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_novelty_service import NoveltyLabel, SigmaNoveltyService, classify_match_novelty
from src.services.sigma_semantic_precompute import precompute_semantic_fields
from src.services.similarity_serialization import serialize_similarity_match

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-ab-test", tags=["sigma-ab-test"])


def _extract_yaml_block(text: str) -> str:
    """Extract YAML from text (strip markdown code fences, leading prose)."""
    if not text or not text.strip():
        return text.strip() if text else ""
    text = text.strip()
    # Handle markdown code fences with optional "yaml" and support CRLF/newline variants.
    # Use plain string search (no backtracking) to avoid ReDoS on crafted input.
    fence_open = re.match(r"```(?:[a-z0-9]+)?[ \t]*\r?\n", text, re.IGNORECASE)
    if fence_open:
        content_start = fence_open.end()
        fence_close = text.find("\n```", content_start)
        if fence_close == -1:
            fence_close = text.find("```", content_start)
        content = text[content_start:fence_close].strip() if fence_close != -1 else text[content_start:].strip()
        return content
    for start in ("title:", "id:", "logsource:", "detection:"):
        idx = text.find(start)
        if idx != -1:
            # If the YAML is followed by another code fence / prose, truncate at the next fence.
            candidate = text[idx:].strip()
            candidate = re.split(r"```", candidate, maxsplit=1)[0].strip()
            return candidate
    # No obvious YAML boundary markers; fall back to raw content.
    return text.strip()


class CompareRequest(BaseModel):
    """Request model for pairwise rule comparison."""

    rule_a: str
    rule_b: str


class CompareToRepositoryRequest(BaseModel):
    """Request model for comparing a rule against the repository."""

    rule: str


def _parse_and_validate_rule(raw: str, field: str) -> dict[str, Any]:
    """Parse YAML, validate detection, return normalized rule dict."""
    content = _extract_yaml_block(raw)
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail=f"Rule {field} is empty or has no content")
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML in {field}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail=f"Rule {field} must be a YAML object")
    if not data.get("detection"):
        raise HTTPException(status_code=400, detail=f"Rule {field} must have a detection section")
    return data


def _classify_pairwise_novelty(weighted_sim: float) -> str:
    """Classify novelty from pairwise similarity (0-1)."""
    if weighted_sim >= 0.95:
        return NoveltyLabel.DUPLICATE
    if weighted_sim >= 0.80:
        return NoveltyLabel.SIMILAR
    return NoveltyLabel.NOVEL


@router.post("/compare")
async def compare_rules(compare_request: CompareRequest):
    """
    Compare two SIGMA rules pairwise.

    Returns similarity, novelty label, and atom-level explainability.
    """
    rule_a_data = _parse_and_validate_rule(compare_request.rule_a, "rule_a")
    rule_b_data = _parse_and_validate_rule(compare_request.rule_b, "rule_b")

    service = SigmaNoveltyService(db_session=None)

    # Deterministic-first: extract BOTH rules with the same precompute
    # (sigma_similarity package) extractor used at index time, then score via
    # the shared precomputed-atom scorer. One extractor, two timings -- the
    # in-src parse below is only a fallback for rules the package cannot
    # classify, so /compare cannot diverge from stored-atom scoring
    # (filter-polarity bug: `not N of filter_*` atoms leaked into the
    # positive jaccard and produced false-NOVEL verdicts).
    sem_a = precompute_semantic_fields(rule_a_data)
    sem_b = precompute_semantic_fields(rule_b_data)
    if sem_a is not None and sem_b is not None:
        det_match = service.compare_precomputed_semantics(sem_a, sem_b)
        if det_match is not None:
            # Phase-2 single source of truth for novelty thresholds, same as
            # every stored-atom surface.
            det_match["novelty_label"] = classify_match_novelty(det_match)
            return {"success": True, **serialize_similarity_match(det_match)}

    canonical_a = service.build_canonical_rule(rule_a_data)
    canonical_b = service.build_canonical_rule(rule_b_data)

    atom_jaccard = service.compute_atom_jaccard(canonical_a, canonical_b)
    logic_similarity = service.compute_logic_shape_similarity(canonical_a, canonical_b)
    _, proposed_service = service.normalize_logsource(rule_a_data.get("logsource", {}))
    _, candidate_service = service.normalize_logsource(rule_b_data.get("logsource", {}))
    service_penalty = service._compute_service_penalty(proposed_service, candidate_service)
    filter_penalty = service._compute_filter_penalty(canonical_a, canonical_b)

    weighted_sim = service.compute_weighted_similarity(
        atom_jaccard, logic_similarity, service_penalty=service_penalty, filter_penalty=filter_penalty
    )

    explainability = service.generate_explainability(canonical_a, canonical_b, {})

    novelty_label = _classify_pairwise_novelty(weighted_sim)

    # Project onto the unified canonical contract (Phase 1). /compare computes
    # metrics directly rather than via assess_rule_novelty, so assemble a match
    # dict and serialize it for a shape consistent with every other surface.
    serialized = serialize_similarity_match(
        {
            "similarity": weighted_sim,
            "novelty_label": novelty_label,
            "atom_jaccard": atom_jaccard,
            "logic_shape_similarity": logic_similarity,
            "shared_atoms": explainability["shared_atoms"],
            "added_atoms": explainability["added_atoms"],
            "removed_atoms": explainability["removed_atoms"],
            "service_penalty": service_penalty,
            "filter_penalty": filter_penalty,
        }
    )
    return {"success": True, **serialized}


@router.post("/compare-to-repository")
async def compare_rule_to_repository(compare_request: CompareToRepositoryRequest):
    """
    Compare a SIGMA rule against the repository (behavioral atom set-math via
    assess_rule_novelty; proposed-rule atoms come from the same precompute
    extractor used at index time).
    """
    rule_data = _parse_and_validate_rule(compare_request.rule, "rule")

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    try:
        matching_service = SigmaMatchingService(db_session)
        normalized = {
            "title": rule_data.get("title", ""),
            "description": rule_data.get("description", ""),
            "tags": rule_data.get("tags", []),
            "logsource": rule_data.get("logsource", {}),
            "detection": rule_data.get("detection", {}),
            "level": rule_data.get("level"),
            "status": rule_data.get("status", "experimental"),
        }
        result = matching_service.assess_rule_novelty(proposed_rule=normalized, threshold=0.0)
        matches = result.get("matches", [])[:20]
        return {
            "success": True,
            "matches": [serialize_similarity_match(m) for m in matches],
        }
    finally:
        db_session.close()
