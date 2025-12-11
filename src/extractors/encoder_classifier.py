"""Semantic filtering for Windows command-line candidates."""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover - environment fallback
    np = None

logger = logging.getLogger(__name__)

VALID_EXAMPLES = [
    "powershell.exe -ExecutionPolicy Bypass -enc AAA",
    '"C:\\Program Files\\App\\app.exe" -flag',
    'C:\\Windows\\System32\\net.exe group "domain users" /do',
]

INVALID_EXAMPLES = [
    "Service Control Manager/7036; Velociraptor running",
    "MsiInstaller/11707; Product installed successfully",
    '"C:\\Program Files\\Velociraptor\\Velociraptor.exe"',
    'Velociraptor/1000; ARGV: ["C:..."]',
]

SIMILARITY_MARGIN = 0.05
DEFAULT_MODEL = os.getenv("CMDLINE_ENCODER_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_encoder = None
_reference_embeddings: Optional[Tuple[np.ndarray, np.ndarray]] = None


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-8
    return float(np.dot(a, b) / denom)


def _load_encoder():
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer

        model_name = DEFAULT_MODEL
        _encoder = SentenceTransformer(model_name)
        logger.info("Loaded command-line encoder model: %s", model_name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Falling back to heuristic classification: %s", exc)
        _encoder = None
    return _encoder


def _compute_reference_embeddings(encoder) -> Tuple[np.ndarray, np.ndarray]:
    global _reference_embeddings
    if _reference_embeddings is not None:
        return _reference_embeddings

    valid_embeddings = encoder.encode(VALID_EXAMPLES, convert_to_numpy=True, normalize_embeddings=True)
    invalid_embeddings = encoder.encode(INVALID_EXAMPLES, convert_to_numpy=True, normalize_embeddings=True)
    _reference_embeddings = (np.mean(valid_embeddings, axis=0), np.mean(invalid_embeddings, axis=0))
    return _reference_embeddings


def _is_probably_cmd(candidate: str) -> bool:
    """Cheap heuristics to filter obvious non-commands when encoder is unavailable."""
    text = candidate.strip()
    if not text:
        return False

    lowered = text.lower()
    if any(marker in lowered for marker in ["service control manager", "msiinstaller", "eventlog"]):
        return False
    if lowered.startswith("argv") or "argv" in lowered:
        return False
    if text.startswith("[") or text.startswith("{"):
        return False
    if re.search(r"\.exe\"?\s*$", text, flags=re.IGNORECASE):
        # Executable without arguments
        return False
    return True


@lru_cache(maxsize=1)
def _use_heuristic_mode() -> bool:
    return os.getenv("CMDLINE_ENCODER_MODE", "encoder").lower() == "heuristic"


def classify_candidates(candidates: list[str]) -> list[str]:
    """
    Return the subset of candidates that are VALID Windows commands.
    Uses an encoder to filter log lines, ARGV arrays, filenames, and noise.
    """
    if not candidates:
        return []

    deduped = _dedupe_preserve_order(candidates)
    if _use_heuristic_mode():
        return [c for c in deduped if _is_probably_cmd(c)]

    if np is None:
        logger.warning("NumPy not available; falling back to heuristic classifier")
        return [c for c in deduped if _is_probably_cmd(c)]

    encoder = _load_encoder()
    if encoder is None:
        return [c for c in deduped if _is_probably_cmd(c)]

    valid_mean, invalid_mean = _compute_reference_embeddings(encoder)
    candidate_embeddings = encoder.encode(deduped, convert_to_numpy=True, normalize_embeddings=True)

    filtered: list[str] = []
    for candidate, embedding in zip(deduped, candidate_embeddings):
        sim_valid = _cosine(embedding, valid_mean)
        sim_invalid = _cosine(embedding, invalid_mean)
        if sim_valid > sim_invalid + SIMILARITY_MARGIN and _is_probably_cmd(candidate):
            filtered.append(candidate)

    return filtered
