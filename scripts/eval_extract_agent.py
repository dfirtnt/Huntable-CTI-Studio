#!/usr/bin/env python3
"""
Evaluate Extract Agent performance on test dataset.

Establishes baseline metrics before fine-tuning and can be re-run
after fine-tuning to measure improvement.
"""

import sys
import asyncio
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.evaluation.extract_agent_evaluator import ExtractAgentEvaluator
from src.services.llm_service import LLMService
from src.utils.content_filter import ContentFilter
from src.database.manager import DatabaseManager


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description='Evaluate Extract Agent performance')
    parser.add_argument(
        '--test-data',
        type=str,
        default='outputs/training_data/test_finetuning_data.json',
        help='Path to test data JSON file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='outputs/evaluations/extract_agent_baseline.json',
        help='Output path for evaluation results'
    )
    parser.add_argument(
        '--model',
        type=str,
        help='Model name/identifier (default: from LLMService config)'
    )
    parser.add_argument(
        '--junk-filter-threshold',
        type=float,
        default=0.8,
        help='Junk filter threshold (default: 0.8)'
    )
    parser.add_argument(
        '--evaluation-type',
        type=str,
        default='baseline',
        help='Evaluation type (baseline, finetuned, etc.)'
    )
    parser.add_argument(
        '--save-to-db',
        action='store_true',
        help='Save results to database'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Extract Agent Evaluation")
    print("=" * 80)
    print()
    
    # Initialize services
    llm_service = LLMService()
    content_filter = ContentFilter()
    db_session = None
    
    if args.save_to_db:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
    
    model_name = args.model or llm_service.model_extract
    
    print(f"Model: {model_name}")
    print(f"Test data: {args.test_data}")
    print(f"Evaluation type: {args.evaluation_type}")
    print()
    
    # Initialize evaluator
    evaluator = ExtractAgentEvaluator(
        model_version=model_name,
        evaluation_type=args.evaluation_type
    )
    
    # Run evaluation
    test_data_path = Path(args.test_data)
    if not test_data_path.exists():
        print(f"❌ Test data file not found: {test_data_path}")
        return
    
    metrics = await evaluator.evaluate_dataset(
        test_data_path,
        llm_service=llm_service,
        content_filter=content_filter,
        junk_filter_threshold=args.junk_filter_threshold
    )
    
    # Print summary
    print("\n" + "=" * 80)
    print("Evaluation Summary")
    print("=" * 80)
    print(f"Total articles: {metrics.get('total_articles', 0)}")
    print(f"Valid results: {metrics.get('valid_results', 0)}")
    print(f"Errors: {metrics.get('errors', 0)}")
    print(f"Error rate: {metrics.get('error_rate', 0):.1%}")
    print()
    print("JSON Validity:")
    print(f"  Rate: {metrics.get('json_validity_rate', 0):.1%}")
    print()
    print("Field Completeness:")
    print(f"  Rate: {metrics.get('field_completeness_rate', 0):.1%}")
    print()
    print("Observable Counts:")
    print(f"  Average: {metrics.get('avg_discrete_count', 0):.1f}")
    print(f"  Total: {metrics.get('total_discrete', 0)}")
    print()
    if metrics.get('count_accuracy') is not None:
        print("Count Accuracy:")
        print(f"  Accuracy: {metrics.get('count_accuracy', 0):.1%}")
        print(f"  Avg diff: {metrics.get('avg_count_diff', 0):.1f}")
        print()
    
    # Save results
    output_path = Path(args.output)
    save_result = evaluator.save_results(
        output_path=output_path,
        save_to_db=args.save_to_db,
        db_session=db_session
    )
    
    if args.save_to_db and save_result.get('evaluation_id'):
        print(f"\n✅ Evaluation saved to database with ID: {save_result['evaluation_id']}")
    
    print("\n✅ Evaluation complete!")
    print(f"\n💡 Results saved to: {output_path}")
    print("\n💡 Next steps:")
    print("   1. Review results")
    print("   2. Proceed with fine-tuning")
    print("   3. Re-run evaluation after fine-tuning to compare")


if __name__ == "__main__":
    asyncio.run(main())
