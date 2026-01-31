#!/usr/bin/env python3
"""
Evaluate trained Windows huntables classifier on hold-out evaluation set.

Tests the model on data it has never seen during training.
"""

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.train_huntable_windows_classifier import (
    extract_keyword_features,
)
from src.services.os_detection_service import OSDetectionService


def evaluate_model(
    model_path: Path,
    scaler_path: Path,
    eval_data: list[dict[str, Any]],
    use_embeddings: bool = True,
    use_keywords: bool = True,
) -> dict[str, Any]:
    """Evaluate trained model on evaluation set."""

    # Load model and scaler
    print(f"Loading model from {model_path}...")
    with open(model_path, "rb") as f:
        classifier = pickle.load(f)

    print(f"Loading scaler from {scaler_path}...")
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    # Initialize service for embeddings
    service = None
    if use_embeddings:
        service = OSDetectionService()

    # Extract features
    print("\nExtracting features from evaluation set...")
    X_keyword = []
    X_embedding = []
    y_true = []
    article_ids = []

    for i, item in enumerate(eval_data, 1):
        content = item.get("content", "")
        label = item.get("label", 0)
        article_id = item.get("article_id", i)

        if not content:
            continue

        if i % 50 == 0:
            print(f"  Processed {i}/{len(eval_data)} articles...")

        # Keyword features
        if use_keywords:
            keyword_features = extract_keyword_features(item)
            X_keyword.append(keyword_features)

        # Embedding features
        if use_embeddings and service:
            embedding = service._get_embedding(content[:2000])
            X_embedding.append(embedding)

        y_true.append(label)
        article_ids.append(article_id)

    # Combine features
    if use_keywords and use_embeddings:
        X_keyword = np.array(X_keyword)
        X_embedding = np.array(X_embedding)
        X = np.hstack([X_keyword, X_embedding])
    elif use_keywords:
        X = np.array(X_keyword)
    elif use_embeddings:
        X = np.array(X_embedding)
    else:
        raise ValueError("Must use at least one feature type")

    y_true = np.array(y_true)

    # Scale features
    X_scaled = scaler.transform(X)

    # Predict
    print("\nEvaluating model...")
    y_pred = classifier.predict(X_scaled)
    y_pred_proba = classifier.predict_proba(X_scaled)[:, 1]

    # Calculate metrics
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_true, y_pred_proba)

    print(f"\n{'=' * 80}")
    print("EVALUATION RESULTS (Hold-Out Set)")
    print(f"{'=' * 80}")
    print("\nMetrics:")
    print(f"  Accuracy: {accuracy:.3f}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall: {recall:.3f}")
    print(f"  F1 Score: {f1:.3f}")
    print(f"  ROC-AUC: {roc_auc:.3f}")

    # Classification report
    print("\nClassification Report:")
    print(
        classification_report(
            y_true, y_pred, target_names=["No Windows Huntables", "Windows Huntables"], zero_division=0
        )
    )

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    print("\nConfusion Matrix:")
    print("                Predicted")
    print("              No    Yes")
    print(f"Actual No   {cm[0][0]:4d}  {cm[0][1]:4d}")
    print(f"       Yes   {cm[1][0]:4d}  {cm[1][1]:4d}")

    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": float(roc_auc),
        "confusion_matrix": cm.tolist(),
        "evaluation_samples": len(y_true),
        "positive_samples": int(np.sum(y_true == 1)),
        "negative_samples": int(np.sum(y_true == 0)),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate trained Windows huntables classifier on hold-out set")
    parser.add_argument("--model", type=Path, required=True, help="Path to trained classifier (.pkl)")
    parser.add_argument(
        "--scaler",
        type=Path,
        default=None,
        help="Path to feature scaler (.pkl). Defaults to same dir as model with _scaler suffix",
    )
    parser.add_argument("--eval-data", type=Path, required=True, help="Path to evaluation dataset JSON")
    parser.add_argument("--output", type=Path, default=None, help="Output path for evaluation results JSON")
    parser.add_argument("--no-embeddings", action="store_true", help="Model uses keyword features only")
    parser.add_argument("--no-keywords", action="store_true", help="Model uses embedding features only")

    args = parser.parse_args()

    # Auto-detect scaler path
    if args.scaler is None:
        scaler_name = args.model.stem.replace("classifier", "scaler").replace("_classifier", "_scaler") + ".pkl"
        args.scaler = args.model.parent / scaler_name
        if not args.scaler.exists():
            # Try alternative naming
            args.scaler = args.model.parent / "huntable_windows_scaler.pkl"

    if not args.scaler.exists():
        print(f"Error: Scaler not found at {args.scaler}")
        return

    # Load evaluation data
    print(f"Loading evaluation data from {args.eval_data}...")
    with open(args.eval_data) as f:
        eval_data = json.load(f)
    print(f"Loaded {len(eval_data)} evaluation samples")

    # Evaluate
    results = evaluate_model(
        args.model, args.scaler, eval_data, use_embeddings=not args.no_embeddings, use_keywords=not args.no_keywords
    )

    # Save results
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n✅ Evaluation results saved to: {args.output}")

    # Compare with baseline
    baseline_path = Path("outputs/huntable_windows_baseline_results.json")
    if baseline_path.exists():
        print(f"\n{'=' * 80}")
        print("COMPARISON WITH BASELINE")
        print(f"{'=' * 80}")

        with open(baseline_path) as f:
            baseline_data = json.load(f)

        # Find best baseline (keyword features only)
        best_baseline = None
        for baseline in baseline_data.get("baselines", []):
            if "keyword_features_only" in baseline["method"]:
                best_baseline = baseline
                break

        if best_baseline:
            print("\nBaseline (Keyword Features Only):")
            print(f"  Accuracy: {best_baseline['accuracy']:.3f}")
            print(f"  F1 Score: {best_baseline.get('f1', 0):.3f}")
            print(f"  ROC-AUC: {best_baseline.get('roc_auc', 0):.3f}")

            print("\nTrained Model (Hybrid):")
            print(f"  Accuracy: {results['accuracy']:.3f}")
            print(f"  F1 Score: {results['f1']:.3f}")
            print(f"  ROC-AUC: {results['roc_auc']:.3f}")

            acc_diff = results["accuracy"] - best_baseline["accuracy"]
            f1_diff = results["f1"] - best_baseline.get("f1", 0)
            roc_diff = results["roc_auc"] - best_baseline.get("roc_auc", 0)

            print("\nImprovement:")
            print(f"  Accuracy: {acc_diff:+.3f}")
            print(f"  F1 Score: {f1_diff:+.3f}")
            print(f"  ROC-AUC: {roc_diff:+.3f}")


if __name__ == "__main__":
    main()
