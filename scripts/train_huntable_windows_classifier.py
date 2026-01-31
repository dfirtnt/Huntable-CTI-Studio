#!/usr/bin/env python3
"""
Train hybrid classifier for Windows huntables detection.

Combines:
1. LOLBAS keyword features (explicit Windows indicators)
2. CTI-BERT embeddings (semantic understanding)

Binary classification: Does this article contain Windows-based huntables?
"""

import argparse
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.os_detection_service import OSDetectionService


def load_training_data(data_path: Path) -> list[dict[str, Any]]:
    """Load training data from JSON file."""
    with open(data_path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Training data must be a list of objects")

    return data


def extract_keyword_features(article: dict[str, Any], max_length: int = 2000) -> np.ndarray:
    """
    Extract keyword-based features from article.

    Features:
    - LOLBAS match count
    - Perfect keyword match count
    - Good keyword match count
    - Binary indicators for key LOLBAS executables
    """
    content = article.get("content", "")[:max_length].lower()

    # Count matches
    lolbas_count = len(article.get("lolbas_matches", []) or [])
    perfect_count = len(article.get("perfect_matches", []) or [])
    good_count = len(article.get("good_matches", []) or [])

    # Check for key LOLBAS executables in content
    key_lolbas = [
        "powershell.exe",
        "cmd.exe",
        "wmic.exe",
        "certutil.exe",
        "schtasks.exe",
        "reg.exe",
        "rundll32.exe",
        "bitsadmin.exe",
    ]

    key_lolbas_present = [1 if exe in content else 0 for exe in key_lolbas]

    # Combine features
    features = np.array([lolbas_count, perfect_count, good_count, *key_lolbas_present], dtype=np.float32)

    return features


def prepare_features_and_labels(
    training_data: list[dict[str, Any]],
    service: OSDetectionService,
    use_embeddings: bool = True,
    use_keywords: bool = True,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """
    Prepare hybrid features (keywords + embeddings) and labels.

    Returns:
        X: Feature matrix (n_samples, n_features)
        y: Labels (n_samples,)
        article_ids: Article IDs for reference
    """
    X_keyword = []
    X_embedding = []
    y = []
    article_ids = []

    print("Generating features from training data...")
    for i, item in enumerate(training_data, 1):
        content = item.get("content", "")
        label = item.get("label", 0)
        article_id = item.get("article_id", i)

        if not content:
            continue

        if i % 10 == 0:
            print(f"  Processed {i}/{len(training_data)} articles...")

        # Extract keyword features
        if use_keywords:
            keyword_features = extract_keyword_features(item)
            X_keyword.append(keyword_features)

        # Extract BERT embeddings
        if use_embeddings:
            embedding = service._get_embedding(content[:2000])
            X_embedding.append(embedding)

        y.append(label)
        article_ids.append(article_id)

    # Combine features
    if use_keywords and use_embeddings:
        X_keyword = np.array(X_keyword)
        X_embedding = np.array(X_embedding)
        X = np.hstack([X_keyword, X_embedding])
        print(
            f"  Combined features: {X_keyword.shape[1]} keyword + {X_embedding.shape[1]} embedding = {X.shape[1]} total"
        )
        print(
            f"    Keyword breakdown: 3 counts + 8 LOLBAS + 64 perfect + 16 obfuscation = {X_keyword.shape[1]} features"
        )
    elif use_keywords:
        X = np.array(X_keyword)
        print(f"  Using keyword features only: {X.shape[1]} features")
    elif use_embeddings:
        X = np.array(X_embedding)
        print(f"  Using embedding features only: {X.shape[1]} features")
    else:
        raise ValueError("Must use at least one feature type")

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

    # Scale features (important for combining keyword counts with embeddings)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train classifier
    if classifier_type == "random_forest":
        classifier = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=random_state, class_weight="balanced"
        )
    else:
        classifier = LogisticRegression(max_iter=1000, random_state=random_state, class_weight="balanced")

    print(f"\nTraining {classifier_type} classifier...")
    classifier.fit(X_train_scaled, y_train)

    # Training accuracy
    train_score = classifier.score(X_train_scaled, y_train)
    print(f"  Training accuracy: {train_score:.3f}")

    # Cross-validation
    print(f"\nPerforming {cv_folds}-fold cross-validation...")
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    cv_scores = cross_val_score(classifier, X_train_scaled, y_train, cv=cv, scoring="accuracy")
    print(f"  CV Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})")

    # Test evaluation
    print("\nEvaluating on test set...")
    y_pred = classifier.predict(X_test_scaled)
    test_accuracy = accuracy_score(y_test, y_pred)

    # ROC-AUC (for binary classification)
    y_pred_proba = classifier.predict_proba(X_test_scaled)[:, 1]
    roc_auc = roc_auc_score(y_test, y_pred_proba)

    print(f"  Test accuracy: {test_accuracy:.3f}")
    print(f"  ROC-AUC: {roc_auc:.3f}")

    # Detailed classification report
    print("\nClassification Report:")
    print(
        classification_report(
            y_test, y_pred, target_names=["No Windows Huntables", "Windows Huntables"], zero_division=0
        )
    )

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    print("\nConfusion Matrix:")
    print("                Predicted")
    print("              No    Yes")
    print(f"Actual No   {cm[0][0]:4d}  {cm[0][1]:4d}")
    print(f"       Yes   {cm[1][0]:4d}  {cm[1][1]:4d}")

    return {
        "classifier": classifier,
        "scaler": scaler,
        "train_accuracy": float(train_score),
        "test_accuracy": float(test_accuracy),
        "roc_auc": float(roc_auc),
        "cv_mean": float(cv_scores.mean()),
        "cv_std": float(cv_scores.std()),
        "classification_report": classification_report(
            y_test,
            y_pred,
            target_names=["No Windows Huntables", "Windows Huntables"],
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": cm.tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description="Train hybrid classifier for Windows huntables detection")
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
        default=Path("models/huntable_windows_classifier.pkl"),
        help="Output path for trained classifier",
    )
    parser.add_argument(
        "--scaler-output",
        type=Path,
        default=Path("models/huntable_windows_scaler.pkl"),
        help="Output path for feature scaler",
    )
    parser.add_argument("--test-split", type=float, default=0.2, help="Test set split ratio (default: 0.2)")
    parser.add_argument("--cv-folds", type=int, default=5, help="Number of cross-validation folds (default: 5)")
    parser.add_argument("--save-metrics", type=Path, default=None, help="Path to save training metrics JSON (optional)")
    parser.add_argument("--no-embeddings", action="store_true", help="Use keyword features only (no BERT embeddings)")
    parser.add_argument("--no-keywords", action="store_true", help="Use BERT embeddings only (no keyword features)")

    args = parser.parse_args()

    if args.no_embeddings and args.no_keywords:
        print("Error: Cannot disable both embeddings and keywords")
        return

    print("=" * 80)
    print("HUNTABLE WINDOWS CLASSIFIER TRAINING (HYBRID)")
    print("=" * 80)

    # Load training data
    print(f"\nLoading training data from {args.data}...")
    training_data = load_training_data(args.data)
    print(f"Loaded {len(training_data)} training samples")

    if len(training_data) < 20:
        print("⚠️  Warning: Very few training samples. Results may be unreliable.")

    # Check label distribution
    label_counts = {}
    for item in training_data:
        label = item.get("label", 0)
        label_counts[label] = label_counts.get(label, 0) + 1

    print("\nLabel distribution:")
    print(f"  Positive (Windows huntables): {label_counts.get(1, 0)}")
    print(f"  Negative (No Windows huntables): {label_counts.get(0, 0)}")

    # Initialize service
    print("\nInitializing OS detection service...")
    service = OSDetectionService()

    # Prepare features
    X, y, article_ids = prepare_features_and_labels(
        training_data, service, use_embeddings=not args.no_embeddings, use_keywords=not args.no_keywords
    )

    if len(X) == 0:
        print("Error: No valid training samples after processing")
        return

    print(f"\nGenerated {len(X)} feature vectors with {X.shape[1]} dimensions")

    # Train and evaluate
    results = train_and_evaluate(
        X, y, classifier_type=args.classifier, test_size=args.test_split, cv_folds=args.cv_folds
    )

    # Save classifier and scaler
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "wb") as f:
        pickle.dump(results["classifier"], f)

    args.scaler_output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.scaler_output, "wb") as f:
        pickle.dump(results["scaler"], f)

    print(f"\n✅ Classifier saved to: {args.output}")
    print(f"✅ Scaler saved to: {args.scaler_output}")

    # Save metrics if requested
    if args.save_metrics:
        metrics = {
            "classifier_type": args.classifier,
            "training_samples": len(X),
            "feature_dimensions": int(X.shape[1]),
            "uses_embeddings": not args.no_embeddings,
            "uses_keywords": not args.no_keywords,
            "train_accuracy": results["train_accuracy"],
            "test_accuracy": results["test_accuracy"],
            "roc_auc": results["roc_auc"],
            "cv_mean": results["cv_mean"],
            "cv_std": results["cv_std"],
            "classification_report": results["classification_report"],
            "confusion_matrix": results["confusion_matrix"],
            "trained_at": datetime.now().isoformat(),
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
    print(f"  ROC-AUC: {results['roc_auc']:.3f}")
    print(f"  CV Accuracy: {results['cv_mean']:.3f} (+/- {results['cv_std']:.3f})")
    print("\nThe classifier is ready to use for Windows huntables detection.")


if __name__ == "__main__":
    main()
