"""
Span-level metrics: strict (exact) and relaxed (IoU-based) matching.
"""

from typing import Dict, List, Tuple


def iou(span_a: Dict, span_b: Dict) -> float:
    inter = max(0, min(span_a["end"], span_b["end"]) - max(span_a["start"], span_b["start"]))
    union = max(span_a["end"], span_b["end"]) - min(span_a["start"], span_b["start"])
    return inter / union if union else 0.0


def _match(preds: List[Dict], golds: List[Dict], relaxed: bool, iou_threshold: float) -> Tuple[int, int, int]:
    matched_gold = set()
    tp = fp = 0
    for p in preds:
        hit_idx = None
        for idx, g in enumerate(golds):
            if idx in matched_gold:
                continue
            if relaxed:
                if iou(p, g) >= iou_threshold:
                    hit_idx = idx
                    break
            else:
                if p["start"] == g["start"] and p["end"] == g["end"]:
                    hit_idx = idx
                    break
        if hit_idx is not None:
            tp += 1
            matched_gold.add(hit_idx)
        else:
            fp += 1
    fn = len(golds) - len(matched_gold)
    return tp, fp, fn


def compute_metrics(preds: List[Dict], golds: List[Dict], relaxed: bool = False, iou_threshold: float = 0.5) -> Dict:
    tp, fp, fn = _match(preds, golds, relaxed=relaxed, iou_threshold=iou_threshold)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fp_rate = fp / (tp + fp) if tp + fp else 0.0  # proxy FPR
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fp_rate,
    }
