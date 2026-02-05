# CTI Scraper Debugging Tools Guide

This comprehensive guide covers the enhanced debugging capabilities available in the CTI Scraper test suite. These tools are designed to improve developer productivity by providing detailed failure analysis, performance monitoring, and debugging utilities.

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

The CTI Scraper debugging tools provide:

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

The LangFuse integration is implemented in [src/utils/langfuse_client.py](../src/utils/langfuse_client.py):

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

- **Trace creation**: [src/utils/langfuse_client.py:155-189](../src/utils/langfuse_client.py#L155-L189)
- **Workflow execution**: [src/workflows/agentic_workflow.py:1662](../src/workflows/agentic_workflow.py#L1662)
- **Debug link generation**: [src/web/routes/workflow_executions.py:805-814](../src/web/routes/workflow_executions.py#L805-L814)

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

The CTI Scraper debugging tools provide comprehensive support for test debugging and optimization. By using these tools effectively, you can:

- Quickly identify and resolve test failures
- Debug complex async operations
- Monitor and optimize test performance
- Ensure proper test isolation
- Get rich, informative test output

For more information, refer to the individual module documentation and examples in the `tests/utils/` directory.
# CTI Scraper Debugging Tools Guide

This comprehensive guide covers the enhanced debugging capabilities available in the CTI Scraper test suite. These tools are designed to improve developer productivity by providing detailed failure analysis, performance monitoring, and debugging utilities.

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

The CTI Scraper debugging tools provide:

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

The LangFuse integration is implemented in [src/utils/langfuse_client.py](../src/utils/langfuse_client.py):

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

- **Trace creation**: [src/utils/langfuse_client.py:155-189](../src/utils/langfuse_client.py#L155-L189)
- **Workflow execution**: [src/workflows/agentic_workflow.py:1662](../src/workflows/agentic_workflow.py#L1662)
- **Debug link generation**: [src/web/routes/workflow_executions.py:805-814](../src/web/routes/workflow_executions.py#L805-L814)

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

The CTI Scraper debugging tools provide comprehensive support for test debugging and optimization. By using these tools effectively, you can:

- Quickly identify and resolve test failures
- Debug complex async operations
- Monitor and optimize test performance
- Ensure proper test isolation
- Get rich, informative test output

For more information, refer to the individual module documentation and examples in the `tests/utils/` directory.
