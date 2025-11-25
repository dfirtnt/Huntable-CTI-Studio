#!/usr/bin/env python3
"""
Train OS Detection Classifier

This script trains a RandomForest or LogisticRegression classifier on labeled CTI text
for OS detection. The classifier uses CTI-BERT embeddings as features.

Usage:
    python3 train_os_detection_classifier.py --data training_data.json --classifier random_forest
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

from src.services.os_detection_service import OSDetectionService

def load_training_data(data_path: Path) -> List[Dict[str, Any]]:
    """Load training data from JSON file."""
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Expected format: [{"content": "...", "os_label": "Windows"}, ...]
    if not isinstance(data, list):
        raise ValueError("Training data must be a list of objects")
    
    return data

def main():
    parser = argparse.ArgumentParser(description="Train OS detection classifier")
    parser.add_argument(
        '--data',
        type=Path,
        required=True,
        help='Path to training data JSON file'
    )
    parser.add_argument(
        '--classifier',
        type=str,
        choices=['random_forest', 'logistic_regression'],
        default='random_forest',
        help='Classifier type to train'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('models/os_detection_classifier.pkl'),
        help='Output path for trained classifier'
    )
    
    args = parser.parse_args()
    
    # Load training data
    print(f"Loading training data from {args.data}...")
    training_data = load_training_data(args.data)
    print(f"Loaded {len(training_data)} training samples")
    
    # Initialize service
    print(f"Initializing OS detection service with {args.classifier} classifier...")
    service = OSDetectionService(classifier_type=args.classifier)
    
    # Train classifier
    print("Training classifier...")
    metrics = service.train_classifier(training_data, save_path=args.output)
    
    print("\nTraining complete!")
    print(f"  Training samples: {metrics['training_samples']}")
    print(f"  Train accuracy: {metrics['train_accuracy']:.3f}")
    print(f"  Classifier type: {metrics['classifier_type']}")
    print(f"  Saved to: {metrics['saved_path']}")

if __name__ == "__main__":
    main()


