"""Hybrid extractor workflow node."""

import os
from typing import Any, Dict, List

from src.extractors.encoder_classifier import classify_candidates
from src.extractors.hybrid_cmdline_extractor import (
    extract_commands,
    literal_filter,
    update_cmdline_state,
)
from src.extractors.qa_validator import qa_validate
from src.extractors.regex_windows import extract_candidate_lines


class HybridExtractorNode:
    """Simple workflow node wrapper for hybrid command extraction."""

    def run(self, article_text: str) -> Dict[str, Any]:
        """Execute the hybrid extraction pipeline."""
        candidates = extract_candidate_lines(article_text)
        classified = classify_candidates(candidates)
        filtered = literal_filter(classified, article_text)

        if os.getenv("CMDLINE_QA_ENABLED", "false").lower() == "true":
            filtered = qa_validate(filtered, article_text)

        state: Dict[str, Any] = {}
        update_cmdline_state(state, filtered)
        return state


__all__: List[str] = ["HybridExtractorNode"]
