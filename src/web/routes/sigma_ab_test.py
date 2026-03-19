"""
API routes for SIGMA rule A/B pairwise comparison.

Provides POST /api/sigma-ab-test/compare and /compare-to-repository.
"""

import re
import logging
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.database.manager import DatabaseManager
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_novelty_service import NoveltyLabel, SigmaNoveltyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-ab-test", tags=["sigma-ab-test"])


def _extract_yaml_block(text: str) -> str:
    """Extract YAML from text (strip markdown code fences, leading prose)."""
    if not text or not text.strip():
        return text.strip() if text else ""
    text = text.strip()
    # Handle markdown code fences with optional "yaml" and support CRLF/newline variants.
    match = re.search(
        r"```(?:yaml)?[ \t]*\r?\n(.*?)(?:\r?\n[ \t]*```|[ \t]*```|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
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
        raise HTTPException(status_code=400, detail=f"Invalid YAML in {field}: {e}") from e
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

    return {
        "success": True,
        "similarity": round(weighted_sim, 4),
        "novelty_label": novelty_label,
        "atom_jaccard": round(atom_jaccard, 4),
        "logic_shape_similarity": round(logic_similarity, 4),
        "shared_atoms": explainability["shared_atoms"],
        "added_atoms": explainability["added_atoms"],
        "removed_atoms": explainability["removed_atoms"],
    }


@router.post("/compare-to-repository")
async def compare_rule_to_repository(compare_request: CompareToRepositoryRequest):
    """
    Compare a SIGMA rule against the repository (embedding-based similarity).
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
        result = matching_service.compare_proposed_rule_to_embeddings(
            proposed_rule=normalized, threshold=0.0
        )
        matches = result.get("matches", [])[:20]
        return {
            "success": True,
            "matches": [
                {
                    "rule_id": m.get("rule_id", ""),
                    "title": m.get("title", ""),
                    "similarity": m.get("similarity", 0.0),
                    "atom_jaccard": m.get("atom_jaccard"),
                    "logic_shape_similarity": m.get("logic_shape_similarity"),
                }
                for m in matches
            ],
        }
    finally:
        db_session.close()
