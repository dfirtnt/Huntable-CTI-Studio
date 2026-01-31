#!/usr/bin/env python3
"""
Evaluate SIGMA Agent performance using E2E-SIG framework.

Runs comprehensive 7-stage evaluation on test dataset.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.services.evaluation.sigma_agent_evaluator import SigmaAgentEvaluator
from src.services.llm_service import LLMService


async def generate_rule_for_article(article_id: int) -> str:
    """
    Generate SIGMA rule for an article.

    This is a placeholder - should be replaced with actual rule generation logic.
    """
    from src.database.models import ArticleTable
    from src.services.sigma_generation_service import SigmaGenerationService

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
        if not article:
            raise ValueError(f"Article {article_id} not found")

        sigma_service = SigmaGenerationService()
        result = await sigma_service.generate_sigma_rules(
            article_title=article.title,
            article_content=article.content or "",
            source_name=article.source.name if article.source else "",
            url=article.canonical_url or "",
            article_id=article_id,
        )

        # Extract first rule from result
        if result.get("rules") and len(result["rules"]) > 0:
            return result["rules"][0].get("content", "")
        raise ValueError("No rules generated")
    finally:
        db_session.close()


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description="Evaluate SIGMA Agent performance")
    parser.add_argument("--test-data", type=str, required=True, help="Path to test data JSON file")
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/evaluations/sigma_agent_baseline.json",
        help="Output path for evaluation results",
    )
    parser.add_argument("--model", type=str, help="Model name/identifier")
    parser.add_argument(
        "--evaluation-type", type=str, default="baseline", help="Evaluation type (baseline, finetuned, etc.)"
    )
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")

    args = parser.parse_args()

    print("=" * 80)
    print("SIGMA Agent Evaluation (E2E-SIG Framework)")
    print("=" * 80)
    print()

    # Initialize services
    llm_service = LLMService()
    db_session = None

    if args.save_to_db:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

    model_name = args.model or llm_service.model_sigma

    print(f"Model: {model_name}")
    print(f"Test data: {args.test_data}")
    print(f"Evaluation type: {args.evaluation_type}")
    print()

    # Initialize evaluator
    evaluator = SigmaAgentEvaluator(
        model_version=model_name, evaluation_type=args.evaluation_type, llm_service=llm_service, db_session=db_session
    )

    # Run evaluation
    test_data_path = Path(args.test_data)
    if not test_data_path.exists():
        print(f"❌ Test data file not found: {test_data_path}")
        return

    metrics = await evaluator.evaluate_dataset(test_data_path, generate_rule_func=generate_rule_for_article)

    # Print summary
    print("\n" + "=" * 80)
    print("Evaluation Summary")
    print("=" * 80)
    print(f"Total articles: {metrics.get('total_articles', 0)}")
    print(f"Valid results: {metrics.get('valid_results', 0)}")
    print(f"Errors: {metrics.get('errors', 0)}")
    print()

    if metrics.get("structural_validation_pass_rate") is not None:
        print("Structural Validation:")
        print(f"  Pass rate: {metrics['structural_validation_pass_rate']:.1%}")
        print()

    if metrics.get("avg_huntability_score") is not None:
        print("Huntability Score:")
        print(f"  Average: {metrics['avg_huntability_score']:.2f}/10")
        print()

    if metrics.get("avg_semantic_similarity") is not None:
        print("Semantic Similarity:")
        print(f"  Average: {metrics['avg_semantic_similarity']:.2%}")
        print()

    if metrics.get("novelty_distribution"):
        print("Novelty Distribution:")
        dist = metrics["novelty_distribution"]
        print(f"  Duplicates: {dist.get('duplicates', 0)}")
        print(f"  Variants: {dist.get('variants', 0)}")
        print(f"  Novel: {dist.get('novel', 0)}")
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
