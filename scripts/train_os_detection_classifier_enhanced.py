#!/usr/bin/env python3
"""
Enhanced OS Detection Classifier Training

Trains RandomForest or LogisticRegression classifier on CTI-BERT embeddings
with cross-validation, detailed metrics, and evaluation on test set.

Usage:
    python scripts/train_os_detection_classifier_enhanced.py \
        --data data/os_detection_training_data.json \
        --classifier random_forest \
        --test-split 0.2
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.os_detection_service import OS_LABELS, OSDetectionService


def load_training_data(data_path: Path) -> list[dict[str, Any]]:
    """Load training data from JSON file."""
    with open(data_path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Training data must be a list of objects")

    return data


def prepare_features_and_labels(
    training_data: list[dict[str, Any]], service: OSDetectionService
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Prepare feature embeddings and labels from training data."""
    X = []
    y = []
    article_ids = []

    print("Generating embeddings from training data...")
    for i, item in enumerate(training_data, 1):
        content = item.get("content", "")
        os_label = item.get("os_label", "Unknown")
        article_id = item.get("article_id", i)

        if not content:
            continue

        if i % 10 == 0:
            print(f"  Processed {i}/{len(training_data)} articles...")

        # Generate embedding
        embedding = service._get_embedding(content[:2000])
        X.append(embedding)

        # Map label to index
        if os_label in OS_LABELS:
            y.append(OS_LABELS.index(os_label))
        else:
            y.append(OS_LABELS.index("Unknown"))

        article_ids.append(article_id)

    X = np.array(X)
    y = np.array(y)

    return X, y, article_ids


def train_and_evaluate(
    X: np.ndarray,
    y: np.ndarray,
    classifier_type: str,
    test_size: float = 0.2,
    random_state: int = 42,
    cv_folds: int = 5,
) -> dict[str, Any]:
    """Train classifier and evaluate with cross-validation."""

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    print("\nData split:")
    print(f"  Training samples: {len(X_train)}")
    print(f"  Test samples: {len(X_test)}")

    # Train classifier
    if classifier_type == "random_forest":
        classifier = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=random_state, class_weight="balanced"
        )
    else:
        classifier = LogisticRegression(max_iter=1000, random_state=random_state, class_weight="balanced")

    print(f"\nTraining {classifier_type} classifier...")
    classifier.fit(X_train, y_train)

    # Training accuracy
    train_score = classifier.score(X_train, y_train)
    print(f"  Training accuracy: {train_score:.3f}")

    # Cross-validation
    print(f"\nPerforming {cv_folds}-fold cross-validation...")
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    cv_scores = cross_val_score(classifier, X_train, y_train, cv=cv, scoring="accuracy")
    print(f"  CV Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})")

    # Test evaluation
    print("\nEvaluating on test set...")
    y_pred = classifier.predict(X_test)
    test_accuracy = accuracy_score(y_test, y_pred)
    print(f"  Test accuracy: {test_accuracy:.3f}")

    # Get unique classes present in data
    unique_labels = np.unique(np.concatenate([y_test, y_pred]))
    present_labels = [OS_LABELS[i] for i in unique_labels]

    # Detailed metrics
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, labels=unique_labels, target_names=present_labels, zero_division=0))

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred, labels=unique_labels)
    print("\nConfusion Matrix:")
    print(f"{'':<12}", end="")
    for label in present_labels:
        print(f"{label[:8]:<12}", end="")
    print()
    for i, label in enumerate(present_labels):
        print(f"{label[:12]:<12}", end="")
        for j in range(len(present_labels)):
            print(f"{cm[i][j]:<12}", end="")
        print()

    # Per-class accuracy
    print("\nPer-class accuracy:")
    for i, label_idx in enumerate(unique_labels):
        label = OS_LABELS[label_idx]
        if np.sum(y_test == label_idx) > 0:
            class_mask = y_test == label_idx
            class_accuracy = accuracy_score(y_test[class_mask], y_pred[class_mask])
            print(f"  {label}: {class_accuracy:.3f} ({np.sum(class_mask)} samples)")

    return {
        "classifier": classifier,
        "train_accuracy": float(train_score),
        "test_accuracy": float(test_accuracy),
        "cv_mean": float(cv_scores.mean()),
        "cv_std": float(cv_scores.std()),
        "classification_report": classification_report(
            y_test, y_pred, labels=unique_labels, target_names=present_labels, output_dict=True, zero_division=0
        ),
        "confusion_matrix": cm.tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description="Train OS detection classifier with enhanced evaluation")
    parser.add_argument("--data", type=Path, required=True, help="Path to training data JSON file")
    parser.add_argument(
        "--classifier",
        type=str,
        choices=["random_forest", "logistic_regression"],
        default="random_forest",
        help="Classifier type to train",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/os_detection_classifier.pkl"),
        help="Output path for trained classifier",
    )
    parser.add_argument("--test-split", type=float, default=0.2, help="Test set split ratio (default: 0.2)")
    parser.add_argument("--cv-folds", type=int, default=5, help="Number of cross-validation folds (default: 5)")
    parser.add_argument("--save-metrics", type=Path, default=None, help="Path to save training metrics JSON (optional)")

    args = parser.parse_args()

    print("=" * 80)
    print("ENHANCED OS DETECTION CLASSIFIER TRAINING")
    print("=" * 80)

    # Load training data
    print(f"\nLoading training data from {args.data}...")
    training_data = load_training_data(args.data)
    print(f"Loaded {len(training_data)} training samples")

    if len(training_data) < 10:
        print("⚠️  Warning: Very few training samples. Results may be unreliable.")

    # Check label distribution
    label_counts = {}
    for item in training_data:
        label = item.get("os_label", "Unknown")
        label_counts[label] = label_counts.get(label, 0) + 1

    print("\nLabel distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count}")

    # Initialize service
    print(f"\nInitializing OS detection service with {args.classifier} classifier...")
    service = OSDetectionService(classifier_type=args.classifier)

    # Prepare features
    X, y, article_ids = prepare_features_and_labels(training_data, service)

    if len(X) == 0:
        print("Error: No valid training samples after processing")
        return

    print(f"\nGenerated {len(X)} feature vectors with {X.shape[1]} dimensions")

    # Train and evaluate
    results = train_and_evaluate(
        X, y, classifier_type=args.classifier, test_size=args.test_split, cv_folds=args.cv_folds
    )

    # Save classifier
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import pickle

    with open(args.output, "wb") as f:
        pickle.dump(results["classifier"], f)

    print(f"\n✅ Classifier saved to: {args.output}")

    # Save metrics if requested
    if args.save_metrics:
        metrics = {
            "classifier_type": args.classifier,
            "training_samples": len(X),
            "train_accuracy": results["train_accuracy"],
            "test_accuracy": results["test_accuracy"],
            "cv_mean": results["cv_mean"],
            "cv_std": results["cv_std"],
            "classification_report": results["classification_report"],
            "confusion_matrix": results["confusion_matrix"],
        }
        args.save_metrics.parent.mkdir(parents=True, exist_ok=True)
        with open(args.save_metrics, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"✅ Metrics saved to: {args.save_metrics}")

    print("\n" + "=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)
    print("\nSummary:")
    print(f"  Training Accuracy: {results['train_accuracy']:.3f}")
    print(f"  Test Accuracy: {results['test_accuracy']:.3f}")
    print(f"  CV Accuracy: {results['cv_mean']:.3f} (+/- {results['cv_std']:.3f})")
    print("\nThe classifier is ready to use in OSDetectionService.")


if __name__ == "__main__":
    main()
