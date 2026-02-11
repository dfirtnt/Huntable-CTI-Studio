# Troubleshooting: Evaluation Executions Stuck in Pending

## Root Cause

**Issue:** Evaluation executions are created with `status='pending'` but never start processing, resulting in no LMStudio logs.

**Root Cause:** Celery worker is at capacity processing other tasks, preventing `trigger_agentic_workflow` tasks from being picked up.

## Evidence

### 1. Tasks Queued But Not Processing
```bash
docker exec cti_worker celery -A src.worker.celery_app inspect reserved
```

Shows multiple `trigger_agentic_workflow` tasks in the `workflowsdefault` queue:
- All have `'time_start': None` and `'worker_pid': None`
- Tasks are queued but not being executed

### 2. Worker Capacity
- **Max concurrency:** 12 workers
- **Prefetch count:** 12 tasks
- **Active tasks:** Worker slots are filled with long-running tasks (especially `check_all_sources`)

### 3. Task Routing
- `trigger_agentic_workflow` → `workflows` queue (as configured in celeryconfig.pydefault` queue (no specific routing)
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

<!--stackedit_data:
eyJoaXN0b3J5IjpbLTE4Mjc0ODc2MDldfQ==
-->