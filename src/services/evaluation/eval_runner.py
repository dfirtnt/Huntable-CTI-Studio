"""
Evaluation runner for preset-based evaluations.

Executes CmdLine extraction on Gold articles from Langfuse datasets
and logs results to Langfuse experiments/traces.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.database.models import EvalPresetSnapshotTable, EvalRunTable
from src.services.evaluation.langfuse_eval_client import LangfuseEvalClient
from src.services.llm_service import LLMService
from src.utils.langfuse_client import get_langfuse_client

logger = logging.getLogger(__name__)


def _run_async_in_thread(coro):
    """Run async coroutine in a new thread with its own event loop.

    WARNING: This should only be used when absolutely necessary (e.g., Celery tasks).
    Prefer using async/await directly in async contexts.
    """

    def run_in_thread():
        # Create a new event loop in this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        return future.result()


class EvalRunner:
    """Runner for evaluation execution."""

    def __init__(self, db_session: Session):
        """Initialize with database session."""
        self.db = db_session
        self.langfuse_client = LangfuseEvalClient()

    def run_evaluation(self, eval_run_id: UUID, snapshot_id: UUID, dataset_name: str) -> dict[str, Any]:
        """
        Run evaluation against a Langfuse dataset.

        Args:
            eval_run_id: UUID of the evaluation run
            snapshot_id: UUID of the preset snapshot
            dataset_name: Name of the Langfuse dataset

        Returns:
            Dictionary with evaluation results
        """
        # Load eval run
        eval_run = self.db.query(EvalRunTable).filter(EvalRunTable.id == eval_run_id).first()

        if not eval_run:
            raise ValueError(f"Eval run {eval_run_id} not found")

        # Load snapshot
        snapshot = self.db.query(EvalPresetSnapshotTable).filter(EvalPresetSnapshotTable.id == snapshot_id).first()

        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        snapshot_data = snapshot.snapshot_data

        try:
            # Load dataset from Langfuse
            langfuse_client = get_langfuse_client()
            if not langfuse_client:
                raise ValueError("Langfuse not configured")

            dataset = langfuse_client.get_dataset(dataset_name)
            if not dataset:
                raise ValueError(f"Dataset '{dataset_name}' not found")

            # Update eval_run: Set total_items and status
            eval_run.total_items = len(dataset.items) if hasattr(dataset, "items") and dataset.items else 0
            eval_run.status = "running"
            eval_run.started_at = datetime.now()
            self.db.commit()

            logger.info(f"Starting evaluation run {eval_run_id} with {eval_run.total_items} items")

            # Create Langfuse experiment
            experiment = self.langfuse_client.create_experiment(
                eval_run_id=eval_run_id, snapshot_id=snapshot_id, snapshot_data=snapshot_data
            )

            if experiment:
                eval_run.langfuse_experiment_id = experiment.get("id")
                eval_run.langfuse_experiment_name = experiment.get("name")
                self.db.commit()

            # Initialize metrics
            exact_matches = 0
            count_diffs = []
            execution_errors = 0

            # Process each dataset item
            if hasattr(dataset, "items") and dataset.items:
                for item in dataset.items:
                    try:
                        # Create trace
                        trace = self.langfuse_client.create_trace(
                            experiment=experiment,
                            article_item=item,
                            eval_run_id=eval_run_id,
                            snapshot_id=snapshot_id,
                            snapshot_data=snapshot_data,
                        )

                        # Get expected count
                        expected_output = item.expected_output if hasattr(item, "expected_output") else {}
                        if isinstance(expected_output, dict):
                            expected_count = expected_output.get("expected_count", 0)
                        else:
                            expected_count = 0

                        # Get article content for trace update
                        article_text = (
                            item.input.get("article_text", "")
                            if hasattr(item, "input") and isinstance(item.input, dict)
                            else ""
                        )
                        article_title = (
                            item.input.get("article_title", "")
                            if hasattr(item, "input") and isinstance(item.input, dict)
                            else ""
                        )

                        # Run extraction
                        predicted_count = 0
                        extraction_result = None
                        execution_error = False
                        infra_failed = False

                        try:
                            extraction_result = self._run_extraction(item, snapshot_data)
                            predicted_count = extraction_result.get("count", 0)
                            cmdline_items = extraction_result.get("cmdline_items", [])

                            # Log detailed extraction info
                            full_result = extraction_result.get("full_result", {})
                            reported_count = full_result.get("count") if full_result else None

                            logger.info(
                                f"Extraction completed: predicted_count={predicted_count}, "
                                f"expected_count={expected_count}, items={len(cmdline_items)}, "
                                f"reported_count={reported_count}, full_result_keys={list(full_result.keys()) if full_result else 'None'}"
                            )

                            if predicted_count == 0 and len(cmdline_items) == 0:
                                logger.warning(
                                    f"Extraction returned 0 items! Full result structure: {list(full_result.keys()) if full_result else 'No full_result'}"
                                )
                                if full_result:
                                    logger.warning(f"Full result count field: {full_result.get('count')}")
                                    logger.warning(
                                        f"Full result cmdline_items: {type(full_result.get('cmdline_items'))}, length: {len(full_result.get('cmdline_items', []))}"
                                    )

                            # Update trace input to show what was actually sent (if not already set)
                            if trace and article_text:
                                try:
                                    trace.update(
                                        input={
                                            "article_text": article_text[:1000] + "..."
                                            if len(article_text) > 1000
                                            else article_text,
                                            "article_title": article_title,
                                            "article_length": len(article_text),
                                        }
                                    )
                                except Exception as update_error:
                                    logger.warning(f"Could not update trace input: {update_error}")
                        except Exception as e:
                            from src.services.llm_service import PreprocessInvariantError

                            if isinstance(e, PreprocessInvariantError):
                                logger.error(
                                    f"Preprocess invariant failed for item {getattr(item, 'id', 'unknown')}: {e}. "
                                    f"Debug artifacts: {getattr(e, 'debug_artifacts', {})}"
                                )
                                execution_error = False
                                infra_failed = True
                                extraction_result = {
                                    "count": 0,
                                    "cmdline_items": [],
                                    "full_result": None,
                                    "error": str(e),
                                    "infra_failed": True,
                                    "infra_debug_artifacts": getattr(e, "debug_artifacts", {}),
                                }
                            else:
                                logger.error(
                                    f"Extraction failed for item {getattr(item, 'id', 'unknown')}: {e}",
                                    exc_info=True,
                                )
                                execution_error = True
                                infra_failed = False
                                extraction_result = {
                                    "count": 0,
                                    "cmdline_items": [],
                                    "full_result": None,
                                    "error": str(e),
                                }
                            execution_errors += 1

                        # Log scores and update trace output (this sets the output visible in Langfuse)
                        self.langfuse_client.log_trace_scores(
                            trace=trace,
                            predicted_count=predicted_count,
                            expected_count=expected_count,
                            extraction_result=extraction_result,
                            execution_error=execution_error,
                            infra_failed=infra_failed,
                            infra_debug_artifacts=extraction_result.get("infra_debug_artifacts")
                            if extraction_result
                            else None,
                        )

                        # End the trace after output is set
                        if trace:
                            try:
                                # Ensure output is flushed before ending
                                if self.langfuse_client.client:
                                    self.langfuse_client.client.flush()
                                trace.end()
                                logger.debug("Trace ended for article extraction")
                            except Exception as e:
                                logger.warning(f"Failed to end trace: {e}")

                        # Update metrics
                        if not execution_error and not infra_failed:
                            if predicted_count == expected_count:
                                exact_matches += 1
                            count_diffs.append(abs(predicted_count - expected_count))
                        else:
                            # For errors or infra failures, treat as worst-case difference
                            count_diffs.append(expected_count)

                        # Increment completed_items
                        eval_run.completed_items += 1
                        self.db.commit()

                    except Exception as e:
                        logger.error(f"Error processing dataset item: {e}")
                        # Continue with next item (non-fatal)
                        eval_run.completed_items += 1
                        self.db.commit()
                        continue

            # Compute aggregate metrics
            total_items = eval_run.total_items
            accuracy = exact_matches / total_items if total_items > 0 else 0.0
            mean_count_diff = sum(count_diffs) / len(count_diffs) if count_diffs else 0.0
            passed = accuracy == 1.0

            aggregate_metrics = {"accuracy": accuracy, "mean_count_diff": mean_count_diff, "passed": passed}

            # Finalize experiment
            self.langfuse_client.finalize_experiment(experiment, aggregate_metrics)

            # Update eval_run with results
            eval_run.accuracy = accuracy
            eval_run.mean_count_diff = mean_count_diff
            eval_run.passed = passed
            eval_run.status = "completed"
            eval_run.completed_at = datetime.now()
            self.db.commit()

            logger.info(
                f"Evaluation run {eval_run_id} completed: accuracy={accuracy:.3f}, mean_count_diff={mean_count_diff:.2f}"
            )

            return {
                "eval_run_id": str(eval_run_id),
                "status": "completed",
                "accuracy": accuracy,
                "mean_count_diff": mean_count_diff,
                "passed": passed,
                "total_items": total_items,
                "execution_errors": execution_errors,
            }

        except Exception as e:
            logger.error(f"Evaluation run {eval_run_id} failed: {e}", exc_info=True)
            eval_run.status = "failed"
            eval_run.error_message = str(e)
            eval_run.completed_at = datetime.now()
            self.db.commit()
            raise

    def _run_extraction(self, item: Any, snapshot_data: dict[str, Any]) -> dict[str, Any]:
        """
        Run CmdLine extraction on a dataset item.

        Args:
            item: Dataset item with input
            snapshot_data: Snapshot configuration data

        Returns:
            Dictionary with extraction results:
            - count: Predicted command-line count
            - cmdline_items: List of extracted command lines
            - full_result: Complete extraction result from LLM service
        """
        # Get article content from dataset item
        # Langfuse dataset items have .input attribute with the article data
        if hasattr(item, "input"):
            if isinstance(item.input, dict):
                article_text = item.input.get("article_text", "")
                article_title = item.input.get("article_title", "")
                article_url = item.input.get("article_url", "")
            else:
                # Handle case where input might be a string (JSON)
                import json

                try:
                    input_data = json.loads(item.input) if isinstance(item.input, str) else item.input
                    article_text = input_data.get("article_text", "") if isinstance(input_data, dict) else ""
                    article_title = input_data.get("article_title", "") if isinstance(input_data, dict) else ""
                    article_url = input_data.get("article_url", "") if isinstance(input_data, dict) else ""
                except (json.JSONDecodeError, AttributeError):
                    article_text = str(item.input) if item.input else ""
                    article_title = ""
                    article_url = ""
        else:
            article_text = ""
            article_title = ""
            article_url = ""

        logger.info(
            f"Extracting from article: title='{article_title[:50] if article_title else 'N/A'}...', text_length={len(article_text)}"
        )

        if not article_text:
            logger.error(
                f"Article text is empty! Dataset item structure: input={type(item.input)}, has_input={hasattr(item, 'input')}"
            )
            if hasattr(item, "input"):
                logger.error(
                    f"Item input keys: {list(item.input.keys()) if isinstance(item.input, dict) else 'not a dict'}"
                )
            raise ValueError("Article text is required - dataset item has no article_text in input")

        # Get CmdlineExtract prompt config from snapshot
        agent_prompts = snapshot_data.get("agent_prompts", {})
        logger.info(f"Available agent prompts in snapshot: {list(agent_prompts.keys())}")

        cmdline_prompt_config = agent_prompts.get("CmdlineExtract")

        if not cmdline_prompt_config:
            available_agents = list(agent_prompts.keys())
            raise ValueError(
                f"CmdlineExtract prompt not found in snapshot. "
                f"Available agents: {available_agents}. "
                f"Please ensure CmdlineExtract is enabled in your workflow config."
            )

        logger.info(
            f"Using CmdlineExtract prompt: model={cmdline_prompt_config.get('model')}, "
            f"prompt_length={len(cmdline_prompt_config.get('prompt', ''))}, "
            f"instructions_length={len(cmdline_prompt_config.get('instructions', ''))}"
        )

        # Initialize LLM service with snapshot models
        # Normalize model names for LMStudio compatibility (remove prefixes/suffixes)
        # BUT: Don't normalize provider keys or non-model values
        agent_models = snapshot_data.get("agent_models", {})
        normalized_agent_models = {}
        for key, value in agent_models.items():
            # Only normalize model names, not provider keys or other config values
            if key.endswith("_provider") or key.endswith("_temperature") or key.endswith("_top_p"):
                normalized_agent_models[key] = value  # Keep provider/config values as-is
            elif isinstance(value, str):
                normalized_agent_models[key] = self._normalize_lmstudio_model_name(value)
            else:
                normalized_agent_models[key] = value
        llm_service = LLMService(config_models=normalized_agent_models)

        # Get provider for CmdlineExtract (fallback to ExtractAgent provider)
        # Use original agent_models (not normalized) for provider lookup
        cmdline_provider = agent_models.get("CmdlineExtract_provider")
        if not cmdline_provider or (isinstance(cmdline_provider, str) and not cmdline_provider.strip()):
            cmdline_provider = agent_models.get("ExtractAgent_provider")
        logger.info(
            f"Eval runner using provider for CmdlineExtract: {cmdline_provider} (from agent_models keys: {list(agent_models.keys())})"
        )

        # Normalize model name for LMStudio (remove prefixes/suffixes that LMStudio doesn't recognize)
        raw_model = cmdline_prompt_config.get("model", normalized_agent_models.get("ExtractAgent", ""))
        normalized_model = self._normalize_lmstudio_model_name(raw_model)

        # Create prompt config for extraction
        prompt_config = {
            "prompt": cmdline_prompt_config.get("prompt", ""),
            "instructions": cmdline_prompt_config.get("instructions", ""),
            "model": normalized_model,
        }

        # Check if QA is enabled for CmdlineExtract
        qa_enabled = snapshot_data.get("qa_enabled", {}).get("CmdlineExtract", False)
        qa_prompt_config = None
        if qa_enabled:
            # Get CmdLineQA prompt config from snapshot
            cmdline_qa_prompt_config = agent_prompts.get("CmdLineQA")
            if cmdline_qa_prompt_config:
                # Normalize QA model name
                qa_raw_model = cmdline_qa_prompt_config.get(
                    "model", normalized_agent_models.get("CmdLineQA", normalized_model)
                )
                qa_normalized_model = self._normalize_lmstudio_model_name(qa_raw_model)
                qa_prompt_config = {
                    "prompt": cmdline_qa_prompt_config.get("prompt", ""),
                    "instructions": cmdline_qa_prompt_config.get("instructions", ""),
                    "model": qa_normalized_model,
                    "role": cmdline_qa_prompt_config.get("role", "You are a QA agent."),
                    "objective": cmdline_qa_prompt_config.get("objective", "Verify extraction."),
                    "evaluation_criteria": cmdline_qa_prompt_config.get("evaluation_criteria", []),
                }
                logger.info(f"QA enabled for CmdlineExtract: using model={qa_normalized_model}")
            else:
                logger.warning("QA enabled for CmdlineExtract but CmdLineQA prompt not found in snapshot, disabling QA")

        # Run extraction
        coro = llm_service.run_extraction_agent(
            agent_name="CmdlineExtract",
            content=article_text,
            title=article_title,
            url=article_url,
            prompt_config=prompt_config,
            qa_prompt_config=qa_prompt_config,
            max_retries=3,
            execution_id=None,
            model_name=prompt_config.get("model"),
            temperature=0.0,
            provider=cmdline_provider,  # Pass provider from snapshot config
            attention_preprocessor_enabled=True,
        )

        # Run async code - handle event loop gracefully
        # This method is called from sync context (EvalRunner is sync), so we need to handle both cases
        try:
            loop = asyncio.get_running_loop()
            # Event loop is running, use thread executor (shouldn't happen in normal flow)
            logger.warning("EvalRunner._run_extraction called from running event loop - using thread executor")
            extractor_result = _run_async_in_thread(coro)
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            extractor_result = asyncio.run(coro)

        # Log what we received from the extraction
        result_keys = list(extractor_result.keys()) if isinstance(extractor_result, dict) else "not a dict"
        logger.info(f"Raw extraction result keys: {result_keys}")
        logger.info(f"Raw extraction result: {extractor_result}")

        # Check if we got the wrong extraction type (IOCs instead of cmdline_items)
        if isinstance(extractor_result, dict) and "IOCs" in extractor_result:
            logger.error(
                f"ERROR: Extraction returned 'IOCs' key instead of 'cmdline_items'! "
                f"This suggests the model returned the wrong format. "
                f"All keys: {result_keys}"
            )

        # Extract items and count from result
        # The prompt always returns both cmdline_items array and a count field
        cmdline_items = extractor_result.get("cmdline_items") or extractor_result.get("items", [])

        # Ensure cmdline_items is a list (handle case where it might be None or wrong type)
        if not isinstance(cmdline_items, list):
            logger.warning(f"cmdline_items is not a list: {type(cmdline_items)}, converting to list")
            cmdline_items = (
                []
                if cmdline_items is None
                else [cmdline_items]
                if not isinstance(cmdline_items, list)
                else cmdline_items
            )

        # Use the count field from the result (prompt always sends it)
        # But validate it against the array length
        reported_count = extractor_result.get("count")
        array_count = len(cmdline_items)

        if reported_count is not None:
            count = int(reported_count) if isinstance(reported_count, (int, float)) else array_count
            # Validate count matches array length
            if count != array_count:
                logger.warning(
                    f"Count mismatch: result count field={count}, "
                    f"but cmdline_items array has {array_count} items. Using count field value."
                )
        else:
            # Fallback to array count if count field is missing
            logger.warning("Count field missing from result, using array length")
            count = array_count

        logger.info(
            f"Extraction result: count={count} (from field), array_length={array_count}, items={len(cmdline_items)}"
        )

        # Include the original count from the result for visibility
        # Note: extractor_result IS the full_result (run_extraction_agent returns the parsed JSON directly)
        result_dict = {
            "count": count,  # The validated count we're using
            "cmdline_items": cmdline_items,
            "full_result": extractor_result,  # This is the actual result dict from run_extraction_agent
        }

        # Also include the original count field from the result if it exists
        if "count" in extractor_result:
            result_dict["reported_count"] = extractor_result["count"]

        return result_dict

    def _normalize_lmstudio_model_name(self, model_name: str) -> str:
        """
        Normalize LMStudio model name by removing prefixes and date suffixes.

        LMStudio expects model names like "qwen3-4b", but snapshots may contain
        names like "qwen/qwen3-4b-2507" (with prefix and date suffix).

        Examples:
        - "qwen/qwen3-4b-2507" -> "qwen3-4b"
        - "mistralai/mistral-7b-instruct-v0.3" -> "mistral-7b-instruct-v0.3"
        - "qwen3-4b" -> "qwen3-4b" (no change)

        Args:
            model_name: Raw model name from snapshot

        Returns:
            Normalized model name for LMStudio
        """
        if not model_name:
            return model_name

        # Remove common prefixes (e.g., "qwen/", "mistralai/")
        # Split by "/" and take the last part
        if "/" in model_name:
            model_name = model_name.split("/")[-1]

        # Remove date suffixes (e.g., "-2507", "-2024", "-20231219")
        # Pattern: dash followed by 4-8 digits at the end
        import re

        model_name = re.sub(r"-\d{4,8}$", "", model_name)

        return model_name
