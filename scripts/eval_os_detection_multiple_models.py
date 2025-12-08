#!/usr/bin/env python3
"""
Evaluate OS Detection with multiple embedding models and local LLMs.

Tests:
- CTI-BERT (ibm-research/CTI-BERT)
- SEC-BERT (nlpaueb/sec-bert-base) 
- deepseek/deepseek-r1-0528-qwen3-8b (via LMStudio)
- Other recommended local models
"""

import sys
import asyncio
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.os_detection_service import OSDetectionService
from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.utils.content_filter import ContentFilter

# Import the manual test data
from scripts.eval_os_detection_manual import MANUAL_TEST_DATA, normalize_os_label, calculate_accuracy, calculate_confusion_matrix


# Recommended local models for OS detection
# Updated based on available LMStudio models
RECOMMENDED_MODELS = {
    'cti-bert': {
        'embedding': 'ibm-research/CTI-BERT',
        'fallback': None,
        'description': 'CTI-BERT (designed for threat intelligence)'
    },
    'sec-bert': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': None,
        'description': 'SEC-BERT (security domain embeddings)'
    },
    # Available in LMStudio
    'deepseek-r1-qwen3-8b': {
        'embedding': 'nlpaueb/sec-bert-base',  # Use SEC-BERT for embeddings
        'fallback': 'deepseek/deepseek-r1-0528-qwen3-8b',
        'description': 'DeepSeek R1 Qwen3 8B (reasoning model - AVAILABLE)'
    },
    'mistral-7b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'mistralai/mistral-7b-instruct-v0.3',
        'description': 'Mistral 7B Instruct (current default - AVAILABLE)'
    },
    'qwen3-4b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'qwen/qwen3-4b-2507',
        'description': 'Qwen3 4B 2507 (small, efficient - AVAILABLE)'
    },
    'qwen2-7b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'qwen2-7b-instruct',
        'description': 'Qwen2 7B Instruct (good balance - AVAILABLE)'
    },
    'llama-3.1-8b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'meta-llama-3.1-8b-instruct',
        'description': 'Llama 3.1 8B Instruct (general purpose - AVAILABLE)'
    },
    'llama-3-8b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'meta-llama-3-8b-instruct',
        'description': 'Llama 3 8B Instruct (general purpose - AVAILABLE)'
    },
    'llama-3-13b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'meta-llama-3-13b-instruct',
        'description': 'Llama 3 13B Instruct (larger, more capable - AVAILABLE)'
    },
    'llama-3.3-70b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'meta/llama-3.3-70b',
        'description': 'Llama 3.3 70B (very capable, slower - AVAILABLE)'
    },
    'phi-3-mini': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'phi-3-mini-3.8b-instructiontuned-alpaca',
        'description': 'Phi-3 Mini 3.8B (small, fast - AVAILABLE)'
    },
    'llama-3.2-1b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'llama-3.2-1b-instruct',
        'description': 'Llama 3.2 1B (very small, very fast - AVAILABLE)'
    },
    'mixtral-8x7b': {
        'embedding': 'nlpaueb/sec-bert-base',
        'fallback': 'mixtral-8x7b-instruct-v0.1',
        'description': 'Mixtral 8x7B Instruct (very capable - AVAILABLE)'
    }
}


async def run_os_detection_with_model(
    article_id: int,
    content: Optional[str],
    embedding_model: str,
    fallback_model: Optional[str] = None,
    junk_filter_threshold: float = 0.8,
    db_session=None
) -> Dict[str, Any]:
    """Run OS detection with specified embedding model and optional fallback."""
    # Use provided session or create new one
    if db_session is None:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        should_close = True
    else:
        should_close = False
    
    try:
        # Get article if content not provided
        if content is None:
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                return {
                    'detected_os': 'Unknown',
                    'method': 'error',
                    'confidence': 'unknown',
                    'error': 'Article not found'
                }
            content = article.content
        else:
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
        
        # Apply junk filter
        content_filter = ContentFilter()
        hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article and article.article_metadata else 0
        
        filter_result = content_filter.filter_content(
            content,
            min_confidence=junk_filter_threshold,
            hunt_score=hunt_score,
            article_id=article_id
        )
        filtered_content = filter_result.filtered_content or content
        
        # Run OS detection with specified model
        os_service = OSDetectionService(model_name=embedding_model)
        
        # Test each model independently:
        # - LLM models: Use LLM-only (skip classifier and similarity)
        # - BERT-only models: Use similarity-only (no LLM fallback)
        if fallback_model:
            # LLM-only mode: skip classifier and similarity, go straight to LLM
            result = await os_service._detect_with_llm_fallback(filtered_content, fallback_model=fallback_model)
            if not result:
                result = {'operating_system': 'Unknown', 'method': 'llm_fallback_failed'}
        else:
            # BERT-only mode: use similarity only (no classifier, no LLM)
            result = os_service._detect_with_similarity(filtered_content)
        
        return {
            'detected_os': result.get('operating_system', 'Unknown'),
            'method': result.get('method', 'unknown'),
            'confidence': result.get('confidence', 'unknown'),
            'similarities': result.get('similarities'),
            'max_similarity': result.get('max_similarity')
        }
    finally:
        if should_close:
            db_session.close()


async def evaluate_model(
    model_key: str,
    model_config: Dict[str, Any],
    url_to_id: Dict[str, int],
    junk_filter_threshold: float = 0.8
) -> Dict[str, Any]:
    """Evaluate a single model configuration."""
    print(f"\n{'='*80}")
    print(f"Evaluating: {model_config['description']}")
    print(f"{'='*80}")
    print(f"Embedding model: {model_config['embedding']}")
    if model_config['fallback']:
        print(f"Fallback model: {model_config['fallback']}")
    print()
    
    # Create a single database session for this model evaluation
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    predictions = []
    ground_truth = []
    results = []
    
    try:
        for test_item in MANUAL_TEST_DATA:
            url = test_item['url']
            if url not in url_to_id:
                continue
            
            article_id = url_to_id[url]
            human_truth = normalize_os_label(test_item['human'])
            ground_truth.append(human_truth)
            
            # Get article content (reuse existing session from run_os_detection_with_model)
            # The run_os_detection_with_model function handles its own DB session
            try:
                # Run detection (this will fetch article internally)
                result = await run_os_detection_with_model(
                    article_id,
                    None,  # Will fetch content internally
                    model_config['embedding'],
                    model_config['fallback'],
                    junk_filter_threshold,
                    db_session=db_session  # Reuse session
                )
                
                detected_os = normalize_os_label(result['detected_os'])
                predictions.append(detected_os)
                
                # Get article title for results (reuse session)
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                title = article.title if article else test_item.get('title', 'Unknown')
                
                results.append({
                    'article_id': article_id,
                    'url': url,
                    'title': title,
                    'ground_truth': human_truth,
                    'predicted': detected_os,
                    'correct': detected_os == human_truth,
                    'method': result['method'],
                    'confidence': result['confidence'],
                    'details': result
                })
                
                status = "✓" if detected_os == human_truth else "✗"
                print(f"  {status} Article {article_id}: {detected_os} (truth: {human_truth}, method: {result['method']})")
            except Exception as e:
                predictions.append('Unknown')
                results.append({
                    'article_id': article_id,
                    'url': url,
                    'error': str(e)
                })
                print(f"  ✗ Article {article_id}: Error - {e}")
    finally:
        db_session.close()
    
    # Calculate metrics
    accuracy = calculate_accuracy(predictions, ground_truth)
    confusion = calculate_confusion_matrix(predictions, ground_truth)
    
    return {
        'model_key': model_key,
        'model_config': model_config,
        'accuracy': accuracy,
        'confusion_matrix': confusion,
        'predictions': predictions,
        'ground_truth': ground_truth,
        'results': results,
        'total_articles': len(predictions)
    }


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description='Evaluate OS Detection with multiple models')
    parser.add_argument(
        '--models',
        type=str,
        nargs='+',
        default=['cti-bert', 'sec-bert', 'deepseek-r1-qwen3-8b'],
        help='Models to test (default: cti-bert, sec-bert, deepseek-r1-qwen3-8b)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='outputs/evaluations/os_detection_multi_model_eval.json',
        help='Output path for evaluation results'
    )
    parser.add_argument(
        '--junk-filter-threshold',
        type=float,
        default=0.8,
        help='Junk filter threshold (default: 0.8)'
    )
    parser.add_argument(
        '--list-models',
        action='store_true',
        help='List available models and exit'
    )
    
    args = parser.parse_args()
    
    if args.list_models:
        print("Available models:")
        print("=" * 80)
        for key, config in RECOMMENDED_MODELS.items():
            print(f"\n{key}:")
            print(f"  Description: {config['description']}")
            print(f"  Embedding: {config['embedding']}")
            if config['fallback']:
                print(f"  Fallback: {config['fallback']}")
        return
    
    print("=" * 80)
    print("OS Detection Multi-Model Evaluation")
    print("=" * 80)
    print()
    
    # Map URLs to article IDs
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    url_to_id = {}
    try:
        for test_item in MANUAL_TEST_DATA:
            article = db_session.query(ArticleTable).filter(
                ArticleTable.canonical_url == test_item['url']
            ).first()
            if article:
                url_to_id[test_item['url']] = article.id
    finally:
        db_session.close()
    
    print(f"Found {len(url_to_id)} articles in database")
    print(f"Testing models: {', '.join(args.models)}")
    print(f"Junk filter threshold: {args.junk_filter_threshold}")
    print()
    
    # Validate models
    invalid_models = [m for m in args.models if m not in RECOMMENDED_MODELS]
    if invalid_models:
        print(f"❌ Invalid models: {', '.join(invalid_models)}")
        print(f"Available models: {', '.join(RECOMMENDED_MODELS.keys())}")
        return
    
    # Evaluate each model
    all_results = {}
    for model_key in args.models:
        model_config = RECOMMENDED_MODELS[model_key]
        try:
            result = await evaluate_model(
                model_key,
                model_config,
                url_to_id,
                args.junk_filter_threshold
            )
            all_results[model_key] = result
        except Exception as e:
            print(f"❌ Error evaluating {model_key}: {e}")
            import traceback
            traceback.print_exc()
            all_results[model_key] = {
                'model_key': model_key,
                'error': str(e)
            }
    
    # Print comparison summary
    print("\n" + "=" * 80)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 80)
    print()
    
    print(f"{'Model':<30} {'Accuracy':<15} {'Description'}")
    print("-" * 80)
    
    sorted_results = sorted(
        [(k, v) for k, v in all_results.items() if 'accuracy' in v],
        key=lambda x: x[1]['accuracy'],
        reverse=True
    )
    
    for model_key, result in sorted_results:
        if 'accuracy' in result:
            model_name = RECOMMENDED_MODELS[model_key]['description']
            accuracy = result['accuracy']
            print(f"{model_name:<30} {accuracy:>6.1%}        {model_name}")
    
    # Detailed per-model results
    print("\n" + "=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)
    
    for model_key, result in sorted_results:
        if 'accuracy' not in result:
            continue
        
        print(f"\n{'-'*80}")
        print(f"{RECOMMENDED_MODELS[model_key]['description']}")
        print(f"{'-'*80}")
        print(f"Accuracy: {result['accuracy']:.1%}")
        print(f"Total articles: {result['total_articles']}")
        
        # Show confusion matrix
        print("\nConfusion Matrix:")
        confusion = result['confusion_matrix']
        all_labels = set()
        for truth_label, preds in confusion.items():
            all_labels.add(truth_label)
            all_labels.update(preds.keys())
        all_labels = sorted(all_labels)
        
        header = "Truth\\Pred"
        print(f"{header:<15}", end="")
        for label in all_labels:
            print(f"{label:<15}", end="")
        print()
        
        for truth_label in all_labels:
            print(f"{truth_label:<15}", end="")
            for pred_label in all_labels:
                count = confusion.get(truth_label, {}).get(pred_label, 0)
                print(f"{count:<15}", end="")
            print()
        
        # Show incorrect predictions
        incorrect = [r for r in result['results'] if not r.get('correct', True)]
        if incorrect:
            print(f"\nIncorrect predictions ({len(incorrect)}):")
            for r in incorrect:
                print(f"  Article {r['article_id']}: Predicted {r['predicted']}, Truth {r['ground_truth']}")
    
    # Save results (merge with existing if file exists)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing results if file exists
    existing_results = {}
    if output_path.exists():
        try:
            with open(output_path, 'r') as f:
                existing_data = json.load(f)
                existing_results = existing_data.get('results', {})
        except Exception as e:
            print(f"Warning: Could not load existing results: {e}")
    
    # Merge new results with existing (new results overwrite existing for same model keys)
    merged_results = {**existing_results, **all_results}
    
    summary = {
        'evaluation_date': str(Path(__file__).stat().st_mtime),
        'total_articles': len(url_to_id),
        'junk_filter_threshold': args.junk_filter_threshold,
        'models_tested': args.models,
        'results': merged_results
    }
    
    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Results saved to: {output_path}")
    
    if sorted_results:
        best_model = sorted_results[0]
        print(f"\n📊 Best model: {RECOMMENDED_MODELS[best_model[0]]['description']} ({best_model[1]['accuracy']:.1%})")


if __name__ == "__main__":
    asyncio.run(main())

