# Workflow Queue Setup - Dedicated Workers

## Overview

Workflow tasks (`trigger_agentic_workflow`) are now routed to a dedicated `workflows` queue with dedicated workers, preventing them from being blocked by long-running source check tasks.

## Changes Made

### 1. Celery Configuration (`src/worker/celeryconfig.py`)

**Added workflow queue routing:**
```python
task_routes = {
    # ... existing routes
    'src.worker.celery_app.trigger_agentic_workflow': {'queue': 'workflows'},
}

task_queues = {
    # ... existing queues
    'workflows': {
        'exchange': 'workflows',
        'routing_key': 'workflows',
    },
}
```

### 2. Docker Compose (`docker-compose.yml`)

**Updated main worker** to exclude workflows queue (note: `collection_immediate` is listed first so user-initiated "Collect Now" tasks are consumed before scheduled collection):
```yaml
worker:
  command: celery -A src.worker.celery_app worker --loglevel=${CELERY_LOG_LEVEL:-info} -Q collection_immediate,default,source_checks,maintenance,reports,connectivity,collection --concurrency=${WORKER_CONCURRENCY:-2} --without-gossip --without-mingle --without-heartbeat
```

**Added dedicated workflow worker:**
```yaml
workflow_worker:
  container_name: cti_workflow_worker
  command: celery -A src.worker.celery_app worker --loglevel=${CELERY_LOG_LEVEL:-info} -Q workflows --concurrency=${WORKFLOW_WORKER_CONCURRENCY:-2} --without-gossip --without-mingle --without-heartbeat
  # ... same environment and volumes as main worker
```

## Benefits

1. **Isolation:** Workflow tasks are never blocked by source checks.
2. **Performance:** Dedicated workers run workflow execution without contention from other queues.
3. **Scalability:** Workflow workers scale independently of the main worker (see [Scaling](#scaling)).
4. **Reliability:** Workflow failures don't affect other task types.

## Deployment

### Restart Services

```bash
docker-compose up -d workflow_worker
docker-compose restart worker
```

### Verify Setup

**Check workflow worker is running:**
```bash
docker ps | grep workflow_worker
```

**Check queue routing:**
```bash
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect registered | grep trigger_agentic_workflow
```

**Check worker is consuming workflows queue:**
```bash
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect active_queues
```

**Monitor workflow tasks:**
```bash
docker logs cti_workflow_worker --tail 50 -f
```

## Queue Architecture

```text
┌─────────────────┐
│  Main Worker    │  → Processes: collection_immediate, default, source_checks,
│  (cti_worker)   │              maintenance, reports, connectivity, collection
└─────────────────┘

┌─────────────────┐
│ Workflow Worker │  → Processes: workflows (trigger_agentic_workflow)
│(workflow_worker)│
└─────────────────┘
```

## Monitoring

### Check Queue Depth
```bash
docker exec cti_redis redis-cli LLEN workflows
```
<!-- AUDIT: Accuracy (High) -- original command checked `LLEN celery`, which is not one of this
app's queue keys. celeryconfig.py's task_queues has no "celery" entry; the general queue is
named "default" and the workflow queue is "workflows" (both keyed by queue name under Celery's
redis transport). `LLEN celery` would read an unrelated/empty list and mislead a reader
troubleshooting workflow backlog. Check `default` too if source-check/maintenance backlog is
the concern: `docker exec cti_redis redis-cli LLEN default`. -->

### Check Overall Worker Health

For a broader view (not just the workflows queue), see [Agent Orientation -- Workers and schedules](agent-orientation.md#runtime-entry-points) [VERIFY LINK] and the `AGENTS.md` "Runtime" section (repository root) for the restart requirement on `cti_worker` / `cti_workflow_worker` after `.py` changes.

### Check Workflow Worker Stats
```bash
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect stats
```

### Check Active Tasks
```bash
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect active
```

### Check Reserved Tasks
```bash
docker exec cti_workflow_worker celery -A src.worker.celery_app inspect reserved
```

## Troubleshooting

### Workflow tasks still pending

1. **Check workflow worker is running:**
   ```bash
   docker ps | grep workflow_worker
   ```

2. **Check worker is consuming workflows queue:**
   ```bash
   docker exec cti_workflow_worker celery -A src.worker.celery_app inspect active_queues
   ```
   Should show `workflows` queue.

3. **Check for errors:**
   ```bash
   docker logs cti_workflow_worker --tail 100
   ```

4. **Verify task routing:**
   ```bash
   docker exec cti_workflow_worker celery -A src.worker.celery_app inspect registered | grep trigger_agentic_workflow
   ```

### Worker not starting

1. **Check Redis connectivity:**
   ```bash
   docker exec cti_workflow_worker celery -A src.worker.celery_app inspect ping
   ```

2. **Check database connectivity:**
   ```bash
   docker exec cti_workflow_worker python3 -c "from src.database.manager import DatabaseManager; db = DatabaseManager(); print('DB OK')"
   ```

## Scaling

To scale workflow workers (e.g., for high evaluation load):

```bash
docker-compose up -d --scale workflow_worker=3
```

Or update docker-compose.yml:
```yaml
workflow_worker:
  deploy:
    replicas: 3
```

## Related Files
- `src/worker/celeryconfig.py` - Queue and routing configuration
- `docker-compose.yml` - Worker service definitions
- `src/worker/celery_app.py` - `trigger_agentic_workflow` task

_Last updated: 2026-07-03_
_Last reviewed: 2026-09-01_
