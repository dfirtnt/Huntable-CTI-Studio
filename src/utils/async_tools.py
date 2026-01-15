"""
Async utilities for safe async/sync interop.

Provides helpers to safely bridge async and sync code without event loop conflicts.
"""

import asyncio
from typing import TypeVar, Coroutine, Any
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_sync(coro: Coroutine[Any, Any, T], *, allow_running_loop: bool = False) -> T:
    """
    Safely run an async coroutine from sync code.
    
    This function raises RuntimeError if called from within a running event loop
    (unless allow_running_loop=True), preventing the "Runner.run() cannot be called
    from a running event loop" error in Python 3.14+.
    
    Args:
        coro: The coroutine to run
        allow_running_loop: If True, allows calling from a running loop (not recommended)
        
    Returns:
        The result of the coroutine
        
    Raises:
        RuntimeError: If called from a running event loop (unless allow_running_loop=True)
    """
    try:
        loop = asyncio.get_running_loop()
        # We're in a running event loop
        if allow_running_loop:
            logger.warning(
                "run_sync() called from running event loop with allow_running_loop=True. "
                "This may cause deadlocks. Consider using 'await' instead."
            )
            # Use a thread executor to run in a separate loop
            from concurrent.futures import ThreadPoolExecutor
            
            def run_in_thread():
                return asyncio.run(coro)
            
            with ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
        else:
            raise RuntimeError(
                "run_sync() called from a running event loop. "
                "Use 'await' in async context instead, or refactor to avoid sync wrapper."
            )
    except RuntimeError as e:
        if "running event loop" in str(e):
            raise  # Re-raise our custom error
        # No running loop, safe to use asyncio.run()
        return asyncio.run(coro)


def ensure_async_context(func):
    """
    Decorator to ensure a function is only called from async context.
    
    Raises RuntimeError if called from sync context.
    """
    def wrapper(*args, **kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                f"{func.__name__}() must be called from async context. "
                "Use 'await' instead of calling directly."
            )
        return func(*args, **kwargs)
    return wrapper
