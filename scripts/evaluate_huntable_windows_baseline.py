#!/usr/bin/env python3
"""
Evaluate baseline performance for Windows huntables detection.

Tests multiple baseline approaches before training the hybrid classifier:
1. Keyword-only (LOLBAS count threshold)
2. Keyword features only (no embeddings)
3. Embedding features only (no keywords)
4. Current OSDetectionService approach

This establishes baseline metrics to measure improvement.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    precision_score, recall_score, f1_score, roc_auc_score
)
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.os_detection_service import OSDetectionService
from scripts.train_huntable_windows_classifier import (
    load_training_data,
    extract_keyword_features,
    prepare_features_and_labels
)


def baseline_keyword_threshold(
    training_data: List[Dict[str, Any]],
    threshold: int = 1
) -> Dict[str, Any]:
    """Baseline: Simple keyword threshold (if LOLBAS count >= threshold, positive)."""
    print(f"\n{'='*80}")
    print(f"BASELINE 1: Keyword Threshold (LOLBAS >= {threshold})")
    print(f"{'='*80}")
    
    y_true = []
    y_pred = []
    
    for item in training_data:
        label = item.get('label', 0)
        lolbas_count = len(item.get('lolbas_matches', []) or [])
        
        y_true.append(label)
        y_pred.append(1 if lolbas_count >= threshold else 0)
    
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    
    print(f"\nResults:")
    print(f"  Accuracy: {accuracy:.3f}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall: {recall:.3f}")
    print(f"  F1 Score: {f1:.3f}")
    
    cm = confusion_matrix(y_true, y_pred)
    print(f"\nConfusion Matrix:")
    print(f"                Predicted")
    print(f"              No    Yes")
    print(f"Actual No   {cm[0][0]:4d}  {cm[0][1]:4d}")
    print(f"       Yes   {cm[1][0]:4d}  {cm[1][1]:4d}")
    
    return {
        "method": f"keyword_threshold_{threshold}",
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "confusion_matrix": cm.tolist()
    }


def baseline_keyword_features_only(
    training_data: List[Dict[str, Any]],
    classifier_type: str = "random_forest"
) -> Dict[str, Any]:
    """Baseline: Classifier on keyword features only (no embeddings)."""
    print(f"\n{'='*80}")
    print(f"BASELINE 2: Keyword Features Only ({classifier_type})")
    print(f"{'='*80}")
    
    # Extract keyword features
    X_keyword = []
    y = []
    
    for item in training_data:
        keyword_features = extract_keyword_features(item)
        X_keyword.append(keyword_features)
        y.append(item.get('label', 0))
    
    X = np.array(X_keyword)
    y = np.array(y)
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train
    if classifier_type == "random_forest":
        classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            class_weight='balanced'
        )
    else:
        classifier = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight='balanced'
        )
    
    classifier.fit(X_train_scaled, y_train)
    
    # Evaluate
    y_pred = classifier.predict(X_test_scaled)
    y_pred_proba = classifier.predict_proba(X_test_scaled)[:, 1]
    
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_pred_proba)
    
    print(f"\nResults:")
    print(f"  Accuracy: {accuracy:.3f}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall: {recall:.3f}")
    print(f"  F1 Score: {f1:.3f}")
    print(f"  ROC-AUC: {roc_auc:.3f}")
    
    cm = confusion_matrix(y_test, y_pred)
    print(f"\nConfusion Matrix:")
    print(f"                Predicted")
    print(f"              No    Yes")
    print(f"Actual No   {cm[0][0]:4d}  {cm[0][1]:4d}")
    print(f"       Yes   {cm[1][0]:4d}  {cm[1][1]:4d}")
    
    return {
        "method": f"keyword_features_only_{classifier_type}",
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": float(roc_auc),
        "confusion_matrix": cm.tolist()
    }


def baseline_embedding_features_only(
    training_data: List[Dict[str, Any]],
    classifier_type: str = "random_forest"
) -> Dict[str, Any]:
    """Baseline: Classifier on BERT embeddings only (no keywords)."""
    print(f"\n{'='*80}")
    print(f"BASELINE 3: Embedding Features Only ({classifier_type})")
    print(f"{'='*80}")
    
    service = OSDetectionService()
    
    # Extract embedding features
    X_embedding = []
    y = []
    
    print("Generating embeddings...")
    for i, item in enumerate(training_data, 1):
        content = item.get('content', '')
        if not content:
            continue
        
        if i % 50 == 0:
            print(f"  Processed {i}/{len(training_data)} articles...")
        
        embedding = service._get_embedding(content[:2000])
        X_embedding.append(embedding)
        y.append(item.get('label', 0))
    
    X = np.array(X_embedding)
    y = np.array(y)
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train
    if classifier_type == "random_forest":
        classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            class_weight='balanced'
        )
    else:
        classifier = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight='balanced'
        )
    
    classifier.fit(X_train_scaled, y_train)
    
    # Evaluate
    y_pred = classifier.predict(X_test_scaled)
    y_pred_proba = classifier.predict_proba(X_test_scaled)[:, 1]
    
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_pred_proba)
    
    print(f"\nResults:")
    print(f"  Accuracy: {accuracy:.3f}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall: {recall:.3f}")
    print(f"  F1 Score: {f1:.3f}")
    print(f"  ROC-AUC: {roc_auc:.3f}")
    
    cm = confusion_matrix(y_test, y_pred)
    print(f"\nConfusion Matrix:")
    print(f"                Predicted")
    print(f"              No    Yes")
    print(f"Actual No   {cm[0][0]:4d}  {cm[0][1]:4d}")
    print(f"       Yes   {cm[1][0]:4d}  {cm[1][1]:4d}")
    
    return {
        "method": f"embedding_features_only_{classifier_type}",
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": float(roc_auc),
        "confusion_matrix": cm.tolist()
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate baseline performance for Windows huntables detection"
    )
    parser.add_argument(
        '--data',
        type=Path,
        required=True,
        help='Path to training data JSON file'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('outputs/huntable_windows_baseline_results.json'),
        help='Output path for baseline results JSON'
    )
    parser.add_argument(
        '--classifier',
        type=str,
        choices=['random_forest', 'logistic_regression'],
        default='random_forest',
        help='Classifier type for feature-based baselines'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("HUNTABLE WINDOWS BASELINE EVALUATION")
    print("="*80)
    
    # Load training data
    print(f"\nLoading training data from {args.data}...")
    training_data = load_training_data(args.data)
    print(f"Loaded {len(training_data)} samples")
    
    # Check label distribution
    positive_count = sum(1 for x in training_data if x.get('label') == 1)
    negative_count = sum(1 for x in training_data if x.get('label') == 0)
    print(f"  Positive: {positive_count}, Negative: {negative_count}")
    
    # Run baselines
    results = {
        "evaluated_at": datetime.now().isoformat(),
        "training_samples": len(training_data),
        "positive_samples": positive_count,
        "negative_samples": negative_count,
        "baselines": []
    }
    
    # Baseline 1: Keyword threshold
    baseline1 = baseline_keyword_threshold(training_data, threshold=1)
    results["baselines"].append(baseline1)
    
    # Baseline 2: Keyword features only
    baseline2 = baseline_keyword_features_only(training_data, args.classifier)
    results["baselines"].append(baseline2)
    
    # Baseline 3: Embedding features only
    baseline3 = baseline_embedding_features_only(training_data, args.classifier)
    results["baselines"].append(baseline3)
    
    # Summary
    print(f"\n{'='*80}")
    print("BASELINE SUMMARY")
    print(f"{'='*80}")
    print(f"\n{'Method':<40} {'Accuracy':<10} {'F1':<10} {'ROC-AUC':<10}")
    print("-" * 80)
    
    for baseline in results["baselines"]:
        method = baseline["method"]
        accuracy = baseline["accuracy"]
        f1 = baseline.get("f1", 0.0)
        roc_auc = baseline.get("roc_auc", 0.0)
        print(f"{method:<40} {accuracy:<10.3f} {f1:<10.3f} {roc_auc:<10.3f}")
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Baseline results saved to: {args.output}")
    print(f"\nNext step: Train hybrid classifier and compare:")
    print(f"  python scripts/train_huntable_windows_classifier.py --data {args.data}")


if __name__ == "__main__":
    main()

