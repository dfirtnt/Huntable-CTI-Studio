"""LangGraph/LangChain node wrapper for the hybrid command-line extractor."""

from __future__ import annotations

from src.extractors.encoder_classifier import classify_candidates
from src.extractors.hybrid_cmdline_extractor import is_qa_enabled, literal_filter
from src.extractors.qa_validator import qa_validate
from src.extractors.regex_windows import extract_candidate_lines


class HybridExtractorNode:
    """Simple node wrapper to keep interface compatible with existing workflows."""

    def run(self, article_text: str) -> dict:
        # Explicitly invoke each hybrid stage to ensure wiring is exercised.
        text = article_text or ""
        candidates = extract_candidate_lines(text)
        filtered = classify_candidates(candidates)
        literal_matches = literal_filter(filtered, text)
        qa_enabled = is_qa_enabled()
        if qa_enabled:
            final = qa_validate(literal_matches, text)
        else:
            final = literal_matches

        # Preserve order and dedupe
        deduped = []
        seen = set()
        for item in final:
            if item not in seen:
                seen.add(item)
                deduped.append(item)

        qa_corrections = {
            "removed": [item for item in literal_matches if item not in final] if qa_enabled else [],
            "added": [],
            "summary": "QA validation applied" if qa_enabled else "None.",
        }

        return {
            "cmdline_items": deduped,
            "count": len(deduped),
            "qa_corrections": qa_corrections,
        }
