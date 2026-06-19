"""Phase B: LLM platform adjudicator for the low-confidence / Unknown tail.

Runs ONLY when the deterministic KB gate (Phase A, ``platform_classifier``) cannot
confidently classify an article. The LLM call is dependency-injected (``llm_call``)
so the logic is unit-testable without network access. Any failure degrades to
Unknown -- adjudication must never break the workflow.

See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (§6).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable

from src.services.platform_classifier import SUPPORTED_PLATFORMS, PlatformClassification

logger = logging.getLogger(__name__)

# Phase A scope: Windows / Linux / macOS (+ aliases). Cross-platform/Domains/Products
# are Phase D; an article spanning OSes is expressed as a multi-platform list.
_ALIAS = {
    "windows": "windows",
    "win": "windows",
    "linux": "linux",
    "macos": "macos",
    "mac": "macos",
    "mac os": "macos",
    "osx": "macos",
    "os x": "macos",
    "darwin": "macos",
}

ADJUDICATION_SYSTEM = (
    "You are a precise threat-intelligence platform classifier. Given a security article, "
    "identify which host operating system(s) the attacker activity concerns. Only choose "
    "from: Windows, Linux, macOS. List every platform that clearly applies (an article may "
    "cover more than one). If the article gives no clear host-platform signal, return an "
    "empty list. Base the decision on host artifacts and commands, not incidental mentions. "
    "Respond with strict JSON only."
)

_JSON_INSTRUCTIONS = (
    'Return JSON exactly like: {"platforms": ["Linux"], "confidence": "high|medium|low", '
    '"evidence": ["short reason", "..."]}. Use platform names from {Windows, Linux, macOS}. '
    "An empty platforms list means unknown / no clear signal."
)


def build_adjudication_messages(content: str, max_chars: int = 8000) -> list[dict]:
    """Build the chat messages for platform adjudication (content excerpt bounded)."""
    excerpt = (content or "")[:max_chars]
    user = f"{_JSON_INSTRUCTIONS}\n\nArticle:\n{excerpt}"
    return [
        {"role": "system", "content": ADJUDICATION_SYSTEM},
        {"role": "user", "content": user},
    ]


def _unknown() -> PlatformClassification:
    return PlatformClassification(
        platforms=[],
        primary="unknown",
        confidence="low",
        scores={p: 0.0 for p in SUPPORTED_PLATFORMS},
        evidence={},
        method="llm_adjudication",
    )


def _extract_json(text: str) -> str | None:
    t = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if fence:
        return fence.group(1)
    brace = re.search(r"\{.*\}", t, re.DOTALL)
    return brace.group(0) if brace else None


def parse_adjudication_response(text: str) -> PlatformClassification:
    """Parse an LLM adjudication response into a PlatformClassification.

    Robust to markdown fences and extra prose; any parse failure -> Unknown.
    """
    raw = _extract_json(text)
    if not raw:
        return _unknown()
    try:
        data = json.loads(raw)
    except Exception:
        return _unknown()
    if not isinstance(data, dict):
        return _unknown()

    platforms: list[str] = []
    for p in data.get("platforms", []) or []:
        norm = _ALIAS.get(str(p).strip().lower())
        if norm in SUPPORTED_PLATFORMS and norm not in platforms:
            platforms.append(norm)

    confidence = str(data.get("confidence", "medium")).strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    if not platforms:
        return _unknown()

    ev = data.get("evidence") or []
    evidence = {"adjudication": [str(e) for e in ev]} if isinstance(ev, list) else {}
    return PlatformClassification(
        platforms=platforms,
        primary=platforms[0],
        confidence=confidence,
        scores={p: 0.0 for p in SUPPORTED_PLATFORMS},
        evidence=evidence,
        method="llm_adjudication",
    )


async def adjudicate_platforms(
    content: str,
    *,
    llm_call: Callable[[list[dict]], Awaitable[str]],
    max_chars: int = 8000,
) -> PlatformClassification:
    """Classify platforms via an injected async LLM call. Never raises -> Unknown on error."""
    try:
        messages = build_adjudication_messages(content, max_chars=max_chars)
        text = await llm_call(messages)
        return parse_adjudication_response(text)
    except Exception as e:
        logger.warning(f"Platform adjudication failed, returning Unknown: {e}")
        return _unknown()
