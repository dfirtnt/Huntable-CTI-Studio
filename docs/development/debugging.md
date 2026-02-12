# Debugging

<!-- MERGED FROM: development/DEBUGGING_TOOLS_GUIDE.md, development/DEBUG_EVAL_LMSTUDIO_LOGS.md, development/TROUBLESHOOT_EVAL_PENDING.md -->

# Huntable CTI Studio Debugging Tools Guide

This comprehensive guide covers the enhanced debugging capabilities available in the Huntable CTI Studio test suite. These tools are designed to improve developer productivity by providing detailed failure analysis, performance monitoring, and debugging utilities.

## Table of Contents

1. [Overview](#overview)
2. [LangFuse Workflow Debugging](#langfuse-workflow-debugging)
3. [Test Failure Analysis](#test-failure-analysis)
4. [Async Test Debugging](#async-test-debugging)
5. [Test Isolation and Cleanup](#test-isolation-and-cleanup)
6. [Performance Profiling](#performance-profiling)
7. [Enhanced Output Formatting](#enhanced-output-formatting)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Overview

The Huntable CTI Studio debugging tools provide:

- **LangFuse Workflow Debugging**: Session-based tracing for agentic workflow executions with direct links to LangFuse UI
- **Comprehensive Failure Analysis**: Automatic categorization and analysis of test failures with actionable suggestions
- **Async Debugging**: Specialized tools for debugging async/await code and event loop issues
- **Test Isolation**: Enhanced isolation mechanisms to prevent test interference
- **Performance Profiling**: Detailed performance monitoring and bottleneck identification
- **Rich Output Formatting**: Timestamped, colorized, and structured test output

## LangFuse Workflow Debugging

### Overview

The agentic workflow integrates with LangFuse to provide comprehensive tracing and debugging capabilities. Each workflow execution creates a session in LangFuse that groups all traces, spans, and events for that execution.

### Accessing Debug Links

From the Workflow Executions page, each execution has a **Debug** button that takes you directly to the LangFuse session:

```
https://us.cloud.langfuse.com/project/{project_id}/sessions/workflow_exec_{execution_id}
```

**Example**: For execution #86, the session URL is:
```
https://us.cloud.langfuse.com/project/{project_id}/sessions/workflow_exec_86
```

### Session Structure

Each workflow execution creates:

1. **Session ID**: Format `workflow_exec_{execution_id}` (e.g., `workflow_exec_86`)
2. **Trace ID**: 32-character unique identifier for the execution trace
3. **Spans**: Individual workflow steps (extraction, ranking, SIGMA generation, etc.)

### Implementation Details

The LangFuse integration is implemented in `src/utils/langfuse_client.py`:

```python
# Create trace with session context
from langfuse.types import TraceContext
trace_context = TraceContext(
    session_id=f"workflow_exec_{execution_id}",
    user_id=f"article_{article_id}",
)

# Start trace as current span
span_cm = client.start_as_current_span(
    trace_context=trace_context,
    name=f"agentic_workflow_execution_{execution_id}",
    input={"execution_id": execution_id, "article_id": article_id},
    metadata={...}
)
span = span_cm.__enter__()

# Explicitly associate trace with session (required in LangFuse 3.x)
span.update_trace(session_id=session_id)

# Store trace_id (32 chars) not span id (16 chars)
trace_id = span.trace_id
```

### Key Implementation Points

1. **Session Association**: In LangFuse 3.x with OpenTelemetry, passing `session_id` in `TraceContext` alone is insufficient. An explicit `span.update_trace(session_id=...)` call is required.

2. **Trace ID vs Span ID**:
   - **Trace ID**: 32-character identifier (e.g., `62ed1c144abee5401636ea6c5b9b4f7a`)
   - **Span ID**: 16-character identifier (e.g., `9754b82b9794d922`)
   - Store the **trace ID** for debug links, not the span ID.

3. **Context Manager Handling**: The span context manager must be properly entered with `__enter__()` and exited with `__exit__()` to ensure traces are flushed.

### Viewing Workflow Traces

#### Session View (Recommended)

The session view shows all traces for a workflow execution grouped together:

1. Click **Debug** button on workflow execution
2. View all workflow steps in chronological order
3. See inputs, outputs, and metadata for each step
4. Track token usage and latency per agent

#### Trace View (Individual Steps)

To view an individual trace:

```
https://us.cloud.langfuse.com/project/{project_id}/traces/{trace_id}
```

### Debugging Workflow Issues

When debugging workflow failures:

1. **Check Session View**: Start with the session view to see the full execution timeline
2. **Identify Failed Step**: Look for spans with `ERROR` status
3. **Review Inputs/Outputs**: Check the input and output data for each span
4. **Check Metadata**: Review metadata for execution context (article ID, config version, etc.)
5. **Monitor Token Usage**: Track token consumption across agents

### Configuration

LangFuse configuration is set via environment variables:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PROJECT_ID=your-project-id
```

### Code References

- **Trace creation**: `src/utils/langfuse_client.py` (lines 155-189)
- **Workflow execution**: `src/workflows/agentic_workflow.py` (line 1662)
- **Debug link generation**: `src/web/routes/workflow_executions.py` (lines 805-814)

## Test Failure Analysis

### Automatic Failure Analysis

The `TestFailureAnalyzer` automatically categorizes test failures and provides debugging context:

```python
from tests.utils.test_failure_analyzer import analyze_test_failure, generate_failure_report

# Analyze a test failure
failure_context = analyze_test_failure(
    test_name="test_example",
    exc_info=sys.exc_info(),
    test_duration=2.5,
    environment_info={"database": "test_db"}
)

# Generate comprehensive failure report
failure_report = generate_failure_report(
    test_name="test_example",
    exc_info=sys.exc_info(),
    test_duration=2.5
)
```

### Failure Categories

The analyzer categorizes failures into these types:

- **AssertionError**: Test assertion failures
- **TimeoutError**: Async operation timeouts
- **ConnectionError**: Network/database connection issues
- **ImportError**: Module import problems
- **AttributeError**: Missing object attributes
- **TypeError**: Type mismatch errors
- **ValueError**: Invalid values
- **KeyError**: Missing dictionary keys
- **AsyncError**: Async/await related issues
- **MockError**: Mock configuration problems
- **DatabaseError**: Database operation failures
- **NetworkError**: Network-related issues
- **PermissionError**: File system permission issues
- **FileNotFoundError**: Missing files
- **ConfigurationError**: Configuration problems

### Using Failure Analysis in Tests

```python
import pytest
from tests.utils.test_failure_analyzer import TestFailureReporter

@pytest.fixture
def failure_reporter():
    return TestFailureReporter()

def test_example(failure_reporter):
    try:
        # Your test code here
        assert some_condition
    except Exception as e:
        # Generate failure report
        failure_context = failure_reporter.generate_failure_report(
            test_name="test_example",
            exc_info=sys.exc_info(),
            test_duration=time.time() - start_time
        )
        
        # Access failure analysis
        print(f"Failure type: {failure_context.failure_type}")
        print(f"Suggestions: {failure_context.suggestions}")
        raise
```

## Async Test Debugging

### Async Debugger

The `AsyncDebugger` provides specialized debugging for async operations:

```python
from tests.utils.async_debug_utils import AsyncDebugger, debug_async_test

# Using the debugger directly
debugger = AsyncDebugger()
await debugger.start_monitoring()

try:
    # Your async test code
    result = await some_async_operation()
finally:
    await debugger.stop_monitoring()

# Using the convenience function
result, error = await debug_async_test(some_async_function, arg1, arg2)
```

### Async Context Managers

```python
from tests.utils.async_debug_utils import async_debug_context, async_test_isolation

# Debug context
async with async_debug_context() as debugger:
    # Your async test code
    result = await some_async_operation()
    
    # Get debug info
    debug_info = debugger.get_debug_summary()

# Test isolation
async with async_test_isolation() as isolation:
    # Your async test code
    result = await some_async_operation()
```

### Async Operation Tracing

```python
from tests.utils.async_debug_utils import trace_async_operation

async def test_async_operation():
    async with trace_async_operation("database_query") as trace:
        # Your async operation
        result = await database.query("SELECT * FROM users")
        
        # Trace data is automatically collected
        print(f"Operation duration: {trace.duration}")
```

## Test Isolation and Cleanup

### Test Isolation Manager

The `TestIsolationManager` provides comprehensive test isolation:

```python
from tests.utils.test_isolation import TestIsolationManager, test_isolation

# Using the manager directly
manager = TestIsolationManager()
await manager.start_isolation()

try:
    # Your test code
    pass
finally:
    await manager.stop_isolation()

# Using the context manager
async with test_isolation() as isolation:
    # Your test code
    pass
```

### File System Isolation

```python
from tests.utils.test_isolation import isolated_filesystem

with isolated_filesystem() as temp_dir:
    # Create test files
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    
    # Files are automatically cleaned up
```

### Database Isolation

```python
from tests.utils.test_isolation import isolated_database

async with isolated_database(engine) as db_isolation:
    # Database is automatically cleaned up
    # Test data is isolated
    pass
```

### Mock Isolation

```python
from tests.utils.test_isolation import isolated_mocks

with isolated_mocks() as mock_isolation:
    # Mocks are automatically reset
    pass
```

## Performance Profiling

### Performance Profiler

The `PerformanceProfiler` monitors test performance:

```python
from tests.utils.performance_profiler import PerformanceProfiler, profile_test

# Using the profiler directly
profiler = PerformanceProfiler()
with profiler.profile_test("test_example"):
    # Your test code
    pass

# Using the context manager
with profile_test("test_example"):
    # Your test code
    pass
```

### Performance Monitoring

```python
from tests.utils.performance_profiler import start_performance_monitoring, stop_performance_monitoring

# Start monitoring
start_performance_monitoring()

try:
    # Your test code
    pass
finally:
    # Stop monitoring and generate report
    stop_performance_monitoring()
    save_performance_report()
```

### Performance Decorators

```python
from tests.utils.performance_profiler import profile_performance, profile_async_performance

@profile_performance("test_example")
def test_example():
    # Your test code
    pass

@profile_async_performance("async_test_example")
async def test_async_example():
    # Your async test code
    pass
```

### Performance Analysis

```python
from tests.utils.performance_profiler import get_analyzer

analyzer = get_analyzer()
analysis = analyzer.analyze_performance_data(metrics)

print(f"Overall assessment: {analysis['overall_assessment']}")
print(f"Issues: {analysis['issues']}")
print(f"Recommendations: {analysis['recommendations']}")
```

## Enhanced Output Formatting

### Test Output Formatter

The `TestOutputFormatter` provides rich, timestamped output:

```python
from tests.utils.test_output_formatter import TestOutputFormatter, print_header, print_test_result

formatter = TestOutputFormatter()

# Print formatted header
formatter.print_header("Test Suite", "Running all tests")

# Print test results
formatter.print_test_result("test_example", "PASSED", 1.5)

# Print test failure
formatter.print_test_failure("test_example", "Assertion failed", traceback)
```

### Convenience Functions

```python
from tests.utils.test_output_formatter import (
    print_header, print_test_start, print_test_result,
    print_test_failure, print_progress, print_summary
)

# Print test start
print_test_start("test_example")

# Print test result
print_test_result("test_example", "PASSED", 1.5)

# Print progress
print_progress(5, 10, "Running tests")

# Print summary
print_summary()
```

### Output Configuration

```python
from tests.utils.test_output_formatter import TestOutputConfig, TestOutputFormatter

config = TestOutputConfig(
    show_timestamps=True,
    show_colors=True,
    show_emojis=True,
    timestamp_format="%H:%M:%S",
    output_file="test_results.log"
)

formatter = TestOutputFormatter(config)
```

## Best Practices

### 1. Use Failure Analysis for Debugging

Always use the failure analyzer for test failures:

```python
def test_example(failure_reporter):
    try:
        # Your test code
        pass
    except Exception as e:
        # Generate failure report
        failure_context = failure_reporter.generate_failure_report(
            test_name="test_example",
            exc_info=sys.exc_info()
        )
        
        # Use suggestions for debugging
        for suggestion in failure_context.suggestions:
            logger.info(f"Suggestion: {suggestion}")
        
        raise
```

### 2. Profile Slow Tests

Use performance profiling for tests that take longer than 1 second:

```python
@pytest.mark.performance
def test_slow_operation():
    with profile_test("test_slow_operation"):
        # Your slow test code
        pass
```

### 3. Use Test Isolation

Always use test isolation for tests that modify global state:

```python
async def test_database_operation(isolation_manager):
    await isolation_manager.start_isolation()
    
    try:
        # Your test code
        pass
    finally:
        await isolation_manager.stop_isolation()
```

### 4. Debug Async Tests

Use async debugging for complex async operations:

```python
async def test_async_operation(async_debugger):
    await async_debugger.start_monitoring()
    
    try:
        # Your async test code
        result = await some_async_operation()
        
        # Check debug info
        debug_info = async_debugger.get_debug_summary()
        assert debug_info["status"] == "active"
        
    finally:
        await async_debugger.stop_monitoring()
```

### 5. Use Rich Output Formatting

Use the output formatter for better test visibility:

```python
def test_example(test_output_formatter):
    test_output_formatter.print_test_start("test_example")
    
    try:
        # Your test code
        result = some_operation()
        
        test_output_formatter.print_test_result("test_example", "PASSED", 1.5)
        return result
        
    except Exception as e:
        test_output_formatter.print_test_failure("test_example", str(e))
        raise
```

## Troubleshooting

### Common Issues

#### 1. Import Errors

If you get import errors for the debugging utilities:

```bash
# Ensure the project root is in Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or add to your test file
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

#### 2. Async Debugging Issues

If async debugging doesn't work:

```python
# Ensure you're in an async context
async def test_example():
    debugger = AsyncDebugger()
    await debugger.start_monitoring()
    
    try:
        # Your async code
        pass
    finally:
        await debugger.stop_monitoring()
```

#### 3. Performance Profiling Issues

If performance profiling fails:

```python
# Check if profiling is enabled
from tests.utils.performance_profiler import get_profiler

profiler = get_profiler()
if profiler.config.enable_cpu_profiling:
    # Profiling is enabled
    pass
```

#### 4. Test Isolation Issues

If test isolation doesn't work:

```python
# Check isolation configuration
from tests.utils.test_isolation import TestIsolationManager

manager = TestIsolationManager()
if manager.config.database_cleanup:
    # Database cleanup is enabled
    pass
```

### Debug Mode

Enable debug mode for more verbose output:

```bash
# Set debug environment variable
export TEST_LOG_LEVEL=DEBUG

# Or use in test
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

### Performance Issues

If tests are running slowly:

1. **Check performance profiling**: Use the profiler to identify bottlenecks
2. **Review test isolation**: Ensure cleanup isn't taking too long
3. **Check async operations**: Use async debugging to identify event loop issues
4. **Review mock usage**: Ensure mocks aren't causing performance issues

### Memory Issues

If tests are using too much memory:

1. **Use memory profiling**: Enable memory profiling in the performance profiler
2. **Check test isolation**: Ensure proper cleanup of resources
3. **Review test data**: Use smaller test datasets
4. **Check for memory leaks**: Use the memory monitoring features

## Integration with Test Runner

The debugging tools are automatically integrated with the test runner:

```bash
# Run tests with enhanced debugging
python3 run_tests.py all --debug --verbose

# Run performance tests with profiling
python3 run_tests.py performance --coverage

# Run tests with failure analysis
python3 run_tests.py unit --debug
```

The test runner automatically:
- Enables failure analysis for failed tests
- Starts performance monitoring for performance tests
- Uses enhanced output formatting
- Provides debugging context in error messages

## Conclusion

The Huntable CTI Studio debugging tools provide comprehensive support for test debugging and optimization. By using these tools effectively, you can:

- Quickly identify and resolve test failures
- Debug complex async operations
- Monitor and optimize test performance
- Ensure proper test isolation
- Get rich, informative test output

For more information, refer to the individual module documentation and examples in the `tests/utils/` directory.
# Huntable CTI Studio Debugging Tools Guide

This comprehensive guide covers the enhanced debugging capabilities available in the Huntable CTI Studio test suite. These tools are designed to improve developer productivity by providing detailed failure analysis, performance monitoring, and debugging utilities.

## Table of Contents

1. [Overview](#overview)
2. [LangFuse Workflow Debugging](#langfuse-workflow-debugging)
3. [Test Failure Analysis](#test-failure-analysis)
4. [Async Test Debugging](#async-test-debugging)
5. [Test Isolation and Cleanup](#test-isolation-and-cleanup)
6. [Performance Profiling](#performance-profiling)
7. [Enhanced Output Formatting](#enhanced-output-formatting)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Overview

The Huntable CTI Studio debugging tools provide:

- **LangFuse Workflow Debugging**: Session-based tracing for agentic workflow executions with direct links to LangFuse UI
- **Comprehensive Failure Analysis**: Automatic categorization and analysis of test failures with actionable suggestions
- **Async Debugging**: Specialized tools for debugging async/await code and event loop issues
- **Test Isolation**: Enhanced isolation mechanisms to prevent test interference
- **Performance Profiling**: Detailed performance monitoring and bottleneck identification
- **Rich Output Formatting**: Timestamped, colorized, and structured test output

## LangFuse Workflow Debugging

### Overview

The agentic workflow integrates with LangFuse to provide comprehensive tracing and debugging capabilities. Each workflow execution creates a session in LangFuse that groups all traces, spans, and events for that execution.

### Accessing Debug Links

From the Workflow Executions page, each execution has a **Debug** button that takes you directly to the LangFuse session:

```
https://us.cloud.langfuse.com/project/{project_id}/sessions/workflow_exec_{execution_id}
```

**Example**: For execution #86, the session URL is:
```
https://us.cloud.langfuse.com/project/{project_id}/sessions/workflow_exec_86
```

### Session Structure

Each workflow execution creates:

1. **Session ID**: Format `workflow_exec_{execution_id}` (e.g., `workflow_exec_86`)
2. **Trace ID**: 32-character unique identifier for the execution trace
3. **Spans**: Individual workflow steps (extraction, ranking, SIGMA generation, etc.)

### Implementation Details

The LangFuse integration is implemented in `src/utils/langfuse_client.py`:

```python
# Create trace with session context
from langfuse.types import TraceContext
trace_context = TraceContext(
    session_id=f"workflow_exec_{execution_id}",
    user_id=f"article_{article_id}",
)

# Start trace as current span
span_cm = client.start_as_current_span(
    trace_context=trace_context,
    name=f"agentic_workflow_execution_{execution_id}",
    input={"execution_id": execution_id, "article_id": article_id},
    metadata={...}
)
span = span_cm.__enter__()

# Explicitly associate trace with session (required in LangFuse 3.x)
span.update_trace(session_id=session_id)

# Store trace_id (32 chars) not span id (16 chars)
trace_id = span.trace_id
```

### Key Implementation Points

1. **Session Association**: In LangFuse 3.x with OpenTelemetry, passing `session_id` in `TraceContext` alone is insufficient. An explicit `span.update_trace(session_id=...)` call is required.

2. **Trace ID vs Span ID**:
   - **Trace ID**: 32-character identifier (e.g., `62ed1c144abee5401636ea6c5b9b4f7a`)
   - **Span ID**: 16-character identifier (e.g., `9754b82b9794d922`)
   - Store the **trace ID** for debug links, not the span ID.

3. **Context Manager Handling**: The span context manager must be properly entered with `__enter__()` and exited with `__exit__()` to ensure traces are flushed.

### Viewing Workflow Traces

#### Session View (Recommended)

The session view shows all traces for a workflow execution grouped together:

1. Click **Debug** button on workflow execution
2. View all workflow steps in chronological order
3. See inputs, outputs, and metadata for each step
4. Track token usage and latency per agent

#### Trace View (Individual Steps)

To view an individual trace:

```
https://us.cloud.langfuse.com/project/{project_id}/traces/{trace_id}
```

### Debugging Workflow Issues

When debugging workflow failures:

1. **Check Session View**: Start with the session view to see the full execution timeline
2. **Identify Failed Step**: Look for spans with `ERROR` status
3. **Review Inputs/Outputs**: Check the input and output data for each span
4. **Check Metadata**: Review metadata for execution context (article ID, config version, etc.)
5. **Monitor Token Usage**: Track token consumption across agents

### Configuration

LangFuse configuration is set via environment variables:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PROJECT_ID=your-project-id
```

### Code References

- **Trace creation**: `src/utils/langfuse_client.py` (lines 155-189)
- **Workflow execution**: `src/workflows/agentic_workflow.py` (line 1662)
- **Debug link generation**: `src/web/routes/workflow_executions.py` (lines 805-814)

## Test Failure Analysis

### Automatic Failure Analysis

The `TestFailureAnalyzer` automatically categorizes test failures and provides debugging context:

```python
from tests.utils.test_failure_analyzer import analyze_test_failure, generate_failure_report

# Analyze a test failure
failure_context = analyze_test_failure(
    test_name="test_example",
    exc_info=sys.exc_info(),
    test_duration=2.5,
    environment_info={"database": "test_db"}
)

# Generate comprehensive failure report
failure_report = generate_failure_report(
    test_name="test_example",
    exc_info=sys.exc_info(),
    test_duration=2.5
)
```

### Failure Categories

The analyzer categorizes failures into these types:

- **AssertionError**: Test assertion failures
- **TimeoutError**: Async operation timeouts
- **ConnectionError**: Network/database connection issues
- **ImportError**: Module import problems
- **AttributeError**: Missing object attributes
- **TypeError**: Type mismatch errors
- **ValueError**: Invalid values
- **KeyError**: Missing dictionary keys
- **AsyncError**: Async/await related issues
- **MockError**: Mock configuration problems
- **DatabaseError**: Database operation failures
- **NetworkError**: Network-related issues
- **PermissionError**: File system permission issues
- **FileNotFoundError**: Missing files
- **ConfigurationError**: Configuration problems

### Using Failure Analysis in Tests

```python
import pytest
from tests.utils.test_failure_analyzer import TestFailureReporter

@pytest.fixture
def failure_reporter():
    return TestFailureReporter()

def test_example(failure_reporter):
    try:
        # Your test code here
        assert some_condition
    except Exception as e:
        # Generate failure report
        failure_context = failure_reporter.generate_failure_report(
            test_name="test_example",
            exc_info=sys.exc_info(),
            test_duration=time.time() - start_time
        )
        
        # Access failure analysis
        print(f"Failure type: {failure_context.failure_type}")
        print(f"Suggestions: {failure_context.suggestions}")
        raise
```

## Async Test Debugging

### Async Debugger

The `AsyncDebugger` provides specialized debugging for async operations:

```python
from tests.utils.async_debug_utils import AsyncDebugger, debug_async_test

# Using the debugger directly
debugger = AsyncDebugger()
await debugger.start_monitoring()

try:
    # Your async test code
    result = await some_async_operation()
finally:
    await debugger.stop_monitoring()

# Using the convenience function
result, error = await debug_async_test(some_async_function, arg1, arg2)
```

### Async Context Managers

```python
from tests.utils.async_debug_utils import async_debug_context, async_test_isolation

# Debug context
async with async_debug_context() as debugger:
    # Your async test code
    result = await some_async_operation()
    
    # Get debug info
    debug_info = debugger.get_debug_summary()

# Test isolation
async with async_test_isolation() as isolation:
    # Your async test code
    result = await some_async_operation()
```

### Async Operation Tracing

```python
from tests.utils.async_debug_utils import trace_async_operation

async def test_async_operation():
    async with trace_async_operation("database_query") as trace:
        # Your async operation
        result = await database.query("SELECT * FROM users")
        
        # Trace data is automatically collected
        print(f"Operation duration: {trace.duration}")
```

## Test Isolation and Cleanup

### Test Isolation Manager

The `TestIsolationManager` provides comprehensive test isolation:

```python
from tests.utils.test_isolation import TestIsolationManager, test_isolation

# Using the manager directly
manager = TestIsolationManager()
await manager.start_isolation()

try:
    # Your test code
    pass
finally:
    await manager.stop_isolation()

# Using the context manager
async with test_isolation() as isolation:
    # Your test code
    pass
```

### File System Isolation

```python
from tests.utils.test_isolation import isolated_filesystem

with isolated_filesystem() as temp_dir:
    # Create test files
    test_file = temp_dir / "test.txt"
    test_file.write_text("test content")
    
    # Files are automatically cleaned up
```

### Database Isolation

```python
from tests.utils.test_isolation import isolated_database

async with isolated_database(engine) as db_isolation:
    # Database is automatically cleaned up
    # Test data is isolated
    pass
```

### Mock Isolation

```python
from tests.utils.test_isolation import isolated_mocks

with isolated_mocks() as mock_isolation:
    # Mocks are automatically reset
    pass
```

## Performance Profiling

### Performance Profiler

The `PerformanceProfiler` monitors test performance:

```python
from tests.utils.performance_profiler import PerformanceProfiler, profile_test

# Using the profiler directly
profiler = PerformanceProfiler()
with profiler.profile_test("test_example"):
    # Your test code
    pass

# Using the context manager
with profile_test("test_example"):
    # Your test code
    pass
```

### Performance Monitoring

```python
from tests.utils.performance_profiler import start_performance_monitoring, stop_performance_monitoring

# Start monitoring
start_performance_monitoring()

try:
    # Your test code
    pass
finally:
    # Stop monitoring and generate report
    stop_performance_monitoring()
    save_performance_report()
```

### Performance Decorators

```python
from tests.utils.performance_profiler import profile_performance, profile_async_performance

@profile_performance("test_example")
def test_example():
    # Your test code
    pass

@profile_async_performance("async_test_example")
async def test_async_example():
    # Your async test code
    pass
```

### Performance Analysis

```python
from tests.utils.performance_profiler import get_analyzer

analyzer = get_analyzer()
analysis = analyzer.analyze_performance_data(metrics)

print(f"Overall assessment: {analysis['overall_assessment']}")
print(f"Issues: {analysis['issues']}")
print(f"Recommendations: {analysis['recommendations']}")
```

## Enhanced Output Formatting

### Test Output Formatter

The `TestOutputFormatter` provides rich, timestamped output:

```python
from tests.utils.test_output_formatter import TestOutputFormatter, print_header, print_test_result

formatter = TestOutputFormatter()

# Print formatted header
formatter.print_header("Test Suite", "Running all tests")

# Print test results
formatter.print_test_result("test_example", "PASSED", 1.5)

# Print test failure
formatter.print_test_failure("test_example", "Assertion failed", traceback)
```

### Convenience Functions

```python
from tests.utils.test_output_formatter import (
    print_header, print_test_start, print_test_result,
    print_test_failure, print_progress, print_summary
)

# Print test start
print_test_start("test_example")

# Print test result
print_test_result("test_example", "PASSED", 1.5)

# Print progress
print_progress(5, 10, "Running tests")

# Print summary
print_summary()
```

### Output Configuration

```python
from tests.utils.test_output_formatter import TestOutputConfig, TestOutputFormatter

config = TestOutputConfig(
    show_timestamps=True,
    show_colors=True,
    show_emojis=True,
    timestamp_format="%H:%M:%S",
    output_file="test_results.log"
)

formatter = TestOutputFormatter(config)
```

## Best Practices

### 1. Use Failure Analysis for Debugging

Always use the failure analyzer for test failures:

```python
def test_example(failure_reporter):
    try:
        # Your test code
        pass
    except Exception as e:
        # Generate failure report
        failure_context = failure_reporter.generate_failure_report(
            test_name="test_example",
            exc_info=sys.exc_info()
        )
        
        # Use suggestions for debugging
        for suggestion in failure_context.suggestions:
            logger.info(f"Suggestion: {suggestion}")
        
        raise
```

### 2. Profile Slow Tests

Use performance profiling for tests that take longer than 1 second:

```python
@pytest.mark.performance
def test_slow_operation():
    with profile_test("test_slow_operation"):
        # Your slow test code
        pass
```

### 3. Use Test Isolation

Always use test isolation for tests that modify global state:

```python
async def test_database_operation(isolation_manager):
    await isolation_manager.start_isolation()
    
    try:
        # Your test code
        pass
    finally:
        await isolation_manager.stop_isolation()
```

### 4. Debug Async Tests

Use async debugging for complex async operations:

```python
async def test_async_operation(async_debugger):
    await async_debugger.start_monitoring()
    
    try:
        # Your async test code
        result = await some_async_operation()
        
        # Check debug info
        debug_info = async_debugger.get_debug_summary()
        assert debug_info["status"] == "active"
        
    finally:
        await async_debugger.stop_monitoring()
```

### 5. Use Rich Output Formatting

Use the output formatter for better test visibility:

```python
def test_example(test_output_formatter):
    test_output_formatter.print_test_start("test_example")
    
    try:
        # Your test code
        result = some_operation()
        
        test_output_formatter.print_test_result("test_example", "PASSED", 1.5)
        return result
        
    except Exception as e:
        test_output_formatter.print_test_failure("test_example", str(e))
        raise
```

## Troubleshooting

### Common Issues

#### 1. Import Errors

If you get import errors for the debugging utilities:

```bash
# Ensure the project root is in Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Or add to your test file
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

#### 2. Async Debugging Issues

If async debugging doesn't work:

```python
# Ensure you're in an async context
async def test_example():
    debugger = AsyncDebugger()
    await debugger.start_monitoring()
    
    try:
        # Your async code
        pass
    finally:
        await debugger.stop_monitoring()
```

#### 3. Performance Profiling Issues

If performance profiling fails:

```python
# Check if profiling is enabled
from tests.utils.performance_profiler import get_profiler

profiler = get_profiler()
if profiler.config.enable_cpu_profiling:
    # Profiling is enabled
    pass
```

#### 4. Test Isolation Issues

If test isolation doesn't work:

```python
# Check isolation configuration
from tests.utils.test_isolation import TestIsolationManager

manager = TestIsolationManager()
if manager.config.database_cleanup:
    # Database cleanup is enabled
    pass
```

### Debug Mode

Enable debug mode for more verbose output:

```bash
# Set debug environment variable
export TEST_LOG_LEVEL=DEBUG

# Or use in test
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

### Performance Issues

If tests are running slowly:

1. **Check performance profiling**: Use the profiler to identify bottlenecks
2. **Review test isolation**: Ensure cleanup isn't taking too long
3. **Check async operations**: Use async debugging to identify event loop issues
4. **Review mock usage**: Ensure mocks aren't causing performance issues

### Memory Issues

If tests are using too much memory:

1. **Use memory profiling**: Enable memory profiling in the performance profiler
2. **Check test isolation**: Ensure proper cleanup of resources
3. **Review test data**: Use smaller test datasets
4. **Check for memory leaks**: Use the memory monitoring features

## Integration with Test Runner

The debugging tools are automatically integrated with the test runner:

```bash
# Run tests with enhanced debugging
python3 run_tests.py all --debug --verbose

# Run performance tests with profiling
python3 run_tests.py performance --coverage

# Run tests with failure analysis
python3 run_tests.py unit --debug
```

The test runner automatically:
- Enables failure analysis for failed tests
- Starts performance monitoring for performance tests
- Uses enhanced output formatting
- Provides debugging context in error messages

## Conclusion

The Huntable CTI Studio debugging tools provide comprehensive support for test debugging and optimization. By using these tools effectively, you can:

- Quickly identify and resolve test failures
- Debug complex async operations
- Monitor and optimize test performance
- Ensure proper test isolation
- Get rich, informative test output

For more information, refer to the individual module documentation and examples in the `tests/utils/` directory.

---

# Debugging Missing LMStudio Logs in Evaluations

## Issue
When running evaluations via `/mlops/agent-evals`, no LMStudio logs are being generated.

## Root Causes

### 1. Execution Not Running
The workflow execution may be stuck in `pending` status and not actually executing.

**Check:**
```sql
SELECT id, article_id, status, current_step, started_at, error_message 
FROM agentic_workflow_executions 
WHERE article_id = 68 
ORDER BY created_at DESC 
LIMIT 5;
```

**Fix:**
- Check Celery worker is running: `docker ps | grep cti_worker`
- Check worker logs: `docker logs cti_worker --tail 100`
- Retry stuck executions via UI or API

### 2. Hybrid Extractor Being Used
If `use_hybrid_extractor=True`, the hybrid extractor runs first and may return results without calling LMStudio.

**Check:**
- If a hybrid extractor is enabled, it may run first and return results without calling LMStudio. Verify workflow configuration and execution logs.

**Fix:**
- Verify no hybrid extractor is enabled for the eval path (check env and workflow config).
- Check execution logs for hybrid extractor usage.

### 3. Execution Failing Before LLM Call
The workflow may be failing at an earlier step (junk filter, OS detection, etc.).

**Check:**
```sql
SELECT 
    id, 
    status, 
    current_step, 
    error_message, 
    error_log 
FROM agentic_workflow_executions 
WHERE article_id = 68 
ORDER BY created_at DESC 
LIMIT 1;
```

**Fix:**
- Review `error_log` JSON for step-specific errors
- Check application logs: `docker logs cti_web --tail 200`

### 4. LMStudio Not Receiving Requests
The HTTP requests may not be reaching LMStudio.

**Check:**
- LMStudio is running and accessible
- `LMSTUDIO_API_URL` is correct (default: `http://host.docker.internal:1234/v1`)
- Network connectivity from container to host

**Verify:**
```bash
# From inside container
curl -X POST http://host.docker.internal:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"test"}]}'
```

### 5. Log Level Too High
LMStudio request logs are at INFO level.

**Check:**
- Application log level: `LOG_LEVEL` env var
- Look for: `"Attempting LMStudio at {url} with model {model}"`

**Fix:**
- Set `LOG_LEVEL=INFO` or `LOG_LEVEL=DEBUG`
- Check logs: `docker logs cti_worker --tail 500 | grep -i lmstudio`

## Diagnostic Steps

### Step 1: Verify Execution Status
```python
from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable

db = DatabaseManager()
session = db.get_session()
exec = session.query(AgenticWorkflowExecutionTable).filter(
    AgenticWorkflowExecutionTable.article_id == 68
).order_by(AgenticWorkflowExecutionTable.created_at.desc()).first()

print(f"Status: {exec.status}")
print(f"Step: {exec.current_step}")
print(f"Error: {exec.error_message}")
print(f"Config: {exec.config_snapshot}")
```

### Step 2: Check Worker Logs
```bash
docker logs cti_worker --tail 500 | grep -E "(CmdlineExtract|LMStudio|extraction)"
```

### Step 3: Verify LMStudio Connectivity
```bash
docker exec cti_worker curl -X POST http://host.docker.internal:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"test"}]}'
```

### Step 4: Check Langfuse Traces
If Langfuse is enabled, check for traces:
- UI: Click "🔍 Trace" button on execution
- Or check Langfuse dashboard for session `workflow_exec_{execution_id}`

## Expected Log Sequence

When evaluation runs correctly, you should see:

1. **Workflow Start:**
   ```
   INFO: Triggering agentic workflow for article 68 (execution_id: XXX)
   ```

2. **Extraction Agent Start:**
   ```
   INFO: Running extraction agent CmdlineExtract (QA enabled: False)
   ```

3. **LMStudio Request:**
   ```
   INFO: Attempting LMStudio at http://host.docker.internal:1234/v1 with model {model} (CmdlineExtract extraction attempt 1)
   ```

4. **Response:**
   ```
   INFO: CmdlineExtract raw response length: XXX chars
   INFO: CmdlineExtract token usage: {...}
   ```

## Quick Fixes

### Force LLM Extraction (Disable Hybrid)
Set in workflow config or execution snapshot:
```python
config_snapshot = {
    ...
    'use_hybrid_extractor': False,  # Force LLM extraction
}
```

### Enable Debug Logging
```bash
docker exec cti_web sh -c 'export LOG_LEVEL=DEBUG'
# Or in docker-compose.yml:
environment:
  - LOG_LEVEL=DEBUG
```

### Retry Stuck Execution
```python
# Via API
POST /api/workflow/executions/{execution_id}/retry
```

## Related Files
- `src/workflows/agentic_workflow.py:944` - `use_hybrid_extractor=False` setting
- `src/services/llm_service.py:2555-2568` - Hybrid extractor logic
- `src/services/llm_service.py:2629-2650` - LLM call with tracing
- `src/services/llm_service.py:971-974` - LMStudio request logging

---

# Troubleshooting: Evaluation Executions Stuck in Pending

## Root Cause

**Issue:** Evaluation executions are created with `status='pending'` but never start processing, resulting in no LMStudio logs.

**Root Cause:** Celery worker is at capacity processing other tasks, preventing `trigger_agentic_workflow` tasks from being picked up.

## Evidence

### 1. Tasks Queued But Not Processing
```bash
docker exec cti_worker celery -A src.worker.celery_app inspect reserved
```

Shows multiple `trigger_agentic_workflow` tasks in the `workflows` or `default` queue:
- All have `'time_start': None` and `'worker_pid': None`
- Tasks are queued but not being executed

### 2. Worker Capacity
- **Max concurrency:** 12 workers
- **Prefetch count:** 12 tasks
- **Active tasks:** Worker slots are filled with long-running tasks (especially `check_all_sources`)

### 3. Task Routing
- `trigger_agentic_workflow` → `workflows` queue (as configured in `src/worker/celeryconfig.py`). Default queue used when no specific routing is set.
- `check_all_sources` → `source_checks` queue
- Worker processes both queues, but `source_checks` tasks are long-running and block capacity

## Why This Happens

1. **Source check tasks are long-running** - They scrape websites, which can take minutes
2. **Worker prefetch fills up** - Worker reserves 12 tasks, but if they're all long-running, new tasks wait
3. **No priority mechanism** - Workflow tasks have same priority as source checks
4. **Sequential processing** - Tasks are processed in order, so workflow tasks wait behind source checks

## Solutions

### Option 1: Increase Worker Concurrency (Quick Fix)
```bash
# In docker-compose.yml, increase worker concurrency
celery -A src.worker.celery_app worker --concurrency=24
```

**Pros:** More capacity for parallel processing
**Cons:** Higher memory usage

### Option 2: Dedicated Workflow Queue (Recommended)
Create a separate queue for workflow tasks with dedicated workers:

**In `src/worker/celeryconfig.py`:**
```python
task_routes = {
    'src.worker.celery_app.check_all_sources': {'queue': 'source_checks'},
    'src.worker.celery_app.trigger_agentic_workflow': {'queue': 'workflows'},  # Add this
    # ... other routes
}

task_queues = {
    # ... existing queues
    'workflows': {
        'exchange': 'workflows',
        'routing_key': 'workflows',
    },
}
```

**Start dedicated worker:**
```bash
celery -A src.worker.celery_app worker -Q workflows --concurrency=4
```

**Pros:** Workflow tasks never blocked by source checks
**Cons:** Requires additional worker process

### Option 3: Reduce Prefetch Multiplier
**In `src/worker/celeryconfig.py`:**
```python
worker_prefetch_multiplier = 1  # Already set, but ensure it's low
```

Lower prefetch means worker doesn't reserve as many tasks, allowing faster task rotation.

### Option 4: Priority Queue (Advanced)
Use Celery priority queues to give workflow tasks higher priority than source checks.

### Option 5: Manual Trigger (Workaround)
For immediate needs, manually trigger stuck executions:
```python
from src.worker.celery_app import trigger_agentic_workflow
trigger_agentic_workflow.delay(article_id)
```

## Diagnostic Commands

### Check Queued Tasks
```bash
docker exec cti_worker celery -A src.worker.celery_app inspect reserved | grep trigger_agentic_workflow
```

### Check Active Tasks
```bash
docker exec cti_worker celery -A src.worker.celery_app inspect active
```

### Check Worker Stats
```bash
docker exec cti_worker celery -A src.worker.celery_app inspect stats
```

### Check Pending Executions
```sql
SELECT id, article_id, status, created_at 
FROM agentic_workflow_executions 
WHERE status = 'pending' 
ORDER BY created_at DESC;
```

## Immediate Workaround

If executions are stuck, manually trigger them:
```python
from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable
from src.worker.celery_app import trigger_agentic_workflow

db = DatabaseManager()
session = db.get_session()
pending = session.query(AgenticWorkflowExecutionTable).filter(
    AgenticWorkflowExecutionTable.status == 'pending'
).all()

for exec in pending:
    trigger_agentic_workflow.delay(exec.article_id)
```

## Prevention

1. **Monitor queue depth** - Alert when `default` queue has > 10 tasks
2. **Separate queues** - Use dedicated queue for workflow tasks
3. **Task timeouts** - Set reasonable timeouts for long-running tasks
4. **Worker scaling** - Scale workers based on queue depth

## Related Files
- `src/worker/celeryconfig.py` - Celery configuration
- `src/worker/celery_app.py:629` - `trigger_agentic_workflow` task definition
- `src/web/routes/evaluation_api.py:862` - Task dispatch in eval API

---

_Last updated: February 2025_
