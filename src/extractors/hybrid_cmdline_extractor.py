"""Hybrid command-line extractor combining regex, encoder, literal filter, and optional QA."""

from __future__ import annotations

import logging
import os
from typing import Dict, List

from src.extractors.encoder_classifier import classify_candidates
from src.extractors.qa_validator import qa_validate
from src.extractors.regex_windows import extract_candidate_lines

logger = logging.getLogger(__name__)


def is_qa_enabled() -> bool:
    """Check runtime flag to enable QA validation."""
    return os.getenv("CMDLINE_QA_ENABLED", "false").lower() in {"1", "true", "yes"}


def literal_filter(cmds: List[str], article: str) -> List[str]:
    """Keep only commands that appear literally in the source article."""
    if not cmds:
        return []
    return [c for c in cmds if c in article]


def update_cmdline_state(state: Dict[str, object], cmdline_items: List[str]) -> Dict[str, object]:
    """Mutate workflow state with cmdline_items/count keys used downstream."""
    state["cmdline_items"] = cmdline_items or []
    state["count"] = len(state["cmdline_items"])
    return state


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def extract_commands(article_text: str) -> Dict[str, object]:
    """
    Run the hybrid extraction pipeline and return JSON-ready output.
    """
    text = article_text or ""
    candidates = extract_candidate_lines(text)
    filtered = classify_candidates(candidates)
    literal_matches = literal_filter(filtered, text)

    qa_enabled = is_qa_enabled()
    if qa_enabled:
        final = qa_validate(literal_matches, text)
        removed = [item for item in literal_matches if item not in final]
        qa_corrections = {
            "removed": removed,
            "added": [],
            "summary": "QA validation applied" if removed else "None.",
        }
    else:
        final = literal_matches
        qa_corrections = {"removed": [], "added": [], "summary": "None."}

    final = _dedupe_preserve_order(final)

    result = {
        "cmdline_items": final,
        "count": len(final),
        "qa_corrections": qa_corrections,
    }

    logger.info(
        "Hybrid extractor produced %s cmdline_items (candidates=%s, qa_enabled=%s)",
        result["count"],
        len(candidates),
        qa_enabled,
    )

    return result
