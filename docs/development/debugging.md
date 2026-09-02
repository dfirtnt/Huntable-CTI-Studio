# Debugging

<!-- MERGED FROM: development/DEBUGGING_TOOLS_GUIDE.md, development/DEBUG_EVAL_LMSTUDIO_LOGS.md, development/TROUBLESHOOT_EVAL_PENDING.md -->

## Debugging Tools Guide

This section covers the debugging utilities available in the Huntable CTI Studio test suite: Langfuse workflow tracing, async test debugging, and performance profiling.

## Table of Contents

1. [Overview](#overview)
2. [Langfuse Workflow Debugging](#langfuse-workflow-debugging)
3. [Test Failure Analysis](#test-failure-analysis)
4. [Async Test Debugging](#async-test-debugging)
5. [Test Isolation and Cleanup](#test-isolation-and-cleanup)
6. [Performance Profiling](#performance-profiling)
7. [Enhanced Output Formatting](#enhanced-output-formatting)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Overview

The Huntable CTI Studio debugging tools provide:

- **Langfuse Workflow Debugging**: Session-based tracing for agentic workflow executions with direct links to Langfuse UI
- **Comprehensive Failure Analysis** *(design sketch -- not implemented)*: Automatic categorization and analysis of test failures with actionable suggestions
- **Async Debugging**: Specialized tools for debugging async/await code and event loop issues
- **Test Isolation** *(design sketch -- not implemented)*: Enhanced isolation mechanisms to prevent test interference
- **Performance Profiling**: Detailed performance monitoring and bottleneck identification
- **Rich Output Formatting** *(design sketch -- not implemented)*: Timestamped, colorized, and structured test output

## Langfuse Workflow Debugging

### Overview

The agentic workflow integrates with Langfuse to provide tracing and debugging for workflow executions and LLM calls. Traces are emitted by the LangGraph/Celery runtime when Langfuse is configured; users do not run standalone Langfuse agents.

Langfuse and the workflow database are complementary, not equivalent:

- The database keeps durable workflow state and selected artifacts for audit, UI rendering, and fallback export.
- Langfuse keeps richer trace and generation telemetry, including fuller request/response payloads, token usage, finish reasons, and per-call metadata.
- When both exist, Langfuse is the better source for reconstructing a specific LLM call in detail.
- For some workflow steps, especially extraction, the database may contain truncated top-level message/response copies in `error_log` to keep JSONB payloads manageable.

!!! warning "Cloud-only support and sensitive trace data"
    Huntable CTI Studio supports **Langfuse Cloud only**. Local or self-hosted Langfuse deployments are not supported by this project.

    Trace inspection can expose sensitive prompts, article excerpts, extracted observables, outputs, and workflow metadata. Limit Langfuse access to authorized users and enable tracing only if your organization permits sending that telemetry to Langfuse Cloud.

### Accessing Debug Links

From the Workflow Executions page, each execution has a **Debug** button that prefers a direct Langfuse trace URL and falls back to a trace search for the workflow `session_id` when full trace metadata is unavailable.

Direct trace URL:

```text
https://cloud.langfuse.com/project/{project_id}/traces/{trace_id}
```

Search fallback:

```text
https://cloud.langfuse.com/project/{project_id}/traces?search=workflow_exec_{execution_id}
```

### Session Structure

Each workflow execution creates:

1. **Session ID**: Format `workflow_exec_{execution_id}` (e.g., `workflow_exec_86`)
2. **Trace ID**: 32-character unique identifier for the execution trace
3. **Spans**: Individual workflow steps (extraction, ranking, Sigma generation, etc.)

### Implementation Details

The Langfuse integration is implemented in `src/utils/langfuse_client.py`
(`_LangfuseWorkflowTrace.__enter__`):

```python
from langfuse import propagate_attributes

attributes_cm = propagate_attributes(
    session_id=f"workflow_exec_{execution_id}",
    user_id=f"article_{article_id}",
    trace_name=f"agentic_workflow_execution_{execution_id}",
    tags=[...],
)
attributes_cm.__enter__()

span_cm = client.start_as_current_observation(
    name=f"agentic_workflow_execution_{execution_id}",
    input={"execution_id": execution_id, "article_id": article_id},
    metadata={...},
)
span = span_cm.__enter__()
trace_id = getattr(span, "trace_id", None) or getattr(span, "id", None)
```

### Key Implementation Points

1. **Session Association**: The workflow trace is created with `propagate_attributes(session_id=..., user_id=...)`, which sets session/user on the OTEL context for everything created inside the block. Child generations are linked by `trace_id` and the same `workflow_exec_{execution_id}` session identifier.

2. **Trace ID vs Span ID**:
   - **Trace ID**: 32-character identifier (e.g., `62ed1c144abee5401636ea6c5b9b4f7a`)
   - **Span ID**: 16-character identifier (e.g., `9754b82b9794d922`)
   - Store the **trace ID** for debug links, not the span ID.

3. **Context Manager Handling**: The span context manager must be properly entered with `__enter__()` and exited with `__exit__()` to ensure traces are flushed.

### Viewing Workflow Traces

#### Trace View (Recommended)

The workflow UI prefers a direct trace view when it has both trace and project metadata:

1. Click **Debug** button on workflow execution
2. Open the workflow trace directly in Langfuse
3. See inputs, outputs, and metadata for each step
4. Track token usage and latency per agent

### Database Fallback Limits

If Langfuse is unavailable, the workflow database still preserves useful debugging data in `agentic_workflow_executions.error_log`, but it is less complete than Langfuse:

- top-level `conversation_log` copies may be truncated;
- token usage is not reliably persisted there;
- some request/response reconstruction relies on fallback fields embedded in step results rather than a first-class trace model.

Use the database as the durable fallback. Use Langfuse when you need maximum per-call detail.

#### Search View (Fallback)

If the execution does not have a resolved trace ID or project ID, the UI falls back to Langfuse trace search using the workflow session identifier:

```text
https://cloud.langfuse.com/project/{project_id}/traces?search=workflow_exec_{execution_id}
```

### Debugging Workflow Issues

When debugging workflow failures:

1. **Check Session View**: Start with the session view to see the full execution timeline
2. **Identify Failed Step**: Look for spans with `ERROR` status
3. **Review Inputs/Outputs**: Check the input and output data for each span
4. **Check Metadata**: Review metadata for execution context (article ID, config version, etc.)
5. **Monitor Token Usage**: Track token consumption across agents

### Configuration

Langfuse configuration can be stored in the Settings UI or provided through environment variables. Settings saved in the UI take precedence over environment variables.

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PROJECT_ID=your-project-id
```

- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are required to emit traces.
- `LANGFUSE_HOST` is optional and defaults to `https://us.cloud.langfuse.com` in the runtime client.
- `LANGFUSE_PROJECT_ID` is optional but recommended because it improves workflow debug deep links.
- Use the Langfuse Cloud host for your account region. This project does not support local or self-hosted Langfuse deployments.

For setup, host selection, security guidance, and troubleshooting, see [Langfuse Setup](../guides/langfuse-setup.md).

### Common Setup Failures

- Missing `LANGFUSE_PUBLIC_KEY` or `LANGFUSE_SECRET_KEY`: tracing is disabled and workflows run without emitting Langfuse traces.
- Wrong `LANGFUSE_HOST`: the connection test can fail even with valid keys if the host does not match the Langfuse Cloud region for that project.
- Missing `LANGFUSE_PROJECT_ID`: traces can still be emitted, but workflow debug links may fall back to broader search URLs instead of project-scoped direct links.
- No trace for an execution: traces only exist for runs that actually executed while Langfuse was enabled.

### Code References

- **Trace creation**: `src/utils/langfuse_client.py` (`_LangfuseWorkflowTrace.__enter__`, lines 183-264; `trace_workflow_execution`, line 335)
- **Workflow execution**: `src/workflows/agentic_workflow.py` (`run_workflow`, defined at line 3500; trace opened via `trace_workflow_execution(...)` at line 3755)
- **Debug link generation**: `src/web/routes/workflow_executions.py` (`_build_langfuse_debug_urls` at line 1327 / `get_workflow_debug_info` at line 1351)

## Test Failure Analysis

!!! warning "Not implemented"
    `tests/utils/test_failure_analyzer.py` does not exist in this repository and never has. `tests/conftest.py`
    imports it inside a `try`/`except ImportError` that always fails, pinning
    `FAILURE_ANALYZER_AVAILABLE = False`, so the `failure_reporter` fixture always returns `None`.
    The examples in this section are a design sketch, not runnable code.

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

!!! warning "Not implemented"
    `tests/utils/test_isolation.py` does not exist in this repository and never has. `tests/conftest.py`
    imports it inside a `try`/`except ImportError` that always fails, pinning
    `ISOLATION_AVAILABLE = False`, so the `isolation_manager` fixture always returns `None`.
    The examples in this section are a design sketch, not runnable code.

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

!!! warning "Not implemented"
    `tests/utils/test_output_formatter.py` does not exist in this repository and never has. `tests/conftest.py`
    imports it inside a `try`/`except ImportError` that always fails, pinning
    `OUTPUT_FORMATTER_AVAILABLE = False`, so the `test_output_formatter` fixture always returns `None`.
    The examples in this section are a design sketch, not runnable code.

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

*Not implemented -- see [Test Failure Analysis](#test-failure-analysis) above.*

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

*Not implemented -- see [Test Isolation and Cleanup](#test-isolation-and-cleanup) above.*

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

*Not implemented -- see [Enhanced Output Formatting](#enhanced-output-formatting) above.*

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

*Not implemented -- see [Test Isolation and Cleanup](#test-isolation-and-cleanup) above.*

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

For the modules that actually exist, see `tests/utils/async_debug_utils.py` and `tests/utils/performance_profiler.py` directly for the full API.

---

## Debugging Missing LMStudio Logs in Evaluations

### Issue
When running evaluations via `/mlops/agent-evals`, no LMStudio logs are being generated.

### Root Causes

#### 1. Execution Not Running
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

#### 2. Hybrid Extractor Being Used (removed, no longer a possible cause)

> **Removed** (commit `51c750c0`, 2026-05-04): `HybridIOCExtractor` and the
> `/extract-iocs` endpoint were deleted, and the `use_hybrid_extractor` flag no longer
> exists anywhere in the codebase. Nothing runs ahead of LMStudio on the eval path, so
> this cannot explain missing LMStudio logs; see the other numbered causes in this
> section instead. Retained only so the cause numbering matches older reports.

#### 3. Execution Failing Before LLM Call
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

#### 4. LMStudio Not Receiving Requests
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

#### 5. Log Level Too High
LMStudio request logs are at INFO level, which is the effective floor.

Setting `LOG_LEVEL` has no effect: nothing in `src/` reads it, and the application
log level is hardcoded to `INFO` in `src/web/dependencies.py:78`.

**Check:**
- Look for: `"Attempting LMStudio at {url} with model {model}"` in `docker logs cti_worker`
- If absent, confirm the workflow actually reached the extraction step (see Cause 3 above) rather than assuming a log-level filter is hiding it

**Fix:**
- Check logs: `docker logs cti_worker --tail 500 | grep -i lmstudio`

### Diagnostic Steps

#### Step 1: Verify Execution Status
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

#### Step 2: Check Worker Logs
```bash
docker logs cti_worker --tail 500 | grep -E "(CmdlineExtract|LMStudio|extraction)"
```

#### Step 3: Verify LMStudio Connectivity
```bash
docker exec cti_worker curl -X POST http://host.docker.internal:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"test"}]}'
```

#### Step 4: Check Langfuse Traces
If Langfuse is enabled, check for traces:
- UI: Click the **Debug** button on the execution (see [Accessing Debug Links](#accessing-debug-links) above)
- Or check the Langfuse dashboard for session `workflow_exec_{execution_id}`

### Expected Log Sequence

When evaluation runs correctly, you should see:

1. **Workflow Start:**
   ```text
   INFO: Triggering agentic workflow for article 68 (execution_id: XXX)
   ```

2. **Extraction Agent Start:**
   ```text
   INFO: Running extraction agent CmdlineExtract (provider=lmstudio, model_name=qwen2.5-coder-7b)
   ```

3. **LMStudio Request:**
   ```text
   INFO: Attempting LMStudio at http://host.docker.internal:1234/v1 with model {model} (CmdlineExtract extraction attempt 1)
   ```

4. **Response:**
   ```text
   INFO: CmdlineExtract raw response length: XXX chars
   INFO: CmdlineExtract token usage: {...}
   ```

### Quick Fixes

#### Former Hybrid Extraction Setting

`use_hybrid_extractor` was removed and no longer has any effect on workflow configuration or execution snapshots.

#### Enable Debug Logging
Not currently possible via environment variable; the application log level is hardcoded to `INFO` (`src/web/dependencies.py:78`).

#### Retry Stuck Execution
```python
# Via API
POST /api/workflow/executions/{execution_id}/retry
```

### Related Files
- `src/services/llm_service.py:474` and `:1057` - LLM calls with tracing (`trace_llm_call`)
- `src/services/llm_provider_clients.py:221` - LMStudio request logging (`Attempting LMStudio at {url}...`)

---

## Troubleshooting: Evaluation Executions Stuck in Pending

Workflow executions are routed to a dedicated `workflows` queue and consumed by
`cti_workflow_worker`; source checks run on the main worker's `source_checks`
queue. A pending evaluation therefore indicates a worker-health, routing, or
database problem rather than normal source-check contention.

### Diagnostic Commands

```bash
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect active
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect reserved
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect stats
```

#### Check Pending Executions
```sql
SELECT id, article_id, status, created_at 
FROM agentic_workflow_executions 
WHERE status = 'pending' 
ORDER BY created_at DESC;
```

### Related Files
- `src/worker/celeryconfig.py` - Celery configuration
- `src/worker/celery_app.py:792` - `trigger_agentic_workflow` task definition
- `src/web/routes/evaluation_api.py` - Task dispatch in eval API (`trigger_agentic_workflow.apply_async(...)` at lines 757 and 1474)
- `src/web/routes/workflow_executions.py:1048` - `POST /api/workflow/executions/{execution_id}/retry` endpoint

---

_Last updated: 2026-07-03_
_Last reviewed: 2026-09-01_
