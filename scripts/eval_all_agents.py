#!/usr/bin/env python3
"""
Unified evaluation runner for all agents.

Runs evaluations for all agents and generates comparison reports.
"""

import sys
import asyncio
import argparse
import json
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.evaluation.extract_agent_evaluator import ExtractAgentEvaluator
from src.services.evaluation.rank_agent_evaluator import RankAgentEvaluator
from src.services.evaluation.sigma_agent_evaluator import SigmaAgentEvaluator
from src.services.evaluation.os_detection_evaluator import OSDetectionEvaluator
from src.services.llm_service import LLMService
from src.utils.content_filter import ContentFilter
from src.services.os_detection_service import OSDetectionService
from src.database.manager import DatabaseManager


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description='Evaluate all agents')
    parser.add_argument(
        '--config',
        type=str,
        help='Path to evaluation config JSON file'
    )
    parser.add_argument(
        '--extract-data',
        type=str,
        help='Path to Extract Agent test data'
    )
    parser.add_argument(
        '--rank-data',
        type=str,
        help='Path to Rank Agent test data'
    )
    parser.add_argument(
        '--sigma-data',
        type=str,
        help='Path to SIGMA Agent test data'
    )
    parser.add_argument(
        '--os-data',
        type=str,
        help='Path to OS Detection test data'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='outputs/evaluations',
        help='Output directory for evaluation results'
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
    
    # Load config if provided
    config = {}
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
    
    # Get dataset paths from config or args
    extract_data = args.extract_data or config.get('extract_agent', {}).get('test_data')
    rank_data = args.rank_data or config.get('rank_agent', {}).get('test_data')
    sigma_data = args.sigma_data or config.get('sigma_agent', {}).get('test_data')
    os_data = args.os_data or config.get('os_detection', {}).get('test_data')
    
    print("=" * 80)
    print("All Agents Evaluation")
    print("=" * 80)
    print()
    
    # Initialize services
    llm_service = LLMService()
    content_filter = ContentFilter()
    os_detection_service = OSDetectionService()
    db_session = None
    
    if args.save_to_db:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    # Evaluate Extract Agent
    if extract_data:
        print("Evaluating Extract Agent...")
        extract_evaluator = ExtractAgentEvaluator(
            evaluation_type=args.evaluation_type
        )
        extract_metrics = await extract_evaluator.evaluate_dataset(
            Path(extract_data),
            llm_service=llm_service,
            content_filter=content_filter
        )
        extract_evaluator.save_results(
            output_path=output_dir / 'extract_agent_results.json',
            save_to_db=args.save_to_db,
            db_session=db_session
        )
        results['extract_agent'] = extract_metrics
        print("✅ Extract Agent evaluation complete\n")
    
    # Evaluate Rank Agent
    if rank_data:
        print("Evaluating Rank Agent...")
        rank_evaluator = RankAgentEvaluator(
            evaluation_type=args.evaluation_type
        )
        rank_metrics = await rank_evaluator.evaluate_dataset(
            Path(rank_data),
            llm_service=llm_service
        )
        rank_evaluator.save_results(
            output_path=output_dir / 'rank_agent_results.json',
            save_to_db=args.save_to_db,
            db_session=db_session
        )
        results['rank_agent'] = rank_metrics
        print("✅ Rank Agent evaluation complete\n")
    
    # Evaluate SIGMA Agent
    if sigma_data:
        print("Evaluating SIGMA Agent...")
        sigma_evaluator = SigmaAgentEvaluator(
            evaluation_type=args.evaluation_type,
            llm_service=llm_service,
            db_session=db_session
        )
        # Note: SIGMA evaluation requires a generate function
        # This is a placeholder - should be implemented based on actual needs
        print("⚠️  SIGMA Agent evaluation requires generate_rule_func - skipping")
        # sigma_metrics = await sigma_evaluator.evaluate_dataset(Path(sigma_data))
        # results['sigma_agent'] = sigma_metrics
        print()
    
    # Evaluate OS Detection
    if os_data:
        print("Evaluating OS Detection Agent...")
        os_evaluator = OSDetectionEvaluator(
            evaluation_type=args.evaluation_type
        )
        os_metrics = await os_evaluator.evaluate_dataset(
            Path(os_data),
            os_detection_service=os_detection_service
        )
        os_evaluator.save_results(
            output_path=output_dir / 'os_detection_results.json',
            save_to_db=args.save_to_db,
            db_session=db_session
        )
        results['os_detection'] = os_metrics
        print("✅ OS Detection evaluation complete\n")
    
    # Save combined report
    combined_report = {
        'evaluation_type': args.evaluation_type,
        'timestamp': asyncio.get_event_loop().time(),
        'results': results
    }
    
    report_path = output_dir / 'all_agents_report.json'
    with open(report_path, 'w') as f:
        json.dump(combined_report, f, indent=2, ensure_ascii=False)
    
    print("=" * 80)
    print("All Evaluations Complete")
    print("=" * 80)
    print(f"\n💡 Combined report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())

