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

