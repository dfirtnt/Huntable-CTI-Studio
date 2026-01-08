#!/usr/bin/env python3
"""Minimal evaluation runner for command-line count extraction.

Compares predicted count against ground-truth expected count from Langfuse dataset.
Uses Langfuse evaluation framework (run_experiment).
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

from langfuse import Langfuse, Evaluation
from langfuse.experiment import ExperimentItem, ExperimentItemResult

from src.services.llm_service import LLMService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_langfuse_client() -> Langfuse:
    """Initialize Langfuse client from environment variables."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        raise ValueError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")

    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        flush_at=1,
        flush_interval=1.0,
    )


def load_prompt_config() -> Dict[str, Any]:
    """Load CmdlineExtract prompt configuration."""
    prompt_path = Path("src/prompts/CmdlineExtract")
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_agent_output(extractor_result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert extractor output to evaluation contract format."""
    # Handle both cmdline_items and items keys
    commands = extractor_result.get("cmdline_items") or extractor_result.get("items", [])
    count = extractor_result.get("count", len(commands))

    return {
        "commands": commands,
        "count": count,
    }


def get_predicted_count(agent_output: Dict[str, Any]) -> int:
    """Extract predicted count from agent output following COUNT HANDLING RULES."""
    if "count" in agent_output and isinstance(agent_output["count"], int):
        return agent_output["count"]

    if "commands" in agent_output and isinstance(agent_output["commands"], list):
        return len(agent_output["commands"])

    return 0


def _run_async_in_thread(coro):
    """Run async coroutine in a new thread with its own event loop."""
    def run_in_thread():
        return asyncio.run(coro)
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        return future.result()


def cmdline_extraction_task(*, item: ExperimentItem, model: str, prompt_version: str, llm_service: LLMService, prompt_config: Dict[str, Any], config_models: Dict[str, str] = None, **kwargs) -> Dict[str, Any]:
    """Task function: runs LLM-based command-line extractor on dataset item."""
    article_text = item.input.get("article_text", "")
    article_title = item.input.get("article_title", "")
    article_url = item.input.get("article_url", "")
    
    # Create the async coroutine
    # Get provider from config_models if provided, otherwise infer from model name
    provider = None
    if config_models:
        provider = config_models.get("CmdlineExtract_provider") or config_models.get("ExtractAgent_provider")
    if not provider:
        # Infer provider from model name
        if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4"):
            provider = "openai"
        elif model.startswith("claude-"):
            provider = "anthropic"
        else:
            provider = "lmstudio"
    
    coro = llm_service.run_extraction_agent(
        agent_name="CmdlineExtract",
        content=article_text,
        title=article_title,
        url=article_url,
        prompt_config=prompt_config,
        qa_prompt_config=None,  # No QA for evaluation
        max_retries=3,
        execution_id=None,
        model_name=model,
        temperature=0.0,
        use_hybrid_extractor=False,  # Force LLM usage
        provider=provider  # Pass provider from config or inferred
    )
    
    # Run async code - handle event loop gracefully
    try:
        loop = asyncio.get_running_loop()
        # Event loop is running, use thread executor
        extractor_result = _run_async_in_thread(coro)
    except RuntimeError:
        # No event loop running, can use asyncio.run()
        extractor_result = asyncio.run(coro)
    
    agent_output = normalize_agent_output(extractor_result)
    return agent_output


def count_diff_evaluator(*, input, output, expected_output=None, **kwargs) -> Evaluation:
    """Evaluator: computes absolute difference between predicted and expected count."""
    if not expected_output:
        return Evaluation(
            name="count_diff",
            value=None,
            comment="No ground truth expected_count",
            data_type="NUMERIC"
        )
    
    expected_count = None
    if isinstance(expected_output, dict):
        expected_count = expected_output.get("expected_count")
    elif isinstance(expected_output, (int, float)):
        expected_count = int(expected_output)
    
    if expected_count is None:
        return Evaluation(
            name="count_diff",
            value=None,
            comment="Missing expected_count in expected_output",
            data_type="NUMERIC"
        )
    
    predicted_count = get_predicted_count(output)
    count_diff = abs(predicted_count - expected_count)
    
    return Evaluation(
        name="count_diff",
        value=count_diff,
        data_type="NUMERIC",
        comment=f"Predicted: {predicted_count}, Expected: {expected_count}",
        metadata={"predicted_count": predicted_count, "expected_count": expected_count}
    )


def count_exact_match_evaluator(*, input, output, expected_output=None, **kwargs) -> Evaluation:
    """Evaluator: checks if predicted count exactly matches expected count."""
    if not expected_output:
        return Evaluation(
            name="count_exact_match",
            value=None,
            comment="No ground truth expected_count",
            data_type="NUMERIC"
        )
    
    expected_count = None
    if isinstance(expected_output, dict):
        expected_count = expected_output.get("expected_count")
    elif isinstance(expected_output, (int, float)):
        expected_count = int(expected_output)
    
    if expected_count is None:
        return Evaluation(
            name="count_exact_match",
            value=None,
            comment="Missing expected_count in expected_output",
            data_type="NUMERIC"
        )
    
    predicted_count = get_predicted_count(output)
    count_exact_match = 1 if predicted_count == expected_count else 0
    
    return Evaluation(
        name="count_exact_match",
        value=count_exact_match,
        data_type="NUMERIC",
        comment="Exact match" if count_exact_match == 1 else "Mismatch",
        metadata={"predicted_count": predicted_count, "expected_count": expected_count}
    )


def run_evaluation(model: str, prompt_version: str) -> None:
    """Run evaluation using Langfuse evaluation framework."""
    client = get_langfuse_client()

    dataset = client.get_dataset("cmdline_extractor_gt")
    if not dataset:
        raise ValueError("Dataset 'cmdline_extractor_gt' not found")

    logger.info(f"Loaded dataset: {dataset.name}")

    # Initialize LLM service with minimal config (only ExtractAgent needed, but RankAgent required for init)
    # Use the provided model for both agents (RankAgent won't be used)
    # Infer provider from model name (gpt-* = openai, claude-* = anthropic, else = lmstudio)
    provider = "lmstudio"  # Default
    if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4"):
        provider = "openai"
    elif model.startswith("claude-"):
        provider = "anthropic"
    
    config_models = {
        "ExtractAgent": model,
        "ExtractAgent_provider": provider,
        "RankAgent": model,  # Required for initialization, but won't be used
        "RankAgent_provider": provider,
        "SigmaAgent": model,  # Required for initialization, but won't be used
        "SigmaAgent_provider": provider,
    }
    llm_service = LLMService(config_models=config_models)
    
    # Load prompt configuration
    prompt_config = load_prompt_config()

    # Create task function with model/prompt context (synchronous)
    def task_with_context(*, item: ExperimentItem, **kwargs):
        return cmdline_extraction_task(
            item=item,
            model=model,
            prompt_version=prompt_version,
            llm_service=llm_service,
            prompt_config=prompt_config,
            **kwargs
        )

    # Run experiment using Langfuse evaluation framework
    result = client.run_experiment(
        name=f"Cmdline Count Eval - {model} - {prompt_version}",
        description="Command-line count extraction evaluation (count-only)",
        data=dataset.items,
        task=task_with_context,
        evaluators=[count_diff_evaluator, count_exact_match_evaluator],
        metadata={
            "agent": "CmdLineExtract",
            "eval_type": "count_only",
            "prompt_version": prompt_version,
            "model": model,
        },
    )

    logger.info(f"Experiment completed: {result.dataset_run_id}")
    logger.info(f"Items processed: {len(result.item_results)}")
    
    for item_result in result.item_results:
        trace_id = item_result.trace_id
        output = item_result.output
        predicted_count = get_predicted_count(output)
        
        logger.info(f"Trace {trace_id}: predicted_count={predicted_count}")
        for evaluation in item_result.evaluations:
            logger.info(f"  {evaluation.name}: {evaluation.value} - {evaluation.comment}")

    client.flush()
    logger.info("Evaluation complete")


def main():
    parser = argparse.ArgumentParser(description="Run command-line count evaluation")
    parser.add_argument("--model", required=True, help="Model identifier")
    parser.add_argument("--prompt", required=True, dest="prompt_version", help="Prompt version identifier")
    args = parser.parse_args()

    try:
        run_evaluation(args.model, args.prompt_version)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

