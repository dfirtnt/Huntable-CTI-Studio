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

            import hashlib

            self._trace_id_hash = hashlib.md5(
                f"workflow_exec_{self.execution_id}".encode()
            ).hexdigest()

            from langfuse.types import TraceContext

            trace_context = TraceContext(
                user_id=self.user_id or f"article_{self.article_id}",
                session_id=session_id,
                trace_id=self._trace_id_hash,
            )

            self._span_cm = self._client.start_as_current_span(
                name=f"agentic_workflow_execution_{self.execution_id}",
                trace_context=trace_context,
                input={
                    "execution_id": self.execution_id,
                    "article_id": self.article_id,
                    "workflow_type": "agentic_workflow",
                },
                metadata={
                    "execution_id": self.execution_id,
                    "article_id": self.article_id,
                    "workflow_type": "agentic_workflow",
                },
                end_on_exit=True,
            )

            self._span = self._span_cm.__enter__()
            _active_trace_id = getattr(self._span, "trace_id", None) or self._trace_id_hash
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

        if self._span_cm is not None:
            try:
                suppress = bool(self._span_cm.__exit__(exc_type, exc, tb))
            except Exception as exit_error:
                # Catch ALL exceptions from Langfuse span exit, especially generator errors
                message = str(exit_error).lower()
                if "generator" in message or "didn't stop" in message or "throw" in message:
                    logger.warning(
                        f"LangFuse span raised generator error on exit: {exit_error}. "
                        "This often occurs when Langfuse is busy or network issues occur. "
                        "Suppressing error to prevent workflow failure."
                    )
                    generator_error_occurred = True
                    suppress = True  # Suppress the original exception (if any) to prevent workflow failure
                    # Don't re-raise - we've handled the generator error
                else:
                    # For other errors, log but don't suppress (let them propagate)
                    logger.error(f"Unexpected error exiting LangFuse span: {exit_error}")
                    suppress = False
                    # Re-raise non-generator errors
                    raise

        if self._client:
            try:
                self._client.flush()
                if self.session_id:
                    logger.debug(
                        "LangFuse trace flushed for workflow execution %s (session: %s)",
                        self.execution_id,
                        self.session_id,
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
        resolved_trace_id = trace_id
        if not resolved_trace_id:
            if execution_id:
                # Generate deterministic hex trace_id from execution_id
                import hashlib
                resolved_trace_id = hashlib.md5(f"workflow_exec_{execution_id}".encode()).hexdigest()
            elif _active_trace_id:
                resolved_trace_id = _active_trace_id
        
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
        
        try:
            yield generation
        finally:
            # Defensive cleanup - catch ALL exceptions to prevent generator protocol issues
            try:
                if generation:
                    try:
                        generation.end()
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
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Log LLM completion to LangFuse generation.
    
    Args:
        generation: LangFuse generation object from trace_llm_call
        input_messages: List of input messages
        output: LLM output text
        usage: Token usage dict with 'prompt_tokens', 'completion_tokens', 'total_tokens'
        metadata: Additional metadata
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
        
        # Add usage if provided
        if usage:
            update_kwargs["usage_details"] = usage
        
        generation.update(**update_kwargs)
        
        # End the generation
        try:
            generation.end()
        except Exception as end_error:
            error_msg = str(end_error).lower()
            if "generator" in error_msg or "didn't stop" in error_msg or "throw" in error_msg:
                logger.warning(f"LangFuse generation.end() raised generator error in log_llm_completion (non-critical): {end_error}")
            else:
                logger.debug(f"Generation.end() failed in log_llm_completion (non-critical): {end_error}")
        
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
        # Mark generation as ended so trace_llm_call finally block doesn't try to end it again
        generation.update(
            level="ERROR",
            status_message=str(error),
            metadata={
                **(metadata or {}),
                "error_type": type(error).__name__
            }
        )
        generation.end()
        
        # Flush after logging error
        client = get_langfuse_client()
        if client:
            client.flush()
    except Exception as e:
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
