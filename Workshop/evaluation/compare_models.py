"""
Evaluate all three models on the same dataset and write reports/results.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple

from Workshop.evaluation.metrics.span_metrics import compute_metrics
from Workshop.inference.extractor import CmdExtractor
from Workshop.utilities.training_helpers import load_jsonl

WORKSHOP_ROOT = Path(__file__).resolve().parents[1]
DATA_SPLITS = WORKSHOP_ROOT / "data" / "splits"
MODELS_ROOT = WORKSHOP_ROOT / "models"
REPORTS_DIR = WORKSHOP_ROOT / "evaluation" / "reports"
RESULTS_DIR = WORKSHOP_ROOT / "evaluation" / "results"


def _aggregate_metrics(pred_spans: List[Dict], gold_spans: List[Dict], iou_threshold: float):
    strict = compute_metrics(pred_spans, gold_spans, relaxed=False, iou_threshold=iou_threshold)
    relaxed = compute_metrics(pred_spans, gold_spans, relaxed=True, iou_threshold=iou_threshold)
    return strict, relaxed


def _combine_counts(counts: List[Dict]) -> Dict:
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


def evaluate_model(model_key: str, version: str, dataset: List[Dict], iou_threshold: float) -> Dict:
    model_path = MODELS_ROOT / model_key / version
    extractor = CmdExtractor(str(model_path))

    strict_counts = []
    relaxed_counts = []
    for record in dataset:
        preds = extractor.extract(record["text"]).get("spans", [])
        golds = record.get("spans", [])
        strict, relaxed = _aggregate_metrics(preds, golds, iou_threshold)
        strict_counts.append(strict)
        relaxed_counts.append(relaxed)

    return {
        "model": model_key,
        "version": version,
        "strict": _combine_counts(strict_counts),
        "relaxed": _combine_counts(relaxed_counts),
    }


def write_report(model_key: str, version: str, metrics: Dict):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{model_key}_{version}.md"
    lines = [
        f"# {model_key} {version} Evaluation",
        "",
        "## Strict",
        f"- Precision: {metrics['strict']['precision']:.4f}",
        f"- Recall: {metrics['strict']['recall']:.4f}",
        f"- F1: {metrics['strict']['f1']:.4f}",
        f"- FP Rate: {metrics['strict']['false_positive_rate']:.4f}",
        "",
        "## Relaxed (IoU)",
        f"- Precision: {metrics['relaxed']['precision']:.4f}",
        f"- Recall: {metrics['relaxed']['recall']:.4f}",
        f"- F1: {metrics['relaxed']['f1']:.4f}",
        f"- FP Rate: {metrics['relaxed']['false_positive_rate']:.4f}",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def write_results(model_key: str, version: str, metrics: Dict):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS_DIR / f"{model_key}_{version}.json"
    result_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate and compare span models.")
    parser.add_argument("--dataset", default=DATA_SPLITS / "test.jsonl", help="JSONL with text and spans")
    parser.add_argument("--version", default="v0.1", help="Model version to evaluate")
    parser.add_argument("--iou-threshold", type=float, default=0.5, help="IoU threshold for relaxed matching")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    dataset = load_jsonl(dataset_path)

    summaries = []
    for model_key in ["bert_base", "secbert", "roberta_base"]:
        metrics = evaluate_model(model_key, args.version, dataset, args.iou_threshold)
        write_report(model_key, args.version, metrics)
        write_results(model_key, args.version, metrics)
        summaries.append(metrics)

    combined_path = RESULTS_DIR / f"combined_{args.version}.json"
    combined_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"Wrote per-model and combined results to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
