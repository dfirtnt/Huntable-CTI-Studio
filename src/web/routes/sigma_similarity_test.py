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
from src.services.similarity_serialization import serialize_similarity_match

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-similarity-test", tags=["sigma-similarity-test"])


def _extract_yaml_block(text: str) -> str:
    """Strip markdown code fences and leading prose, return raw YAML."""
    import re

    if not text or not text.strip():
        return text.strip() if text else ""
    text = text.strip()
    fence_open = re.match(r"```(?:[a-z0-9]+)?[ \t]*\r?\n", text, re.IGNORECASE)
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

        # Project each match onto the unified canonical contract (Phase 1).
        # llm_rerank / semantic_overlap are page-specific extras the template reads.
        formatted = [
            {
                **serialize_similarity_match(m),
                "llm_rerank": None,
                "semantic_overlap": None,
            }
            for m in matches
        ]

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
