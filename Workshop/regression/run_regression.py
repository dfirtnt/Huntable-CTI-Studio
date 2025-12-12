"""
Regression harness: evaluate a model on the fixed regression test set.
"""

import json
from pathlib import Path
from typing import Dict, List

from Workshop.evaluation.metrics.span_metrics import compute_metrics
from Workshop.inference.extractor import CmdExtractor
from Workshop.utilities.training_helpers import load_jsonl

REG_ROOT = Path(__file__).resolve().parents[1] / "regression"
MODELS_ROOT = Path(__file__).resolve().parents[1] / "models"


def aggregate(dataset: List[Dict], extractor: CmdExtractor, iou_threshold: float) -> Dict:
    strict_counts = []
    relaxed_counts = []
    for record in dataset:
        preds = extractor.extract(record["text"]).get("spans", [])
        golds = record.get("spans", [])
        strict = compute_metrics(preds, golds, relaxed=False, iou_threshold=iou_threshold)
        relaxed = compute_metrics(preds, golds, relaxed=True, iou_threshold=iou_threshold)
        strict_counts.append(strict)
        relaxed_counts.append(relaxed)

    def _combine(counts: List[Dict]) -> Dict:
        tp = sum(c["true_positive"] for c in counts)
        fp = sum(c["false_positive"] for c in counts)
        fn = sum(c["false_negative"] for c in counts)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        fp_rate = fp / (tp + fp) if tp + fp else 0.0
        return {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positive_rate": fp_rate,
        }

    return {"strict": _combine(strict_counts), "relaxed": _combine(relaxed_counts)}


def run(model_key: str, version: str, dataset_path: Path, iou_threshold: float, output_path: Path):
    dataset = load_jsonl(dataset_path)
    extractor = CmdExtractor(str(MODELS_ROOT / model_key / version))
    metrics = aggregate(dataset, extractor, iou_threshold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Wrote regression results to {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run regression evaluation.")
    parser.add_argument("--model", required=True, choices=["bert_base", "secbert", "roberta_base"])
    parser.add_argument("--version", default="v0.1")
    parser.add_argument("--dataset", default=REG_ROOT / "test_set" / "test.jsonl")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    output = REG_ROOT / "results" / f"{args.model}_{args.version}.json"
    run(args.model, args.version, Path(args.dataset), args.iou_threshold, output)


if __name__ == "__main__":
    main()
