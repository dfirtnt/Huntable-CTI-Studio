"""Regex-based candidate harvesting for Windows command-lines."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment fallback
    yaml = None

logger = logging.getLogger(__name__)

# Base patterns supplied by specification
PATTERN_EXE_WITH_ARGS = r'(?:"?[A-Za-z]:\\+[^"\s]+\.\w{3,4}"?(?:\s+[^\r\n]+))'
PATTERN_BARE_EXE_WITH_ARGS = r"(?:[A-Za-z0-9_\-]+\.exe)(?:\s+[^\r\n]+)"
PATTERN_POWERSHELL = r"(?:powershell(?:\.exe)?)\s+[^\r\n]+"
PATTERN_SYSTEM32_UTILS = r'(?:"?C:\\+Windows\\+System32\\+(?:net|ipconfig|setspn|quser)\.exe"?\s+[^\r\n]+)'

# Additional pattern to better capture quoted executables containing spaces
PATTERN_QUOTED_WITH_SPACES = r'"[A-Za-z]:\\+[^"\r\n]+?\.\w{3,4}"(?:\s+[^\r\n]+)'

DEFAULT_PATTERNS: dict[str, str] = {
    "exe_with_args": PATTERN_EXE_WITH_ARGS,
    "bare_exe_with_args": PATTERN_BARE_EXE_WITH_ARGS,
    "powershell": PATTERN_POWERSHELL,
    "system32_utils": PATTERN_SYSTEM32_UTILS,
    "quoted_with_spaces": PATTERN_QUOTED_WITH_SPACES,
}


def _load_external_patterns() -> dict[str, str]:
    """Load optional regex overrides from resources/regex/windows_cmd_patterns.yaml."""
    if yaml is None:
        return {}
    try:
        repo_root = Path(__file__).resolve().parents[2]
        config_path = repo_root / "resources" / "regex" / "windows_cmd_patterns.yaml"
        if not config_path.exists():
            return {}
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        patterns = data.get("patterns", {})
        if isinstance(patterns, dict):
            return {k: v for k, v in patterns.items() if isinstance(v, str)}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load external regex patterns: %s", exc)
    return {}


def _iter_patterns() -> Iterable[re.Pattern]:
    """Yield compiled regex patterns, combining defaults with optional overrides."""
    patterns = DEFAULT_PATTERNS.copy()
    patterns.update(_load_external_patterns())
    for _, pattern in patterns.items():
        try:
            yield re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
        except re.error as exc:
            logger.warning("Skipping invalid regex pattern %s: %s", pattern, exc)


def extract_candidate_lines(text: str) -> list[str]:
    """
    Return list of raw candidate command-line strings from the article.
    These are NOT validated; high recall, low precision.
    """
    if not text:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    for pattern in _iter_patterns():
        for match in pattern.finditer(text):
            raw = match.group(0)
            # Preserve original text casing; trim surrounding whitespace only.
            cleaned = raw.strip()
            if not cleaned:
                continue

            # Prefer longer variants when overlapping (e.g., full path vs. bare exe)
            replaced = False
            for idx, existing in enumerate(candidates):
                if cleaned == existing or cleaned in existing:
                    replaced = True
                    break
                if existing in cleaned:
                    candidates[idx] = cleaned
                    seen.discard(existing)
                    seen.add(cleaned)
                    replaced = True
                    break

            if replaced:
                continue

            if cleaned not in seen:
                seen.add(cleaned)
                candidates.append(cleaned)

    return candidates
