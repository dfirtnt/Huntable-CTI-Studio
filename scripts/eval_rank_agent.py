#!/usr/bin/env python3
"""
Evaluate Rank Agent performance on test dataset.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.evaluation.rank_agent_evaluator import RankAgentEvaluator
from src.services.llm_service import LLMService


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate Rank Agent performance")
    parser.add_argument("--test-data", type=str, required=True, help="Path to test data JSON file")
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/evaluations/rank_agent_baseline.json",
        help="Output path for evaluation results",
    )
    parser.add_argument("--model", type=str, help="Model name/identifier")
    parser.add_argument(
        "--evaluation-type", type=str, default="baseline", help="Evaluation type (baseline, finetuned, etc.)"
    )
    parser.add_argument("--ranking-threshold", type=float, default=6.0, help="Ranking threshold (default: 6.0)")
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")

    args = parser.parse_args()

    print("=" * 80)
    print("Rank Agent Evaluation")
    print("=" * 80)
    print()

    # Initialize services
    llm_service = LLMService()
    db_session = None

    if args.save_to_db:
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

    model_name = args.model or llm_service.model_rank

    print(f"Model: {model_name}")
    print(f"Test data: {args.test_data}")
    print(f"Evaluation type: {args.evaluation_type}")
    print(f"Ranking threshold: {args.ranking_threshold}")
    print()

    # Initialize evaluator
    evaluator = RankAgentEvaluator(
        model_version=model_name, evaluation_type=args.evaluation_type, ranking_threshold=args.ranking_threshold
    )

    # Run evaluation
    test_data_path = Path(args.test_data)
    if not test_data_path.exists():
        print(f"❌ Test data file not found: {test_data_path}")
        return

    metrics = await evaluator.evaluate_dataset(test_data_path, llm_service=llm_service)

    # Print summary
    print("\n" + "=" * 80)
    print("Evaluation Summary")
    print("=" * 80)
    print(f"Total articles: {metrics.get('total_articles', 0)}")
    print(f"Valid results: {metrics.get('valid_results', 0)}")
    print(f"Errors: {metrics.get('errors', 0)}")
    print()

    if metrics.get("score_mean") is not None:
        print("Score Distribution:")
        print(f"  Mean: {metrics['score_mean']:.2f}")
        print(f"  Std: {metrics.get('score_std', 0):.2f}")
        print(f"  Min: {metrics.get('score_min', 0):.2f}")
        print(f"  Max: {metrics.get('score_max', 0):.2f}")
        print()

    if metrics.get("threshold_accuracy") is not None:
        print("Threshold Accuracy:")
        print(f"  Accuracy: {metrics['threshold_accuracy']:.1%}")
        print()

    if metrics.get("avg_processing_time") is not None:
        print("Processing Time:")
        print(f"  Average: {metrics['avg_processing_time']:.2f}s")
        print()

    # Save results
    output_path = Path(args.output)
    save_result = evaluator.save_results(output_path=output_path, save_to_db=args.save_to_db, db_session=db_session)

    if args.save_to_db and save_result.get("evaluation_id"):
        print(f"\n✅ Evaluation saved to database with ID: {save_result['evaluation_id']}")

    print("\n✅ Evaluation complete!")
    print(f"\n💡 Results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
