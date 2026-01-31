#!/usr/bin/env python3
"""
Evaluate OS Detection Agent performance on test dataset.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.evaluation.os_detection_evaluator import OSDetectionEvaluator
from src.services.os_detection_service import OSDetectionService


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate OS Detection Agent performance")
    parser.add_argument("--test-data", type=str, required=True, help="Path to test data JSON file")
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/evaluations/os_detection_baseline.json",
        help="Output path for evaluation results",
    )
    parser.add_argument("--model", type=str, help="Model name/identifier")
    parser.add_argument(
        "--evaluation-type", type=str, default="baseline", help="Evaluation type (baseline, finetuned, etc.)"
    )
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")

    args = parser.parse_args()

    print("=" * 80)
    print("OS Detection Agent Evaluation")
    print("=" * 80)
    print()

    # Initialize services
    os_detection_service = OSDetectionService()
    db_session = None

    if args.save_to_db:
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

    model_name = args.model or "baseline"

    print(f"Model: {model_name}")
    print(f"Test data: {args.test_data}")
    print(f"Evaluation type: {args.evaluation_type}")
    print()

    # Initialize evaluator
    evaluator = OSDetectionEvaluator(model_version=model_name, evaluation_type=args.evaluation_type)

    # Run evaluation
    test_data_path = Path(args.test_data)
    if not test_data_path.exists():
        print(f"❌ Test data file not found: {test_data_path}")
        return

    metrics = await evaluator.evaluate_dataset(test_data_path, os_detection_service=os_detection_service)

    # Print summary
    print("\n" + "=" * 80)
    print("Evaluation Summary")
    print("=" * 80)
    print(f"Total articles: {metrics.get('total_articles', 0)}")
    print(f"Valid results: {metrics.get('valid_results', 0)}")
    print(f"Errors: {metrics.get('errors', 0)}")
    print()

    if metrics.get("accuracy") is not None:
        print("Accuracy:")
        print(f"  Accuracy: {metrics['accuracy']:.1%}")
        if metrics.get("ground_truth_accuracy") is not None:
            print(f"  Ground truth accuracy: {metrics['ground_truth_accuracy']:.1%}")
        print()

    if metrics.get("avg_confidence") is not None:
        print("Confidence:")
        print(f"  Average: {metrics['avg_confidence']:.2f}")
        print()

    if metrics.get("multi_os_detection_rate") is not None:
        print("Multi-OS Detection:")
        print(f"  Rate: {metrics['multi_os_detection_rate']:.1%}")
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
