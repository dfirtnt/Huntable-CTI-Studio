"""
Langfuse client for evaluation experiments and traces.

Handles creation of experiments, traces, and scoring for preset-based evaluations.
"""

import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from langfuse import Langfuse
from langfuse.types import TraceContext

from src.utils.langfuse_client import get_langfuse_client, is_langfuse_enabled

logger = logging.getLogger(__name__)


class LangfuseEvalClient:
    """Client for Langfuse evaluation operations."""
    
    def __init__(self):
        """Initialize Langfuse client."""
        if not is_langfuse_enabled():
            logger.warning("Langfuse not enabled, evaluation logging will be disabled")
            self.client = None
        else:
            self.client = get_langfuse_client()
    
    def create_experiment(
        self,
        eval_run_id: UUID,
        snapshot_id: UUID,
        snapshot_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Create a Langfuse experiment for an evaluation run.
        
        Since Langfuse doesn't have a direct create_experiment API, we create a parent trace
        that represents the experiment, and all article traces will be linked to it.
        
        Args:
            eval_run_id: UUID of the evaluation run
            snapshot_id: UUID of the preset snapshot
            snapshot_data: Snapshot data dictionary
        
        Returns:
            Dictionary with experiment info (trace_id, name) or None if Langfuse disabled
        """
        if not self.client:
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            experiment_name = f"cmdline_eval__preset_{snapshot_id}__{timestamp}"
            
            # Create a parent trace that represents the experiment
            # All article traces will link to this via session_id
            from langfuse.types import TraceContext
            
            session_id = f"eval_run_{eval_run_id}"
            # Ensure session_id length is within Langfuse limits
            if len(session_id) > 200:
                logger.warning(f"Session ID too long ({len(session_id)} chars), truncating to 200")
                session_id = session_id[:200]
            
            experiment_trace = self.client.start_span(
                trace_context=TraceContext(
                    session_id=session_id
                ),
                name=experiment_name,
                input={
                    "eval_run_id": str(eval_run_id),
                    "snapshot_id": str(snapshot_id),
                },
                metadata={
                    "preset_snapshot_id": str(snapshot_id),
                    "original_preset_id": snapshot_data.get("preset_id"),
                    "extractor_version": snapshot_data.get("extractor_version", "v1"),
                    "evaluation_scope": snapshot_data.get("evaluation_scope", "cmdline_only"),
                    "eval_run_id": str(eval_run_id),
                    "experiment_type": "preset_evaluation"
                }
            )
            
            # Explicitly associate trace with session (required in LangFuse 3.x)
            # This ensures the session shows up in Langfuse UI
            try:
                experiment_trace.update_trace(session_id=session_id)
            except Exception as update_error:
                logger.warning(f"Could not update experiment trace with session_id: {update_error}")
            
            experiment_info = {
                "id": getattr(experiment_trace, "trace_id", None) or getattr(experiment_trace, "id", None),
                "name": experiment_name,
                "trace": experiment_trace
            }
            
            logger.info(f"Created Langfuse experiment trace: {experiment_name}")
            return experiment_info
        except Exception as e:
            logger.error(f"Failed to create Langfuse experiment: {e}")
            return None
    
    def create_trace(
        self,
        experiment: Optional[Dict[str, Any]],
        article_item: Any,
        eval_run_id: UUID,
        snapshot_id: UUID,
        snapshot_data: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Create a Langfuse trace for a single article evaluation.
        
        Creates a child span of the experiment span if available, otherwise creates a sibling span.
        
        Args:
            experiment: Experiment info dict with trace_id and trace object
            article_item: Dataset item with input/expected_output
            eval_run_id: UUID of the evaluation run
            snapshot_id: UUID of the preset snapshot
            snapshot_data: Snapshot data dictionary
        
        Returns:
            Langfuse trace/span object or None if Langfuse disabled
        """
        if not self.client:
            return None
        
        try:
            article_id = article_item.input.get("article_id") if hasattr(article_item, "input") else None
            trace_name = f"cmdline_extraction_{article_id or 'unknown'}"
            
            session_id = f"eval_run_{eval_run_id}"
            # Ensure session_id length is within Langfuse limits
            if len(session_id) > 200:
                logger.warning(f"Session ID too long ({len(session_id)} chars), truncating to 200")
                session_id = session_id[:200]
            
            from langfuse.types import TraceContext
            
            # If we have an experiment span, create a child span using the parent span's context
            if experiment and experiment.get("trace"):
                experiment_span = experiment["trace"]
                # Create child span by using the parent span's start_span method
                # This ensures proper parent-child relationship
                trace = experiment_span.start_span(
                    name=trace_name,
                    input={
                        "article_text": article_item.input.get("article_text", "") if hasattr(article_item, "input") else "",
                        "article_title": article_item.input.get("article_title", "") if hasattr(article_item, "input") else "",
                    },
                    metadata={
                        "preset_snapshot_id": str(snapshot_id),
                        "original_preset_id": snapshot_data.get("preset_id"),
                        "expected_schema": "CmdlineExtract_v1",
                        "extractor_version": snapshot_data.get("extractor_version", "v1"),
                        "evaluation_scope": snapshot_data.get("evaluation_scope", "cmdline_only"),
                        "article_id": article_id
                    }
                )
            else:
                # Fallback: create sibling span if no experiment span available
                trace_context_kwargs = {
                    "session_id": session_id
                }
                if experiment and experiment.get("id"):
                    trace_context_kwargs["trace_id"] = experiment["id"]
                
                trace = self.client.start_span(
                    trace_context=TraceContext(**trace_context_kwargs),
                    name=trace_name,
                    input={
                        "article_text": article_item.input.get("article_text", "") if hasattr(article_item, "input") else "",
                        "article_title": article_item.input.get("article_title", "") if hasattr(article_item, "input") else "",
                    },
                    metadata={
                        "preset_snapshot_id": str(snapshot_id),
                        "original_preset_id": snapshot_data.get("preset_id"),
                        "expected_schema": "CmdlineExtract_v1",
                        "extractor_version": snapshot_data.get("extractor_version", "v1"),
                        "evaluation_scope": snapshot_data.get("evaluation_scope", "cmdline_only"),
                        "article_id": article_id
                    }
                )
                
                # Explicitly associate trace with session (required in LangFuse 3.x)
                try:
                    trace.update_trace(session_id=session_id)
                except Exception as update_error:
                    logger.warning(f"Could not update trace with session_id: {update_error}")
            
            return trace
        except Exception as e:
            logger.error(f"Failed to create Langfuse trace: {e}")
            return None
    
    def log_trace_scores(
        self,
        trace: Any,
        predicted_count: int,
        expected_count: int,
        extraction_result: Optional[Dict[str, Any]] = None,
        execution_error: bool = False
    ) -> None:
        """
        Log scores to a Langfuse trace.
        
        Args:
            trace: Langfuse trace object
            predicted_count: Predicted command-line count
            expected_count: Expected command-line count
            extraction_result: Full extraction result with cmdline_items
            execution_error: Whether extraction failed
        """
        if not trace:
            return
        
        try:
            if execution_error:
                # Log execution error
                trace.score(
                    name="execution_error",
                    value=1
                )
                trace.score(
                    name="exact_match",
                    value=0
                )
                trace.score(
                    name="count_diff",
                    value=expected_count  # Treat as worst-case difference
                )
            else:
                # Log normal scores
                trace.score(
                    name="exact_match",
                    value=1 if predicted_count == expected_count else 0
                )
                trace.score(
                    name="count_diff",
                    value=abs(predicted_count - expected_count)
                )
            
            # Build output with actual extracted command lines
            output = {
                "predicted_count": predicted_count,
                "expected_count": expected_count,
                "execution_error": execution_error
            }
            
            # Always include extraction results (even if empty) for visibility
            if extraction_result:
                cmdline_items = extraction_result.get("cmdline_items", [])
                # Include the count from the result (what the model reported)
                result_count = extraction_result.get("count", len(cmdline_items))
                array_count = len(cmdline_items)
                
                output["extracted_command_lines"] = cmdline_items
                output["extracted_count"] = result_count  # Use the count from the result
                output["array_length"] = array_count  # Also show array length for comparison
                
                # Include the full result's count field if available
                if extraction_result.get("full_result"):
                    full_result = extraction_result["full_result"]
                    full_result_count = full_result.get("count")
                    if full_result_count is not None:
                        output["reported_count"] = full_result_count
                
                # Include error if present
                if extraction_result.get("error"):
                    output["extraction_error"] = extraction_result["error"]
                
                # Include the full result structure for debugging
                # Note: full_result is the actual result dict from run_extraction_agent
                full_result = extraction_result.get("full_result", {})
                
                if full_result:
                    # Get the actual count from the full result
                    full_result_count = full_result.get("count")
                    if full_result_count is not None:
                        output["reported_count"] = full_result_count
                    
                    # Show all keys in the full result to understand its structure
                    output["full_result_keys"] = list(full_result.keys()) if isinstance(full_result, dict) else "not a dict"
                    
                    # Include the actual result structure (this is what run_extraction_agent returns)
                    # It should have: cmdline_items, count, and possibly other fields
                    output["model_response"] = {
                        "count": full_result.get("count"),
                        "cmdline_items_count": len(full_result.get("cmdline_items", [])),
                        "has_cmdline_items": "cmdline_items" in full_result,
                        "has_items": "items" in full_result,
                        "all_keys": list(full_result.keys()) if isinstance(full_result, dict) else None,
                        "error": full_result.get("error")  # Include error if present
                    }
                    
                    # Include key fields if they exist (they might not be in the result)
                    extraction_details = {}
                    if "agent_name" in full_result:
                        extraction_details["agent_name"] = full_result.get("agent_name")
                    if "extraction_method" in full_result:
                        extraction_details["extraction_method"] = full_result.get("extraction_method")
                    if "model_used" in full_result:
                        extraction_details["model_used"] = full_result.get("model_used")
                    if "raw_response" in full_result:
                        raw_response = full_result.get("raw_response")
                        extraction_details["raw_response_preview"] = str(raw_response)[:500] if raw_response else None
                    
                    if extraction_details:
                        output["extraction_details"] = extraction_details
                else:
                    output["full_result_keys"] = "No full_result provided"
                    output["model_response"] = {"error": "full_result is empty or missing"}
            else:
                # No extraction result available
                output["extracted_command_lines"] = []
                output["extracted_count"] = 0
                output["extraction_error"] = "No extraction result returned"
            
            # Update trace output (this should be visible in Langfuse UI)
            logger.debug(f"Updating trace output: {output}")
            trace.update(output=output)
            
            # Flush to ensure scores are sent
            if self.client:
                self.client.flush()
        except Exception as e:
            logger.error(f"Failed to log trace scores: {e}")
    
    def finalize_experiment(
        self,
        experiment: Optional[Dict[str, Any]],
        aggregate_metrics: Dict[str, Any]
    ) -> None:
        """
        Finalize experiment with aggregate scores.
        
        Args:
            experiment: Experiment info dict with trace
            aggregate_metrics: Dictionary with accuracy, mean_count_diff, passed
        """
        if not experiment or not experiment.get("trace"):
            return
        
        try:
            experiment_trace = experiment["trace"]
            
            # Add experiment-level scores to the experiment trace
            if "accuracy" in aggregate_metrics:
                experiment_trace.score(
                    name="accuracy",
                    value=aggregate_metrics["accuracy"]
                )
            
            if "mean_count_diff" in aggregate_metrics:
                experiment_trace.score(
                    name="mean_count_diff",
                    value=aggregate_metrics["mean_count_diff"]
                )
            
            if "passed" in aggregate_metrics:
                experiment_trace.score(
                    name="passed",
                    value=1 if aggregate_metrics["passed"] else 0
                )
            
            # Update trace with final results
            experiment_trace.update(
                output={
                    "accuracy": aggregate_metrics.get("accuracy"),
                    "mean_count_diff": aggregate_metrics.get("mean_count_diff"),
                    "passed": aggregate_metrics.get("passed", False)
                }
            )
            
            # End the experiment trace
            experiment_trace.end()
            
            # Flush to ensure scores are sent
            if self.client:
                self.client.flush()
        except Exception as e:
            logger.error(f"Failed to finalize experiment: {e}")

