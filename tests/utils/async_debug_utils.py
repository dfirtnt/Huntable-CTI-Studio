"""
Advanced debugging utilities for async tests.

This module provides specialized debugging tools for async test scenarios,
including event loop monitoring, task tracking, and async context debugging.
"""

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AsyncDebugInfo:
    """Information about async execution context."""

    event_loop_type: str
    is_running: bool
    is_closed: bool
    current_task: str | None = None
    total_tasks: int = 0
    running_tasks: int = 0
    pending_tasks: int = 0
    cancelled_tasks: int = 0
    task_details: list[dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AsyncOperationTrace:
    """Trace of an async operation."""

    operation_type: str
    start_time: float
    end_time: float | None = None
    duration: float | None = None
    success: bool = True
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class AsyncDebugger:
    """Advanced async debugging utilities."""

    def __init__(self):
        self.operation_traces: list[AsyncOperationTrace] = []
        self.debug_info_history: list[AsyncDebugInfo] = []
        self.monitoring_active = False
        self._monitor_task: asyncio.Task | None = None

    async def start_monitoring(self, interval: float = 0.1):
        """Start monitoring async operations."""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        logger.debug("Async monitoring started")

    async def stop_monitoring(self):
        """Stop monitoring async operations."""
        if not self.monitoring_active:
            return

        self.monitoring_active = False
        if self._monitor_task:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task

        logger.debug("Async monitoring stopped")

    async def _monitor_loop(self, interval: float):
        """Main monitoring loop."""
        while self.monitoring_active:
            try:
                debug_info = self._capture_debug_info()
                self.debug_info_history.append(debug_info)

                # Keep only recent history
                if len(self.debug_info_history) > 100:
                    self.debug_info_history = self.debug_info_history[-50:]

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)

    def _capture_debug_info(self) -> AsyncDebugInfo:
        """Capture current async debug information."""
        try:
            loop = asyncio.get_running_loop()
            current_task = asyncio.current_task()
            all_tasks = asyncio.all_tasks()

            # Categorize tasks
            running_tasks = [t for t in all_tasks if not t.done()]
            pending_tasks = [t for t in all_tasks if t.done() and not t.cancelled()]
            cancelled_tasks = [t for t in all_tasks if t.cancelled()]

            # Get task details
            task_details = []
            for task in all_tasks[:10]:  # Limit to first 10 tasks
                task_details.append(
                    {
                        "name": task.get_name(),
                        "done": task.done(),
                        "cancelled": task.cancelled(),
                        "exception": str(task.exception()) if task.exception() else None,
                    }
                )

            return AsyncDebugInfo(
                event_loop_type=type(loop).__name__,
                is_running=loop.is_running(),
                is_closed=loop.is_closed(),
                current_task=str(current_task) if current_task else None,
                total_tasks=len(all_tasks),
                running_tasks=len(running_tasks),
                pending_tasks=len(pending_tasks),
                cancelled_tasks=len(cancelled_tasks),
                task_details=task_details,
            )
        except Exception as e:
            logger.error(f"Error capturing debug info: {e}")
            return AsyncDebugInfo(
                event_loop_type="unknown",
                is_running=False,
                is_closed=True,
            )

    @asynccontextmanager
    async def trace_operation(self, operation_type: str, **context):
        """Context manager to trace async operations."""
        trace = AsyncOperationTrace(operation_type=operation_type, start_time=time.time(), context=context)

        try:
            self.operation_traces.append(trace)
            yield trace
            trace.success = True
        except Exception as e:
            trace.success = False
            trace.error = str(e)
            raise
        finally:
            trace.end_time = time.time()
            trace.duration = trace.end_time - trace.start_time

    def get_debug_summary(self) -> dict[str, Any]:
        """Get a summary of debug information."""
        if not self.debug_info_history:
            return {"status": "no_data"}

        latest_info = self.debug_info_history[-1]

        return {
            "status": "active" if self.monitoring_active else "inactive",
            "latest_info": {
                "event_loop_type": latest_info.event_loop_type,
                "is_running": latest_info.is_running,
                "is_closed": latest_info.is_closed,
                "current_task": latest_info.current_task,
                "total_tasks": latest_info.total_tasks,
                "running_tasks": latest_info.running_tasks,
                "pending_tasks": latest_info.pending_tasks,
                "cancelled_tasks": latest_info.cancelled_tasks,
            },
            "operation_traces": len(self.operation_traces),
            "debug_history_length": len(self.debug_info_history),
        }

    def clear_history(self):
        """Clear debug history."""
        self.operation_traces.clear()
        self.debug_info_history.clear()
        logger.debug("Debug history cleared")


class AsyncTestHelper:
    """Helper utilities for async test debugging."""

    @staticmethod
    async def wait_for_condition(
        condition: Callable[[], bool], timeout: float = 5.0, interval: float = 0.1, description: str = "condition"
    ) -> bool:
        """Wait for a condition to become true."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if condition():
                return True
            await asyncio.sleep(interval)

        logger.warning(f"Timeout waiting for {description} after {timeout}s")
        return False

    @staticmethod
    async def run_with_timeout(
        coro: Awaitable[Any], timeout: float, timeout_message: str = "Operation timed out"
    ) -> Any:
        """Run a coroutine with timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            logger.error(f"{timeout_message} after {timeout}s")
            raise

    @staticmethod
    async def gather_with_exceptions(*coros: Awaitable[Any], return_exceptions: bool = True) -> list[Any]:
        """Gather coroutines and return results/exceptions."""
        return await asyncio.gather(*coros, return_exceptions=return_exceptions)

    @staticmethod
    def create_debug_task(coro: Awaitable[Any], name: str = None, debug_info: dict[str, Any] = None) -> asyncio.Task:
        """Create a task with debug information."""
        task = asyncio.create_task(coro, name=name)

        if debug_info:
            # Store debug info as task attribute
            task.debug_info = debug_info

        return task

    @staticmethod
    async def debug_task_cancellation(task: asyncio.Task, timeout: float = 1.0):
        """Debug task cancellation with timeout."""
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError:
            logger.warning(f"Task {task.get_name()} timed out, cancelling...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug(f"Task {task.get_name()} cancelled successfully")
        except asyncio.CancelledError:
            logger.debug(f"Task {task.get_name()} was cancelled")
        except Exception as e:
            logger.error(f"Task {task.get_name()} failed with: {e}")


class AsyncMockDebugger:
    """Debug utilities for async mocks."""

    def __init__(self):
        self.mock_calls: list[dict[str, Any]] = []
        self.mock_expectations: list[dict[str, Any]] = []

    def track_mock_call(
        self,
        mock_name: str,
        method_name: str,
        args: tuple,
        kwargs: dict,
        return_value: Any = None,
        exception: Exception = None,
    ):
        """Track a mock method call."""
        call_info = {
            "timestamp": datetime.now(),
            "mock_name": mock_name,
            "method_name": method_name,
            "args": args,
            "kwargs": kwargs,
            "return_value": return_value,
            "exception": str(exception) if exception else None,
        }

        self.mock_calls.append(call_info)
        logger.debug(f"Mock call tracked: {mock_name}.{method_name}")

    def add_mock_expectation(
        self,
        mock_name: str,
        method_name: str,
        expected_args: tuple = None,
        expected_kwargs: dict = None,
        expected_return: Any = None,
        should_raise: Exception = None,
    ):
        """Add an expectation for a mock call."""
        expectation = {
            "mock_name": mock_name,
            "method_name": method_name,
            "expected_args": expected_args,
            "expected_kwargs": expected_kwargs,
            "expected_return": expected_return,
            "should_raise": should_raise,
            "verified": False,
        }

        self.mock_expectations.append(expectation)
        logger.debug(f"Mock expectation added: {mock_name}.{method_name}")

    def verify_expectations(self) -> list[dict[str, Any]]:
        """Verify all mock expectations."""
        unverified = []

        for expectation in self.mock_expectations:
            if not expectation["verified"]:
                unverified.append(expectation)

        return unverified

    def get_mock_summary(self) -> dict[str, Any]:
        """Get a summary of mock activity."""
        return {
            "total_calls": len(self.mock_calls),
            "total_expectations": len(self.mock_expectations),
            "verified_expectations": len([e for e in self.mock_expectations if e["verified"]]),
            "unverified_expectations": len(self.verify_expectations()),
            "recent_calls": self.mock_calls[-10:] if self.mock_calls else [],
        }


class AsyncTestIsolation:
    """Enhanced test isolation for async tests."""

    def __init__(self):
        self.isolated_tasks: list[asyncio.Task] = []
        self.isolated_resources: list[Any] = []
        self.cleanup_functions: list[Callable] = []

    async def isolate_test(self, test_func: Callable, *args, **kwargs):
        """Run a test in isolation."""
        # Start monitoring
        debugger = AsyncDebugger()
        await debugger.start_monitoring()

        try:
            # Run the test
            return await test_func(*args, **kwargs)
        finally:
            # Cleanup
            await self._cleanup_isolation()
            await debugger.stop_monitoring()

    async def _cleanup_isolation(self):
        """Clean up isolated resources."""
        # Cancel isolated tasks
        for task in self.isolated_tasks:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        # Run cleanup functions
        for cleanup_func in self.cleanup_functions:
            try:
                if inspect.iscoroutinefunction(cleanup_func):
                    await cleanup_func()
                else:
                    cleanup_func()
            except Exception as e:
                logger.error(f"Error in cleanup function: {e}")

        # Clear lists
        self.isolated_tasks.clear()
        self.isolated_resources.clear()
        self.cleanup_functions.clear()

    def add_isolated_task(self, task: asyncio.Task):
        """Add a task to be cleaned up."""
        self.isolated_tasks.append(task)

    def add_isolated_resource(self, resource: Any):
        """Add a resource to be cleaned up."""
        self.isolated_resources.append(resource)

    def add_cleanup_function(self, cleanup_func: Callable):
        """Add a cleanup function."""
        self.cleanup_functions.append(cleanup_func)


# Global debugger instance
_global_debugger = AsyncDebugger()
_global_mock_debugger = AsyncMockDebugger()


def get_global_debugger() -> AsyncDebugger:
    """Get the global async debugger instance."""
    return _global_debugger


def get_global_mock_debugger() -> AsyncMockDebugger:
    """Get the global mock debugger instance."""
    return _global_mock_debugger


# Convenience functions
async def debug_async_test(test_func: Callable, *args, **kwargs):
    """Debug an async test with full monitoring."""
    debugger = get_global_debugger()
    await debugger.start_monitoring()

    try:
        return await test_func(*args, **kwargs)
    finally:
        await debugger.stop_monitoring()


async def trace_async_operation(operation_type: str, **context):
    """Trace an async operation."""
    debugger = get_global_debugger()
    return debugger.trace_operation(operation_type, **context)


def track_mock_call(mock_name: str, method_name: str, *args, **kwargs):
    """Track a mock call."""
    mock_debugger = get_global_mock_debugger()
    mock_debugger.track_mock_call(mock_name, method_name, args, kwargs)


# Pytest integration helpers
def pytest_async_debug_hook(item, call):
    """Pytest hook for async debugging."""
    if call.when == "call" and inspect.iscoroutinefunction(item.function):
        # This is an async test
        debugger = get_global_debugger()
        debug_info = debugger.get_debug_summary()

        if debug_info["status"] == "active":
            logger.debug(f"Async test {item.name} debug info: {debug_info}")


# Context managers for easy use
@asynccontextmanager
async def async_debug_context():
    """Context manager for async debugging."""
    debugger = get_global_debugger()
    await debugger.start_monitoring()

    try:
        yield debugger
    finally:
        await debugger.stop_monitoring()


@asynccontextmanager
async def async_test_isolation():
    """Context manager for async test isolation."""
    isolation = AsyncTestIsolation()

    try:
        yield isolation
    finally:
        await isolation._cleanup_isolation()
