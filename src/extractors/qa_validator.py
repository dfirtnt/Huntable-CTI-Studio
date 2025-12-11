"""Optional QA pass for command-line extraction."""

from __future__ import annotations

import logging
import os
import re
from typing import List

logger = logging.getLogger(__name__)

LLM_MODEL_NAME = os.getenv("CMDLINE_QA_MODEL", "")


def _basic_checks(candidate: str, article: str) -> bool:
    """Lightweight validation that mirrors the prompt criteria without invoking an LLM."""
    if not candidate or candidate not in article:
        return False
    if not re.search(r"\.exe", candidate, flags=re.IGNORECASE):
        return False
    if not re.search(r"\s+\S+", candidate):
        return False
    if re.search(r"(service control manager|msiinstaller)", candidate, flags=re.IGNORECASE):
        return False
    return True


def qa_validate(final_candidates: List[str], article: str) -> List[str]:
    """
    Use a small LLM to re-check borderline cases.
    Must output the same or reduced list.
    """
    if not final_candidates:
        return []

    # Placeholder for future LLM validation; currently rely on deterministic checks to avoid latency.
    reviewed: list[str] = [cmd for cmd in final_candidates if _basic_checks(cmd, article)]

    if not LLM_MODEL_NAME:
        return reviewed

    # If a model is configured, we can extend later to invoke it; keep deterministic behavior for now.
    logger.info("LLM QA model configured (%s) but deterministic validator is currently used.", LLM_MODEL_NAME)
    return reviewed
