"""
DSPy module definition for command-line extraction from CTI chunks.

Input: raw CTI chunk (string).
Output: list of extracted Windows command-line observables (with arguments).

Eval data: outputs/reports/cmdline_evals_clean.json (article-level labels).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Dict, Any

import dspy


class CmdlineExtractSig(dspy.Signature):
    """Extract literal Windows command lines (with arguments) from CTI text."""

    raw_cti_chunk: str = dspy.InputField(
        desc="Literal CTI text chunk (post-filter, e.g., after junk filter at 0.8)"
    )
    cmdline_items: List[str] = dspy.OutputField(
        desc="Windows command-line observables with arguments/switches; cmd.exe chains kept as one"
    )


class CmdlineExtractor(dspy.Module):
    """Module wrapper for the command-line extraction task."""

    def __init__(self):
        super().__init__()
        self.pred = dspy.Predict(CmdlineExtractSig)

    def forward(self, raw_cti_chunk: str):
        return self.pred(raw_cti_chunk=raw_cti_chunk)


# ---------- Eval helpers ----------

def _normalize_cmd(cmd: str) -> str:
    """Light normalization: trim, collapse whitespace; keep casing/escaping."""
    cmd = cmd.strip()
    cmd = re.sub(r"\s+", " ", cmd)
    return cmd


def load_cmdline_eval_dataset(eval_path: Path | str) -> Dict[int, List[str]]:
    """Load article_id -> cmdline_items ground truth from the eval JSON."""
    path = Path(eval_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    evals: Dict[int, List[str]] = {}
    for entry in data:
        aid = int(entry["article_id"])
        items = [_normalize_cmd(x) for x in entry.get("cmdline_items", []) if x.strip()]
        evals[aid] = items
    return evals


def evaluate_predictions(
    predictions: Dict[int, List[str]], ground_truth: Dict[int, List[str]]
) -> Dict[str, Any]:
    """
    Compute simple precision/recall/F1 across all articles.

    Args:
        predictions: article_id -> list of predicted commands
        ground_truth: article_id -> list of gold commands
    """
    tp = fp = fn = 0
    for aid, gold in ground_truth.items():
        gold_set = {_normalize_cmd(c) for c in gold}
        pred_set = {_normalize_cmd(c) for c in predictions.get(aid, [])}
        tp += len(gold_set & pred_set)
        fp += len(pred_set - gold_set)
        fn += len(gold_set - pred_set)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


# ---------- Usage outline ----------
#
# from dspy_cmdline_module import CmdlineExtractor, load_cmdline_eval_dataset, evaluate_predictions
# import dspy, os
#
# lm = dspy.LM(
#     model="openai/qwen/qwen2.5-coder-14b",  # LMStudio OpenAI-compatible prefix
#     model_type="chat",
#     temperature=0.0,
#     max_tokens=512,
#     api_base=os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1"),
#     api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
# )
# dspy.configure(lm=lm)
#
# predictor = CmdlineExtractor()
# pred = predictor(raw_cti_chunk="...CTI text...")
# print(pred.cmdline_items)
#
# # Eval:
# gold = load_cmdline_eval_dataset("outputs/reports/cmdline_evals_clean.json")
# # predictions should be built by running predictor on each article/chunk and grouping by article_id.
# scores = evaluate_predictions(predictions, gold)
# print(scores)
