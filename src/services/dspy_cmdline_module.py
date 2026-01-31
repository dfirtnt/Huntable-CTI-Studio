"""
Deprecated placeholder for former DSPy command-line extractor.

All DSPy functionality was removed; this module now serves as a stub to
avoid import errors. Any call into these symbols will raise immediately.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _normalize_cmd(cmd: str) -> str:
    """Light normalization: trim, collapse whitespace; keep casing/escaping."""
    cmd = cmd.strip()
    cmd = re.sub(r"\s+", " ", cmd)
    return cmd


def load_cmdline_eval_dataset(eval_path: Path | str) -> dict[int, list[str]]:
    """Load article_id -> cmdline_items ground truth from the eval JSON."""
    path = Path(eval_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    evals: dict[int, list[str]] = {}
    for entry in data:
        aid = int(entry["article_id"])
        items = [_normalize_cmd(x) for x in entry.get("cmdline_items", []) if x.strip()]
        evals[aid] = items
    return evals


def evaluate_predictions(predictions: dict[int, list[str]], ground_truth: dict[int, list[str]]) -> dict[str, Any]:
    """Placeholder scorer kept for compatibility; returns zeros."""
    return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}


class CmdlineExtractor:
    """Placeholder stub; DSPy dependency removed."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError("DSPy CmdlineExtractor has been removed from the codebase.")

    def __call__(self, *args, **kwargs):
        raise RuntimeError("DSPy CmdlineExtractor has been removed from the codebase.")
