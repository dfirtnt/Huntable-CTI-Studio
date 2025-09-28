"""
Chunk Prediction for CTI Scraper

Batch prediction of excellence probability for chunks.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import numpy as np

from src.core.models.train_classifier import ChunkClassifierTrainer
from src.core.features.embed import FeatureEngineer

logger = logging.getLogger(__name__)


class ChunkPredictor:
    """Predicts excellence probability for chunks."""
    
    def __init__(self, model_path: str = "models/chunk_classifier.joblib"):
        """
        Initialize the predictor.
        
        Args:
            model_path: Path to the trained model
        """
        self.model_path = Path(model_path)
        self.trainer = ChunkClassifierTrainer(model_path)
        self.feature_engineer = FeatureEngineer()
        
        # Load model
        if not self.trainer.load_model():
            logger.warning(f"Failed to load model from {model_path}")
    
    def predict_chunk(self, text: str, metadata: Dict[str, Any] = None) -> float:
        """
        Predict excellence probability for a single chunk.
        
        Args:
            text: Chunk text
            metadata: Optional metadata
            
        Returns:
            Excellence probability (0-1)
        """
        return self.trainer.predict(text, metadata)
    
    def predict_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Predict excellence probability for multiple chunks.
        
        Args:
            chunks: List of chunk dictionaries with 'text' and optional 'metadata' keys
            
        Returns:
            List of chunks with added 'excellent_prob' field
        """
        results = []
        
        for chunk in chunks:
            try:
                text = chunk.get('text', '')
                metadata = chunk.get('metadata', {})
                
                if not text:
                    logger.warning("Empty text in chunk")
                    chunk['excellent_prob'] = 0.0
                else:
                    prob = self.predict_chunk(text, metadata)
                    chunk['excellent_prob'] = prob
                
                results.append(chunk)
                
            except Exception as e:
                logger.error(f"Failed to predict chunk: {e}")
                chunk['excellent_prob'] = 0.0
                results.append(chunk)
        
        logger.info(f"Predicted probabilities for {len(results)} chunks")
        return results
    
    def predict_jsonl(self, input_path: str, output_path: str = None) -> List[Dict[str, Any]]:
        """
        Predict excellence probability for chunks in JSONL file.
        
        Args:
            input_path: Path to input JSONL file
            output_path: Optional path to output JSONL file
            
        Returns:
            List of chunks with predictions
        """
        logger.info(f"Loading chunks from {input_path}")
        
        chunks = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        chunk = json.loads(line)
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON line: {e}")
                        continue
        
        logger.info(f"Loaded {len(chunks)} chunks")
        
        # Make predictions
        results = self.predict_chunks(chunks)
        
        # Save results if output path provided
        if output_path:
            self._save_jsonl(results, output_path)
        
        return results
    
    def predict_database_chunks(self, chunk_ids: List[int], db_manager) -> List[Dict[str, Any]]:
        """
        Predict excellence probability for chunks from database.
        
        Args:
            chunk_ids: List of chunk IDs
            db_manager: Database manager instance
            
        Returns:
            List of chunks with predictions
        """
        logger.info(f"Predicting for {len(chunk_ids)} database chunks")
        
        chunks = []
        for chunk_id in chunk_ids:
            try:
                # Get chunk from database
                chunk_data = await db_manager.get_chunk(chunk_id)
                if chunk_data:
                    chunks.append({
                        'chunk_id': chunk_id,
                        'text': chunk_data.text,
                        'metadata': {
                            'article_id': chunk_data.article_id,
                            'start_offset': chunk_data.start_offset,
                            'end_offset': chunk_data.end_offset,
                            'created_at': chunk_data.created_at.isoformat() if chunk_data.created_at else None
                        }
                    })
            except Exception as e:
                logger.error(f"Failed to get chunk {chunk_id}: {e}")
                continue
        
        # Make predictions
        results = self.predict_chunks(chunks)
        
        # Update database with predictions
        for result in results:
            try:
                chunk_id = result['chunk_id']
                prob = result['excellent_prob']
                
                # Update chunk score in database
                await db_manager.update_chunk_score(chunk_id, prob)
                
            except Exception as e:
                logger.error(f"Failed to update chunk {chunk_id}: {e}")
                continue
        
        logger.info(f"Updated predictions for {len(results)} chunks in database")
        return results
    
    def _save_jsonl(self, data: List[Dict[str, Any]], output_path: str):
        """Save data to JSONL file."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        logger.info(f"Saved predictions to {output_path}")
    
    def get_prediction_stats(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about predictions.
        
        Args:
            predictions: List of predictions with 'excellent_prob' field
            
        Returns:
            Dictionary with prediction statistics
        """
        if not predictions:
            return {}
        
        probs = [p.get('excellent_prob', 0.0) for p in predictions]
        
        stats = {
            'total_chunks': len(predictions),
            'mean_probability': np.mean(probs),
            'std_probability': np.std(probs),
            'min_probability': np.min(probs),
            'max_probability': np.max(probs),
            'median_probability': np.median(probs),
            'excellent_chunks': sum(1 for p in probs if p > 0.5),
            'excellent_percentage': sum(1 for p in probs if p > 0.5) / len(probs) * 100,
            'high_quality_chunks': sum(1 for p in probs if p > 0.7),
            'high_quality_percentage': sum(1 for p in probs if p > 0.7) / len(probs) * 100
        }
        
        return stats


# Global predictor instance
predictor = ChunkPredictor()


def predict_excellent_probability(text: str, metadata: Dict[str, Any] = None) -> float:
    """
    Convenience function to predict excellence probability.
    
    Args:
        text: Chunk text
        metadata: Optional metadata
        
    Returns:
        Excellence probability (0-1)
    """
    return predictor.predict_chunk(text, metadata)


def predict_chunks_batch(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience function for batch prediction.
    
    Args:
        chunks: List of chunk dictionaries
        
    Returns:
        List of chunks with predictions
    """
    return predictor.predict_chunks(chunks)


def predict_jsonl_file(input_path: str, output_path: str = None) -> List[Dict[str, Any]]:
    """
    Convenience function to predict from JSONL file.
    
    Args:
        input_path: Path to input JSONL file
        output_path: Optional path to output JSONL file
        
    Returns:
        List of chunks with predictions
    """
    return predictor.predict_jsonl(input_path, output_path)
