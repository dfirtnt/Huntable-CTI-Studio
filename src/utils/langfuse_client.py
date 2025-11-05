"""
LangFuse client for LLM observability and monitoring.

Provides centralized LangFuse integration for tracing LLM calls,
workflow execution, and agent interactions.
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

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


@contextmanager
def trace_workflow_execution(execution_id: int, article_id: int, user_id: Optional[str] = None, session_id: Optional[str] = None):
    """
    Context manager for tracing a workflow execution with session support.
    
    Uses Langfuse sessions to group all observations (traces, spans, generations) 
    for a workflow execution together. This enables session replay and session-level metrics.
    
    Args:
        execution_id: The workflow execution ID
        article_id: The article being processed
        user_id: Optional user ID (defaults to article_id)
        session_id: Optional session ID (defaults to execution_id). 
                   Sessions group related traces together in LangFuse.
                   Must be ≤200 characters (US-ASCII).
    
    Usage:
        with trace_workflow_execution(execution_id=123, article_id=456) as trace:
            # Workflow code here - all child observations automatically inherit session_id
            trace.update(metadata={"step": "junk_filter"})
    """
    global _active_trace_id
    
    if not is_langfuse_enabled():
        yield None
        return
    
    span_context = None
    try:
        client = get_langfuse_client()
        # Use execution_id as session_id by default to group all traces for this execution
        # Session ID must be ≤200 characters (US-ASCII)
        session_id = session_id or f"workflow_exec_{execution_id}"
        
        # Validate session_id length (Langfuse requirement)
        if len(session_id) > 200:
            logger.warning(f"Session ID too long ({len(session_id)} chars), truncating to 200")
            session_id = session_id[:200]
        
        trace_id = f"workflow_exec_{execution_id}"
        
        # Create root span using start_as_current_span (LangFuse v3 API)
        # This creates a trace automatically with the session_id in trace_context
        # Use trace_context for user_id and session_id
        from langfuse.types import TraceContext
        
        trace_context = TraceContext(
            user_id=user_id or f"article_{article_id}",
            session_id=session_id,
            trace_id=trace_id  # Explicitly set trace_id so all observations are linked
        )
        
        # Use propagate_attributes to ensure all child observations inherit session_id
        # This is the recommended way to propagate session_id according to Langfuse docs
        from langfuse import propagate_attributes
        
        # Use start_as_current_span which creates a trace automatically
        # The trace_context with session_id ensures the trace is part of the session
        # Wrap in propagate_attributes to ensure session_id propagates to all child observations
        with propagate_attributes(session_id=session_id):
            span_context = client.start_as_current_span(
                name=f"agentic_workflow_execution_{execution_id}",
                trace_context=trace_context,
                metadata={
                    "execution_id": execution_id,
                    "article_id": article_id,
                    "workflow_type": "agentic_workflow"
                },
                end_on_exit=False  # Manual control for better exception handling
            )
            span = span_context.__enter__()
            
            # Store trace ID from the span for child spans/generations
            _active_trace_id = getattr(span, 'trace_id', None) or trace_id
            
            try:
                yield span
            finally:
                # Always end the span and flush, even if exceptions occurred
                try:
                    if span_context:
                        span_context.__exit__(None, None, None)
                except Exception as exit_error:
                    logger.error(f"Error exiting LangFuse span: {exit_error}")
                
                # Flush after span ends
                try:
                    client.flush()
                    logger.debug(f"LangFuse trace flushed for workflow execution {execution_id} (session: {session_id})")
                except Exception as flush_error:
                    logger.error(f"Error flushing LangFuse trace: {flush_error}")
                _active_trace_id = None
    except Exception as e:
        logger.error(f"Error creating LangFuse trace: {e}")
        # Ensure span is closed if it was opened
        if span_context:
            try:
                span_context.__exit__(type(e), e, e.__traceback__)
            except Exception:
                pass
        _active_trace_id = None
        yield None


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
                resolved_trace_id = f"workflow_exec_{execution_id}"
            elif _active_trace_id:
                resolved_trace_id = _active_trace_id
        
        # Create generation using start_generation (LangFuse v3 API)
        from langfuse.types import TraceContext
        
        generation_kwargs = {
            "name": name,
            "model": model,
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
        
        # Use propagate_attributes to ensure child observations inherit session_id
        # This is particularly useful if the generation creates nested spans/generations
        from langfuse import propagate_attributes
        
        try:
            if resolved_session_id:
                # Wrap in propagate_attributes to ensure session_id propagates to child observations
                with propagate_attributes(session_id=resolved_session_id):
                    yield generation
            else:
                yield generation
        finally:
            # Explicitly flush to ensure traces are sent
            if generation:
                try:
                    client.flush()
                    logger.debug(f"LangFuse generation flushed for {name} (session: {resolved_session_id})")
                except Exception as flush_error:
                    logger.error(f"Error flushing LangFuse generation: {flush_error}")
        
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
        update_kwargs = {
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
        generation.end()
        
        # Flush after logging completion
        client = get_langfuse_client()
        if client:
            client.flush()
    except Exception as e:
        logger.error(f"Error logging LLM completion to LangFuse: {e}")


def log_llm_error(generation, error: Exception, metadata: Optional[Dict[str, Any]] = None):
    """Log LLM error to LangFuse generation."""
    if not generation:
        return
    
    try:
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
