"""
API routes for SIGMA rule similarity search.

Provides POST /api/sigma-similarity-test/search — takes an arbitrary rule
and returns ranked similar rules from the indexed corpus using the
behavioral novelty assessment engine (Jaccard × Containment − Filter).
"""

import logging

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.database.manager import DatabaseManager
from src.services.sigma_matching_service import SigmaMatchingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-similarity-test", tags=["sigma-similarity-test"])


def _extract_yaml_block(text: str) -> str:
    """Strip markdown code fences and leading prose, return raw YAML."""
    import re

    if not text or not text.strip():
        return text.strip() if text else ""
    text = text.strip()
    fence_open = re.match(r"```(?:yaml)?[ \t]*\r?\n", text, re.IGNORECASE)
    if fence_open:
        content_start = fence_open.end()
        fence_close = text.find("\n```", content_start)
        if fence_close == -1:
            fence_close = text.find("```", content_start)
        return text[content_start:fence_close].strip() if fence_close != -1 else text[content_start:].strip()
    for start in ("title:", "id:", "logsource:", "detection:"):
        idx = text.find(start)
        if idx != -1:
            candidate = text[idx:].strip()
            candidate = re.split(r"```", candidate, maxsplit=1)[0].strip()
            return candidate
    return text.strip()


class SimilaritySearchRequest(BaseModel):
    rule_yaml: str
    use_llm_rerank: bool = False
    embedding_model: str = ""
    llm_model: str = ""
    top_k: int = Field(default=10, ge=1, le=50)


@router.post("/search")
async def search_similar_rules(request: SimilaritySearchRequest):
    """
    Search for rules similar to the provided SIGMA rule.

    Uses the behavioral novelty assessment engine: candidate retrieval via
    canonical_class SQL filter, scoring via Jaccard × Containment − Filter.
    Returns top-K matches ranked by weighted similarity.
    """
    content = _extract_yaml_block(request.rule_yaml)
    if not content:
        raise HTTPException(status_code=400, detail="Rule YAML is empty")

    try:
        rule_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail="Invalid YAML") from e

    if not isinstance(rule_data, dict):
        raise HTTPException(status_code=400, detail="Rule must be a YAML object")
    if not rule_data.get("detection"):
        raise HTTPException(status_code=400, detail="Rule must have a detection section")

    normalized = {
        "title": rule_data.get("title", ""),
        "description": rule_data.get("description", ""),
        "tags": rule_data.get("tags", []),
        "logsource": rule_data.get("logsource", {}),
        "detection": rule_data.get("detection", {}),
        "level": rule_data.get("level"),
        "status": rule_data.get("status", "experimental"),
    }

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    try:
        matching_service = SigmaMatchingService(db_session)
        result = matching_service.assess_rule_novelty(proposed_rule=normalized, threshold=0.0)

        raw_matches = result.get("matches", [])
        top_k = request.top_k
        matches = raw_matches[:top_k]

        formatted = []
        for m in matches:
            # Build similarity_breakdown in the richer format the template expects
            breakdown = m.get("similarity_breakdown") or {}
            atom_jaccard = m.get("atom_jaccard", breakdown.get("atom_jaccard", 0.0))
            logic_shape = m.get("logic_shape_similarity", breakdown.get("logic_shape_similarity"))

            formatted.append(
                {
                    "rule_id": m.get("rule_id", ""),
                    "title": m.get("title", ""),
                    "description": m.get("description", ""),
                    "logsource": m.get("logsource"),
                    "detection": m.get("detection"),
                    "tags": m.get("tags", []),
                    "level": m.get("level"),
                    "status": m.get("status"),
                    "file_path": m.get("file_path"),
                    "similarity": round(m.get("similarity", 0.0), 4),
                    "similarity_breakdown": {
                        "atom_jaccard": round(atom_jaccard, 4),
                        "logic_shape_similarity": round(logic_shape, 4) if logic_shape is not None else None,
                    },
                    "shared_atoms": m.get("shared_atoms", []),
                    "added_atoms": m.get("added_atoms", []),
                    "removed_atoms": m.get("removed_atoms", []),
                    "filter_differences": m.get("filter_differences", []),
                    "novelty_label": m.get("novelty_label"),
                    "service_penalty": m.get("service_penalty", 0.0),
                    "filter_penalty": m.get("filter_penalty", 0.0),
                    "llm_rerank": None,
                    "semantic_overlap": None,
                }
            )

        return {
            "success": True,
            "matches": formatted,
            "total_candidates_evaluated": result.get("total_candidates_evaluated", 0),
            "models_used": {
                "embedding_model": request.embedding_model or "behavioral-novelty-engine",
                "llm_model": "not used" if not request.use_llm_rerank else (request.llm_model or "none"),
            },
            "input_rule": {
                "title": normalized["title"],
                "logsource": normalized["logsource"],
                "detection": normalized["detection"],
            },
        }
    finally:
        db_session.close()
