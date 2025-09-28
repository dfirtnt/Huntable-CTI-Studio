"""
Chunk Classifier Training for CTI Scraper

Trains a LightGBM classifier to predict excellent chunks for threat hunting.
"""

import json
import logging
import pickle
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime

try:
    import lightgbm as lgb
    from sklearn.model_selection import GroupKFold, train_test_split
    from sklearn.metrics import f1_score, roc_auc_score, classification_report, confusion_matrix
    from sklearn.preprocessing import StandardScaler
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    logging.warning("lightgbm or scikit-learn not available. Install with: pip install lightgbm scikit-learn")

from src.core.features.embed import FeatureEngineer

logger = logging.getLogger(__name__)


class ChunkClassifierTrainer:
    """Trains a LightGBM classifier for chunk quality prediction."""
    
    def __init__(self, model_path: str = "models/chunk_classifier.joblib"):
        """
        Initialize the trainer.
        
        Args:
            model_path: Path to save the trained model
        """
        self.model_path = Path(model_path)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.feature_engineer = FeatureEngineer()
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = None
        
        if not LIGHTGBM_AVAILABLE:
            logger.error("LightGBM not available. Cannot train classifier.")
            raise ImportError("LightGBM and scikit-learn are required for training.")
    
    def load_training_data(self, jsonl_path: str) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """
        Load training data from JSONL file.
        
        Args:
            jsonl_path: Path to JSONL file with training examples
            
        Returns:
            Tuple of (features, labels, article_ids)
        """
        logger.info(f"Loading training data from {jsonl_path}")
        
        examples = []
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        example = json.loads(line)
                        examples.append(example)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON line: {e}")
                        continue
        
        logger.info(f"Loaded {len(examples)} training examples")
        
        # Extract features and labels
        features_list = []
        labels = []
        article_ids = []
        
        for example in examples:
            try:
                # Extract text and metadata
                text = example['text']
                metadata = example.get('meta', {})
                
                # Generate features
                features = self.feature_engineer.extract_features(text, metadata)
                embeddings = self.feature_engineer.generate_single_embedding(text)
                
                # Combine features
                combined_features = self.feature_engineer.combine_features(embeddings, features)
                
                features_list.append(combined_features)
                labels.append(1 if example['labels']['excellent'] else 0)
                article_ids.append(example['article_id'])
                
            except Exception as e:
                logger.error(f"Failed to process example: {e}")
                continue
        
        if not features_list:
            raise ValueError("No valid training examples found")
        
        # Convert to numpy arrays
        X = np.array(features_list)
        y = np.array(labels)
        article_ids = np.array(article_ids)
        
        logger.info(f"Prepared training data: {X.shape[0]} samples, {X.shape[1]} features")
        logger.info(f"Class distribution: {np.bincount(y)}")
        
        return X, y, article_ids
    
    def train_model(self, X: np.ndarray, y: np.ndarray, article_ids: np.ndarray, 
                   test_size: float = 0.2, random_state: int = 42) -> Dict[str, Any]:
        """
        Train the LightGBM classifier.
        
        Args:
            X: Feature matrix
            y: Labels
            article_ids: Article IDs for group splitting
            test_size: Fraction of data to use for testing
            random_state: Random seed
            
        Returns:
            Dictionary with training results and metrics
        """
        logger.info("Starting model training...")
        
        # Split data by article to avoid leakage
        unique_articles = np.unique(article_ids)
        train_articles, test_articles = train_test_split(
            unique_articles, test_size=test_size, random_state=random_state
        )
        
        # Create train/test masks
        train_mask = np.isin(article_ids, train_articles)
        test_mask = np.isin(article_ids, test_articles)
        
        X_train, X_test = X[train_mask], X[test_mask]
        y_train, y_test = y[train_mask], y[test_mask]
        
        logger.info(f"Train set: {X_train.shape[0]} samples")
        logger.info(f"Test set: {X_test.shape[0]} samples")
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Prepare LightGBM datasets
        train_data = lgb.Dataset(X_train_scaled, label=y_train)
        valid_data = lgb.Dataset(X_test_scaled, label=y_test, reference=train_data)
        
        # LightGBM parameters
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1,
            'random_state': random_state
        }
        
        # Train model
        logger.info("Training LightGBM model...")
        self.model = lgb.train(
            params,
            train_data,
            valid_sets=[valid_data],
            num_boost_round=1000,
            callbacks=[lgb.early_stopping(stopping_rounds=50), lgb.log_evaluation(period=100)]
        )
        
        # Make predictions
        y_pred_proba = self.model.predict(X_test_scaled)
        y_pred = (y_pred_proba > 0.5).astype(int)
        
        # Calculate metrics
        metrics = self._calculate_metrics(y_test, y_pred, y_pred_proba)
        
        # Feature importance
        feature_importance = self._get_feature_importance()
        
        # Save model
        self._save_model()
        
        results = {
            'metrics': metrics,
            'feature_importance': feature_importance,
            'model_path': str(self.model_path),
            'training_date': datetime.now().isoformat(),
            'n_samples': len(X),
            'n_features': X.shape[1],
            'class_distribution': np.bincount(y).tolist()
        }
        
        logger.info(f"Training completed. F1 Score: {metrics['f1_score']:.4f}, AUROC: {metrics['auroc']:.4f}")
        
        return results
    
    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray, y_pred_proba: np.ndarray) -> Dict[str, float]:
        """Calculate evaluation metrics."""
        return {
            'f1_score': f1_score(y_true, y_pred),
            'auroc': roc_auc_score(y_true, y_pred_proba),
            'precision': y_pred.sum() / max(y_pred.sum(), 1),
            'recall': y_pred.sum() / max(y_true.sum(), 1),
            'accuracy': (y_true == y_pred).mean()
        }
    
    def _get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        if not self.model:
            return {}
        
        importance = self.model.feature_importance(importance_type='gain')
        feature_names = self._get_feature_names()
        
        # Sort by importance
        feature_importance = dict(zip(feature_names, importance))
        feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
        
        return feature_importance
    
    def _get_feature_names(self) -> List[str]:
        """Get feature names for the model."""
        if self.feature_names is None:
            # Generate feature names based on the feature engineer
            embedding_names = [f'embedding_{i}' for i in range(384)]  # all-MiniLM-L6-v2 dimension
            engineered_names = self.feature_engineer.get_feature_names()
            self.feature_names = embedding_names + engineered_names
        
        return self.feature_names
    
    def _save_model(self):
        """Save the trained model and scaler."""
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self._get_feature_names(),
            'training_date': datetime.now().isoformat()
        }
        
        with open(self.model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Model saved to {self.model_path}")
    
    def load_model(self) -> bool:
        """
        Load a trained model.
        
        Returns:
            True if model loaded successfully
        """
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.feature_names = model_data['feature_names']
            
            logger.info(f"Model loaded from {self.model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def predict(self, text: str, metadata: Dict[str, Any] = None) -> float:
        """
        Predict excellence probability for a chunk.
        
        Args:
            text: Chunk text
            metadata: Optional metadata
            
        Returns:
            Excellence probability (0-1)
        """
        if not self.model:
            logger.error("Model not loaded")
            return 0.0
        
        try:
            # Extract features
            features = self.feature_engineer.extract_features(text, metadata)
            embeddings = self.feature_engineer.generate_single_embedding(text)
            combined_features = self.feature_engineer.combine_features(embeddings, features)
            
            # Scale features
            X_scaled = self.scaler.transform(combined_features.reshape(1, -1))
            
            # Make prediction
            probability = self.model.predict(X_scaled)[0]
            
            return float(probability)
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return 0.0
    
    def cross_validate(self, X: np.ndarray, y: np.ndarray, article_ids: np.ndarray, 
                      n_splits: int = 5) -> Dict[str, List[float]]:
        """
        Perform cross-validation with group splitting.
        
        Args:
            X: Feature matrix
            y: Labels
            article_ids: Article IDs for group splitting
            n_splits: Number of CV folds
            
        Returns:
            Dictionary with CV results
        """
        logger.info(f"Performing {n_splits}-fold cross-validation...")
        
        group_kfold = GroupKFold(n_splits=n_splits)
        
        cv_scores = {
            'f1_scores': [],
            'auroc_scores': [],
            'precision_scores': [],
            'recall_scores': []
        }
        
        for fold, (train_idx, test_idx) in enumerate(group_kfold.split(X, y, article_ids)):
            logger.info(f"Fold {fold + 1}/{n_splits}")
            
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model for this fold
            train_data = lgb.Dataset(X_train_scaled, label=y_train)
            valid_data = lgb.Dataset(X_test_scaled, label=y_test, reference=train_data)
            
            params = {
                'objective': 'binary',
                'metric': 'binary_logloss',
                'boosting_type': 'gbdt',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'feature_fraction': 0.9,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'verbose': -1
            }
            
            model = lgb.train(
                params,
                train_data,
                valid_sets=[valid_data],
                num_boost_round=1000,
                callbacks=[lgb.early_stopping(stopping_rounds=50), lgb.log_evaluation(period=0)]
            )
            
            # Predictions
            y_pred_proba = model.predict(X_test_scaled)
            y_pred = (y_pred_proba > 0.5).astype(int)
            
            # Calculate metrics
            cv_scores['f1_scores'].append(f1_score(y_test, y_pred))
            cv_scores['auroc_scores'].append(roc_auc_score(y_test, y_pred_proba))
            cv_scores['precision_scores'].append(y_pred.sum() / max(y_pred.sum(), 1))
            cv_scores['recall_scores'].append(y_pred.sum() / max(y_test.sum(), 1))
        
        # Calculate mean and std
        results = {}
        for metric, scores in cv_scores.items():
            results[f'{metric}_mean'] = np.mean(scores)
            results[f'{metric}_std'] = np.std(scores)
        
        logger.info(f"Cross-validation results: F1 = {results['f1_scores_mean']:.4f} ± {results['f1_scores_std']:.4f}")
        logger.info(f"Cross-validation results: AUROC = {results['auroc_scores_mean']:.4f} ± {results['auroc_scores_std']:.4f}")
        
        return results


# Global trainer instance
trainer = ChunkClassifierTrainer()


def train_classifier(jsonl_path: str, model_path: str = None) -> Dict[str, Any]:
    """
    Convenience function to train the classifier.
    
    Args:
        jsonl_path: Path to JSONL training data
        model_path: Optional path to save model
        
    Returns:
        Training results
    """
    if model_path:
        trainer.model_path = Path(model_path)
        trainer.model_path.parent.mkdir(parents=True, exist_ok=True)
    
    X, y, article_ids = trainer.load_training_data(jsonl_path)
    results = trainer.train_model(X, y, article_ids)
    
    return results


def predict_excellent_probability(text: str, metadata: Dict[str, Any] = None) -> float:
    """
    Convenience function to predict excellence probability.
    
    Args:
        text: Chunk text
        metadata: Optional metadata
        
    Returns:
        Excellence probability (0-1)
    """
    return trainer.predict(text, metadata)
