"""
LangFuse client for LLM observability and monitoring.

Provides centralized LangFuse integration for tracing LLM calls,
workflow execution, and agent interactions.
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import AbstractContextManager, contextmanager

logger = logging.getLogger(__name__)

# LangFuse client singleton
_langfuse_client = None
_langfuse_enabled = False

# Store trace IDs for linking spans/generations
_active_trace_id: Optional[str] = None
# Cache of session_id -> trace_id observed during trace creation (in-process)
_session_trace_cache: Dict[str, str] = {}


def _get_langfuse_setting(key: str, env_key: str, default: Optional[str] = None) -> Optional[str]:
    """Get Langfuse setting from database first, then fall back to environment variable.
    
    Priority: database setting > environment variable > default
    """
    # Check database setting first (highest priority - user preference from UI)
    try:
        from src.database.manager import DatabaseManager
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            from src.database.models import AppSettingsTable
            setting = db_session.query(AppSettingsTable).filter(
                AppSettingsTable.key == key
            ).first()
            
            if setting and setting.value:
                logger.debug(f"Using {key} from database setting")
                return setting.value
        except Exception as e:
            logger.debug(f"Could not fetch {key} from database: {e}")
        finally:
            db_session.close()
    except Exception as e:
        logger.debug(f"Could not access database for {key}: {e}")
    
    # Fall back to environment variable (second priority)
    env_value = os.getenv(env_key)
    if env_value:
        logger.debug(f"Using {env_key} from environment")
        return env_value
    
    # Return default if provided
    return default


def get_langfuse_client():
    """Get or initialize LangFuse client."""
    global _langfuse_client, _langfuse_enabled
    
    if _langfuse_client is not None:
        return _langfuse_client
    
    # Check if LangFuse is enabled - check database settings first, then environment variables
    public_key = _get_langfuse_setting("LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY")
    secret_key = _get_langfuse_setting("LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY")
    host = _get_langfuse_setting("LANGFUSE_HOST", "LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not public_key or not secret_key:
        logger.info("LangFuse not configured (missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY). Monitoring disabled.")
        _langfuse_enabled = False
        return None
    
    try:
        from langfuse import Langfuse
        
        _langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            # Flush immediately for better reliability
            flush_at=1,  # Flush after 1 event
            flush_interval=1.0  # Flush every 1 second
        )
        _langfuse_enabled = True
        logger.info(f"LangFuse initialized successfully (host: {host})")
        return _langfuse_client
    except Exception as e:
        logger.error(f"Failed to initialize LangFuse: {e}")
        _langfuse_enabled = False
        return None


def is_langfuse_enabled() -> bool:
    """Check if LangFuse is enabled and configured."""
    global _langfuse_enabled
    if _langfuse_enabled:
        return True
    
    # Try to initialize if not already attempted
    client = get_langfuse_client()
    return client is not None


class _LangfuseWorkflowTrace(AbstractContextManager):
    """Context manager wrapper that shields workflows from LangFuse generator issues."""

    def __init__(
        self,
        execution_id: int,
        article_id: int,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self.execution_id = execution_id
        self.article_id = article_id
        self.user_id = user_id
        self.session_id = session_id

        self._client = None
        self._span_cm = None
        self._span = None
        self._trace_id_hash = None

    def __enter__(self):
        global _active_trace_id

        if not is_langfuse_enabled():
            logger.warning(
                f"LangFuse not enabled for execution {self.execution_id} - skipping trace creation"
            )
            return None

        try:
            self._client = get_langfuse_client()
            if not self._client:
                return None

            # Ensure session_id satisfies Langfuse constraints
            session_id = self.session_id or f"workflow_exec_{self.execution_id}"
            if len(session_id) > 200:
                logger.warning(
                    "Session ID too long (%s chars), truncating to 200", len(session_id)
                )
                session_id = session_id[:200]
            self.session_id = session_id

            # Create a trace-level span with session_id
            # This creates a top-level trace that shows up in the Sessions view in LangFuse
            from langfuse.types import TraceContext
            trace_context = TraceContext(
                session_id=session_id,
                user_id=self.user_id or f"article_{self.article_id}",
            )

            # Get the context manager and enter it
            self._span_cm = self._client.start_as_current_span(
                trace_context=trace_context,
                name=f"agentic_workflow_execution_{self.execution_id}",
                input={
                    "execution_id": self.execution_id,
                    "article_id": self.article_id,
                    "workflow_type": "agentic_workflow",
                },
                metadata={
                    "execution_id": self.execution_id,
                    "article_id": self.article_id,
                    "workflow_type": "agentic_workflow",
                    "user_id": self.user_id or f"article_{self.article_id}",
                },
            )
            self._span = self._span_cm.__enter__()

            # Explicitly set session_id on the trace using update_trace()
            # This is required in LangFuse 3.x to properly associate traces with sessions
            try:
                self._span.update_trace(session_id=session_id)
            except Exception as update_error:
                logger.warning(f"Could not update trace with session_id: {update_error}")

            # Get trace ID (use trace_id, not span id)
            trace_id_value = getattr(self._span, "trace_id", None) or getattr(self._span, "id", None)
            self._trace_id_hash = trace_id_value
            _active_trace_id = self._trace_id_hash
            if self._trace_id_hash and self.session_id:
                _session_trace_cache[self.session_id] = self._trace_id_hash
                logger.info(
                    "Langfuse trace created: execution=%s trace_id=%s session_id=%s",
                    self.execution_id,
                    self._trace_id_hash,
                    self.session_id,
                )
            else:
                logger.warning(
                    "Langfuse trace missing id: execution=%s session_id=%s",
                    self.execution_id,
                    self.session_id,
                )
            return self._span
        except Exception as span_error:
            logger.error(f"Failed to create LangFuse span: {span_error}")
            _active_trace_id = None
            self._span_cm = None
            self._span = None
            self._client = None
            return None

    def __exit__(self, exc_type, exc, tb):
        global _active_trace_id
        suppress = False
        generator_error_occurred = False

        # End the trace if it exists
        if self._span_cm is not None:
            try:
                # Update trace with final status before exiting
                if exc_type is not None and self._span is not None:
                    self._span.update(
                        level="ERROR",
                        status_message=str(exc) if exc else "Unknown error",
                    )
                # Exit the context manager (which will end the trace)
                self._span_cm.__exit__(exc_type, exc, tb)
            except Exception as exit_error:
                # Catch ALL exceptions from Langfuse trace exit, especially generator errors
                message = str(exit_error).lower()
                if "generator" in message or "didn't stop" in message or "throw" in message:
                    logger.warning(
                        f"LangFuse trace raised generator error on exit: {exit_error}. "
                        "This often occurs when Langfuse is busy or network issues occur. "
                        "Suppressing error to prevent workflow failure."
                    )
                    generator_error_occurred = True
                    suppress = True  # Suppress the original exception (if any) to prevent workflow failure
                    # Don't re-raise - we've handled the generator error
                else:
                    # For other errors, log but don't suppress (let them propagate)
                    logger.error(f"Unexpected error exiting LangFuse trace: {exit_error}")
                    suppress = False
                    # Re-raise non-generator errors
                    raise

        if self._client:
            try:
                # Flush to send pending traces immediately
                self._client.flush()
                if self.session_id:
                    logger.info(
                        "LangFuse trace flushed for workflow execution %s (session: %s, trace_id: %s)",
                        self.execution_id,
                        self.session_id,
                        self._trace_id_hash,
                    )
            except Exception as flush_error:
                error_msg = str(flush_error).lower()
                if "generator" in error_msg or "didn't stop" in error_msg:
                    logger.warning(f"LangFuse flush raised generator error (non-critical): {flush_error}")
                    generator_error_occurred = True
                else:
                    logger.error(f"Error flushing LangFuse trace: {flush_error}")

        _active_trace_id = None
        self._span_cm = None
        self._span = None
        self._client = None

        # If generator error occurred, suppress any original exception
        # This prevents generator errors from failing the workflow
        return suppress or generator_error_occurred


def trace_workflow_execution(
    execution_id: int,
    article_id: int,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    Context manager for tracing a workflow execution with session support.
    """
    return _LangfuseWorkflowTrace(
        execution_id=execution_id,
        article_id=article_id,
        user_id=user_id,
        session_id=session_id,
    )


def get_langfuse_trace_id_for_session(session_id: str) -> Optional[str]:
    """
    Look up the most recent Langfuse trace ID for the given session.

    Returns the trace ID if found or ``None`` if Langfuse is not configured or
    the lookup fails.
    """
    if not session_id:
        return None

    if not is_langfuse_enabled():
        logger.debug("LangFuse is disabled; skipping trace lookup for session %s", session_id)
        return None

    # First check in-process cache
    cached = _session_trace_cache.get(session_id)
    if cached:
        return cached

    client = get_langfuse_client()
    if client is None:
        return None

    try:
        traces = client.api.trace.list(
            session_id=session_id,
            limit=1,
            order_by="timestamp.desc"
        )
        if traces and traces.data:
            trace = traces.data[0]
            trace_id = getattr(trace, "id", None)
            if trace_id:
                logger.debug("Found LangFuse trace %s for session %s", trace_id, session_id)
                return trace_id
    except Exception as e:
        logger.debug("Failed to lookup LangFuse trace for session %s: %s", session_id, e)

    return None


@contextmanager
def trace_llm_call(
    name: str,
    model: str,
    execution_id: Optional[int] = None,
    article_id: Optional[int] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Context manager for tracing an LLM call with session support.
    
    Automatically links to the workflow execution session if execution_id is provided.
    Uses propagate_attributes to ensure session_id is inherited by child observations.
    
    Args:
        name: Name of the LLM call (e.g., "rank_article")
        model: Model name
        execution_id: Optional workflow execution ID (used to auto-link to session)
        article_id: Optional article ID
        trace_id: Optional trace ID to link to existing trace
        session_id: Optional session ID (defaults to execution_id-based session if execution_id provided)
        metadata: Optional additional metadata
    
    Usage:
        with trace_llm_call("rank_article", model="deepseek-r1", execution_id=123) as generation:
            result = await llm_service.rank_article(...)
            log_llm_completion(generation, messages, result)
    """
    global _active_trace_id
    
    if not is_langfuse_enabled():
        yield None
        return
    
    generation = None
    try:
        client = get_langfuse_client()
        
        # Determine session_id and trace_id
        resolved_session_id = session_id
        if not resolved_session_id and execution_id:
            # Automatically link to the workflow execution session
            resolved_session_id = f"workflow_exec_{execution_id}"
        
        # Validate session_id length (Langfuse requirement)
        if resolved_session_id and len(resolved_session_id) > 200:
            logger.warning(f"Session ID too long ({len(resolved_session_id)} chars), truncating to 200")
            resolved_session_id = resolved_session_id[:200]
        
        # Use provided trace_id, or get from active trace, or create from execution_id
        resolved_trace_id = trace_id or _active_trace_id
        
        # Create generation using start_generation (LangFuse v3 API)
        from langfuse.types import TraceContext
        
        # Convert messages to LangFuse format for input
        langfuse_input = []
        if metadata and "messages" in metadata:
            # If messages are provided in metadata, use them
            langfuse_input = metadata["messages"]
        else:
            # Otherwise create a simple input dict
            langfuse_input = {
                "execution_id": execution_id,
                "article_id": article_id,
                "model": model
            }
        
        generation_kwargs = {
            "name": name,
            "model": model,
            "input": langfuse_input,
            "metadata": {
                **(metadata or {}),
                "execution_id": execution_id,
                "article_id": article_id
            }
        }
        
        # Use trace_context for trace_id and session_id if we have them
        trace_context_kwargs = {}
        if resolved_trace_id:
            trace_context_kwargs["trace_id"] = resolved_trace_id
        if resolved_session_id:
            trace_context_kwargs["session_id"] = resolved_session_id
        
        if trace_context_kwargs:
            generation_kwargs["trace_context"] = TraceContext(**trace_context_kwargs)
        
        generation = client.start_generation(**generation_kwargs)
        
        # Track if we've already ended the generation to avoid double-ending
        generation_ended = False
        
        try:
            yield generation
        finally:
            # Defensive cleanup - catch ALL exceptions to prevent generator protocol issues
            # This ensures the generator properly handles exceptions via Python's generator protocol
            try:
                # Check if generation has already been ended (by log_llm_completion or log_llm_error)
                already_ended = hasattr(generation, '_langfuse_ended') and generation._langfuse_ended
                
                if generation and not generation_ended and not already_ended:
                    try:
                        generation.end()
                        generation_ended = True
                        generation._langfuse_ended = True
                    except Exception as end_error:
                        # Check for generator errors specifically
                        error_msg = str(end_error).lower()
                        if "generator" in error_msg or "didn't stop" in error_msg or "throw" in error_msg:
                            logger.warning(f"LangFuse generation.end() raised generator error (non-critical): {end_error}")
                        else:
                            # Generation was already ended or ending failed - that's fine
                            logger.debug(f"Generation.end() failed (non-critical): {end_error}")
                    
                    # Explicitly flush to ensure traces are sent
                    try:
                        client.flush()
                        logger.debug(f"LangFuse generation flushed for {name} (session: {resolved_session_id})")
                    except Exception as flush_error:
                        error_msg = str(flush_error).lower()
                        if "generator" in error_msg or "didn't stop" in error_msg:
                            logger.warning(f"LangFuse flush raised generator error (non-critical): {flush_error}")
                        else:
                            logger.error(f"Error flushing LangFuse generation: {flush_error}")
            except Exception as cleanup_error:
                # Catch any exception during cleanup to prevent generator protocol issues
                # CRITICAL: Don't re-raise cleanup errors - they interfere with generator protocol
                error_msg = str(cleanup_error).lower()
                if "generator" in error_msg or "didn't stop" in error_msg:
                    logger.warning(f"LangFuse generation cleanup raised generator error (non-critical): {cleanup_error}")
                else:
                    logger.debug(f"Exception during generation cleanup (non-critical): {cleanup_error}")
        
    except Exception as e:
        logger.error(f"Error creating LangFuse generation: {e}")
        yield None


def log_llm_completion(
    generation,
    input_messages: list,
    output: str,
    usage: Optional[Dict[str, int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ground_truth: Optional[Any] = None
):
    """
    Log LLM completion to LangFuse generation.
    
    Args:
        generation: LangFuse generation object from trace_llm_call
        input_messages: List of input messages
        output: LLM output text
        usage: Token usage dict with 'prompt_tokens', 'completion_tokens', 'total_tokens'
        metadata: Additional metadata
        ground_truth: Optional expected output value for evaluation
    """
    if not generation:
        return
    
    try:
        # Convert messages to LangFuse format
        langfuse_messages = []
        for msg in input_messages:
            if isinstance(msg, dict):
                langfuse_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
            else:
                langfuse_messages.append({"role": "user", "content": str(msg)})
        
        # Update generation with completion data
        # Handle usage parameter - LangFuse expects usage_details or individual fields
        # Set input with messages for proper display in Langfuse UI
        update_kwargs = {
            "input": langfuse_messages,  # Set input directly for Langfuse UI display
            "output": output,
            "model_parameters": {
                "messages": langfuse_messages
            },
            "metadata": metadata
        }

        if ground_truth is not None:
            update_kwargs["expected_output"] = ground_truth
        
        # Add usage if provided
        if usage:
            update_kwargs["usage_details"] = usage
        
        generation.update(**update_kwargs)
        
        # Don't end the generation here - let the context manager in trace_llm_call handle it
        # Ending here and then again in the finally block causes generator protocol issues
        # The context manager will properly end the generation when the with block exits
        
        # Flush after logging completion
        client = get_langfuse_client()
        if client:
            try:
                client.flush()
            except Exception as flush_error:
                error_msg = str(flush_error).lower()
                if "generator" in error_msg or "didn't stop" in error_msg:
                    logger.warning(f"LangFuse flush raised generator error in log_llm_completion (non-critical): {flush_error}")
                else:
                    logger.debug(f"LangFuse flush failed in log_llm_completion (non-critical): {flush_error}")
    except Exception as e:
        error_msg = str(e).lower()
        if "generator" in error_msg or "didn't stop" in error_msg:
            logger.warning(f"LangFuse log_llm_completion raised generator error (non-critical): {e}")
        else:
            logger.error(f"Error logging LLM completion to LangFuse: {e}")


def log_llm_error(generation, error: Exception, metadata: Optional[Dict[str, Any]] = None):
    """Log LLM error to LangFuse generation."""
    if not generation:
        return
    
    try:
        # Update generation with error info, but don't end it here
        # Let the context manager in trace_llm_call handle ending to avoid generator protocol issues
        generation.update(
            level="ERROR",
            status_message=str(error),
            metadata={
                **(metadata or {}),
                "error_type": type(error).__name__
            }
        )
        # Mark as ended using a custom attribute to prevent double-ending
        if not hasattr(generation, '_langfuse_ended'):
            try:
                generation.end()
                generation._langfuse_ended = True
            except Exception as end_error:
                error_msg = str(end_error).lower()
                if "generator" in error_msg or "didn't stop" in error_msg or "throw" in error_msg:
                    logger.warning(f"LangFuse generation.end() raised generator error in log_llm_error (non-critical): {end_error}")
                else:
                    logger.debug(f"Generation.end() failed in log_llm_error (non-critical): {end_error}")
        
        # Flush after logging error
        client = get_langfuse_client()
        if client:
            try:
                client.flush()
            except Exception as flush_error:
                error_msg = str(flush_error).lower()
                if "generator" in error_msg or "didn't stop" in error_msg:
                    logger.warning(f"LangFuse flush raised generator error in log_llm_error (non-critical): {flush_error}")
                else:
                    logger.debug(f"LangFuse flush failed in log_llm_error (non-critical): {flush_error}")
    except Exception as e:
        error_msg = str(e).lower()
        if "generator" in error_msg or "didn't stop" in error_msg:
            logger.warning(f"LangFuse log_llm_error raised generator error (non-critical): {e}")
        else:
            logger.error(f"Error logging LLM error to LangFuse: {e}")


def log_workflow_step(
    trace,
    step_name: str,
    step_result: Optional[Dict[str, Any]] = None,
    error: Optional[Exception] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Log a workflow step to LangFuse trace with session support.
    
    Creates a child span that automatically inherits the session_id from the parent trace.
    
    Args:
        trace: LangFuse span object from trace_workflow_execution
        step_name: Name of the workflow step
        step_result: Result dict from the step
        error: Exception if step failed
        metadata: Additional metadata
    """
    if not trace:
        return
    
    try:
        client = get_langfuse_client()
        if not client:
            return
        
        # Create a child span for this workflow step
        from langfuse.types import TraceContext
        
        span_kwargs = {
            "name": step_name,
            "input": step_result if step_result else {},
            "output": {"error": str(error)} if error else {"success": True},
            "metadata": {
                **(metadata or {}),
                "step_result": step_result,
                "error": str(error) if error else None
            }
        }
        
        # Link to parent trace if trace has a trace_id
        # Also inherit session_id from parent trace context
        trace_id = getattr(trace, 'trace_id', None)
        session_id = getattr(trace, 'session_id', None)
        
        trace_context_kwargs = {}
        if trace_id:
            trace_context_kwargs["trace_id"] = trace_id
        if session_id:
            trace_context_kwargs["session_id"] = session_id
        
        if trace_context_kwargs:
            span_kwargs["trace_context"] = TraceContext(**trace_context_kwargs)
        
        span = client.start_span(**span_kwargs)
        
        if error:
            span.update(level="ERROR", status_message=str(error))
        span.end()
        
        # Flush after logging workflow step
        client.flush()
    except Exception as e:
        logger.error(f"Error logging workflow step to LangFuse: {e}")
