# Workflow Data Flow Architecture

This document details how data flows through the agentic workflow, including memory storage, database persistence, and supervisor aggregation.

## Overview

The agentic workflow processes articles through multiple steps, with data stored in both **memory** (during execution) and **database** (for persistence). This document explains the data flow from sub-agent extraction through supervisor aggregation to SIGMA generation.

## Data Storage Locations

### 1. In-Memory Storage (Temporary)

During workflow execution, data is stored in the workflow state dictionary:

```python
state = {
    'extraction_result': {...},  # Aggregated results
    'subresults': {...},         # Individual sub-agent outputs
    ...
}
```

**Characteristics:**
- **Lifetime**: Exists only during workflow execution
- **Purpose**: Fast access for next workflow steps
- **Location**: Python process memory (LangGraph state)
- **Cleared**: When workflow completes or fails

### 2. Database Storage (Persistent)

Results are persisted to PostgreSQL in JSONB format:

**Table**: `agentic_workflow_executions`  
**Column**: `extraction_result` (JSONB)

**Characteristics:**
- **Lifetime**: Permanent (until deleted)
- **Purpose**: Audit trail, debugging, historical analysis
- **Location**: PostgreSQL database
- **Format**: JSONB (binary JSON, queryable)

## Extraction Agent Data Flow

### Step 1: Sub-Agent Execution

Each sub-agent (CmdlineExtract, HuntQueriesExtract, ProcTreeExtract) runs and produces results:

```python
# Sub-agents run sequentially (RegExtract, EventCodeExtract, SigExtract deprecated)
subresults = {
    "cmdline": {
        "items": [...],      # Extracted command lines
        "count": 4,
        "raw": {...}         # Full CmdlineExtract output including qa_corrections
    },
    "hunt_queries": {...},   # or sigma_queries
    "process_lineage": {...}
}
```

**Storage**: In-memory `subresults` dictionary

### Step 2: Supervisor Aggregation

The supervisor agent collects all sub-agent outputs and normalizes them before merging. Each item is tagged with its source level and a lightweight summary is appended for SIGMA input.

```python
# Supervisor aggregation (lines 1731-1784 in agentic_workflow.py)
all_observables = []
content_summary = []

for cat, data in subresults.items():
    items = data.get("items", [])
    if items is None:
        items = []
    elif not isinstance(items, list):
        items = [items]

    if not items:
        continue

    content_summary.append(f"Extracted {cat.replace('_', ' ').title()}:")
    for item in items:
        normalized_value = item
        if isinstance(item, dict):
            normalized_value = item.get("value", item)

        all_observables.append({
            "type": cat,
            "value": normalized_value,
            "original_data": item if isinstance(item, dict) else None,
            "source": "supervisor_aggregation"
        })
        content_summary.append(f"- {json.dumps(item, indent=None) if isinstance(item, dict) else item}")
    content_summary.append("")

extraction_result = {
    "observables": all_observables,
    "summary": {
        "count": len(all_observables),
        "source_url": article.canonical_url,
        "platforms_detected": ["Windows"]
    },
    "discrete_huntables_count": len(all_observables),
    "subresults": subresults,
    "content": "\n".join(content_summary) if content_summary else "",
    "raw_response": json.dumps(subresults, indent=2)
}
```

**Storage**: 
- In-memory: `state['extraction_result']`
- Database: `execution.extraction_result` (JSONB)

### Step 3: Database Persistence

The execution row is updated with both the extracted conversation log and the aggregated result before committing:

```python
# Lines 1786-1818 in agentic_workflow.py
if execution:
    execution.error_log = execution.error_log or {}
    execution.error_log['extract_agent'] = {
        'conversation_log': conversation_log,
        'sub_agents_run': sub_agents_run,
        'sub_agents_disabled': disabled_sub_agents,
        'completed': True,
        'completed_at': datetime.now().isoformat()
    }
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(execution, 'error_log')
    db_session.commit()

    execution.extraction_result = extraction_result
    db_session.commit()
```

**Database Structure:**
```json
{
  "observables": [...],
  "summary": {...},
  "discrete_huntables_count": 4,
  "subresults": {
    "cmdline": {
      "items": ["e.exe -d=\"E:\\\"", ...],
      "count": 4,
      "raw": {
        "cmdline_items": [...],
        "count": 4,
        "qa_corrections": {...}
      }
    },
    ...
  },
  "content": "Extracted Command Line:\n- e.exe -d=\"E:\\\"\n...",
  "raw_response": "..."
}
```

### Step 4: SIGMA Agent Consumption

The SIGMA node reads the in-memory `extraction_result` and picks the best content before calling the SigmaGenerationService:

```python
# Lines 1904-1990 in agentic_workflow.py
sigma_fallback_enabled = config_obj.sigma_fallback_enabled if config_obj and hasattr(config_obj, 'sigma_fallback_enabled') else False
extraction_result = state.get('extraction_result', {})
content_to_use = None

if sigma_fallback_enabled:
    content_to_use = filtered_content
    logger.info(f"[Workflow {state['execution_id']}] Using filtered article content ({len(filtered_content)} chars) for SIGMA generation")
elif extraction_result and extraction_result.get('discrete_huntables_count', 0) > 0:
    extracted_content = extraction_result.get('content', '')
    if extracted_content and len(extracted_content) > 100:
        content_to_use = extracted_content
        logger.info(f"[Workflow {state['execution_id']}] Using extracted content ({len(extracted_content)} chars) for SIGMA generation")
    else:
        logger.warning(f"[Workflow {state['execution_id']}] Extraction result has {extraction_result.get('discrete_huntables_count', 0)} huntables but no usable content")

if content_to_use is None:
    logger.warning(f"[Workflow {state['execution_id']}] No extraction result or filtered content toggle disabled. Skipping SIGMA generation.")
    return {
        **state,
        'sigma_rules': [],
        'current_step': 'generate_sigma',
        'status': state.get('status', 'running'),
        'termination_reason': TERMINATION_REASON_NO_SIGMA_RULES,
        'termination_details': {
            'reason': 'No extraction result or filtered content disabled',
            'discrete_huntables_count': extraction_result.get('discrete_huntables_count', 0) if extraction_result else 0,
            'sigma_fallback_enabled': sigma_fallback_enabled
        }
    }
```

**Content Selection Priority:**
1. **Filtered article content** (if `sigma_fallback_enabled = True`) - always used when enabled
2. **Extracted content** (if `discrete_huntables_count > 0`, content length > 100, and toggle is disabled)
3. **Skip SIGMA generation** (if fallback disabled and no extraction results)

_Note: `sigma_fallback_enabled` defaults to `False`, so Sigma generation normally requires usable extraction content unless the active workflow configuration explicitly overrides the flag._

_Note: `sigma_fallback_enabled` defaults to `False`, so Sigma generation normally requires usable extraction content unless the active workflow configuration explicitly overrides the flag._

**Why memory?**
- Faster access (no database query)
- Workflow is sequential (extraction → SIGMA within the same execution)
- Database is for persistence/audit, not execution logic

**Important:** When every sub-agent returns zero items and fallback is disabled, SIGMA generation returns early with `termination_reason: 'no_sigma_rules'`.

## Celery vs Direct Execution

### Same Workflow Implementation

Both execution paths use the **same workflow code**:

**Celery Path:**
```
trigger_agentic_workflow() (Celery task)
  → run_workflow()
    → create_agentic_workflow()
      → extract_agent_node()  # Same supervisor aggregation
```

**Direct Path:**
```
API endpoint / workflow trigger
  → run_workflow()
    → create_agentic_workflow()
      → extract_agent_node()  # Same supervisor aggregation
```

**Difference:**
- **Trigger**: Background worker (Celery) vs synchronous (direct)
- **Execution**: Same workflow logic, same data flow
- **Storage**: Same memory → database pattern

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Sub-Agent Execution                       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │Cmdline   │  │HuntQuery │  │ProcTree  │
    │Extract   │  │Extract   │  │Extract   │
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │             │             │
         └─────────────┴─────────────┘
                          │
                          ▼
         ┌──────────────────────────────┐
         │  subresults (in memory)      │
         │  {                            │
         │    "cmdline": {...},          │
         │    "hunt_queries": {...},     │
         │    "process_lineage": {...}   │
         │  }                            │
         └──────────────┬─────────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  Supervisor Aggregation      │
         │  • Merge all items           │
         │  • Create content summary    │
         │  • Build extraction_result   │
         └──────────────┬───────────────┘
                        │
                        ├──────────────────────┐
                        │                      │
                        ▼                      ▼
         ┌──────────────────────┐  ┌──────────────────────┐
         │  Memory Storage      │  │  Database Storage   │
         │  state[              │  │  execution.         │
         │    'extraction_      │  │    extraction_      │
         │     result'          │  │    result (JSONB)   │
         │  ]                   │  │                     │
         └──────────┬───────────┘  └──────────────────────┘
                    │
                    │ (Used by SIGMA agent)
                    ▼
         ┌──────────────────────────────┐
         │  SIGMA Generation            │
         │  Reads:                      │
         │  extraction_result['content']│
         │  (from memory)                │
         └──────────────────────────────┘
```

## Key Points

1. **Sub-agents → Supervisor**: All sub-agent results collected in `subresults` dictionary (memory)

2. **Supervisor Aggregation**: Creates unified `extraction_result` with:
   - `observables`: Merged list of all items
   - `content`: Text summary for SIGMA agent
   - `subresults`: Detailed breakdown preserved

3. **Dual Storage**:
   - **Memory**: For workflow execution (fast, temporary)
   - **Database**: For persistence (audit, debugging)

4. **SIGMA Agent**: Reads from memory (`state['extraction_result']['content']`), not database

5. **Celery vs Direct**: Same workflow code, same data flow, different trigger mechanism

## Database Schema

**Table**: `agentic_workflow_executions`

```sql
CREATE TABLE agentic_workflow_executions (
    id SERIAL PRIMARY KEY,
    article_id INTEGER REFERENCES articles(id),
    status VARCHAR(50),
    current_step VARCHAR(50),
    extraction_result JSONB,  -- Stores full extraction_result structure
    ...
);
```

**Querying Extraction Results:**

```sql
-- Get extraction results for an article
SELECT extraction_result 
FROM agentic_workflow_executions 
WHERE article_id = 1427 
  AND status = 'completed';

-- Query specific sub-agent results
SELECT extraction_result->'subresults'->'cmdline'->>'count' as cmdline_count
FROM agentic_workflow_executions
WHERE article_id = 1427;
```

## LangFuse Trace Creation and Session Tracking

Every workflow execution creates a LangFuse trace with session tracking for debugging and monitoring.

### Trace Lifecycle

1. **Session Creation**: Each execution creates a session with ID format `workflow_exec_{execution_id}`
2. **Trace Creation**: A trace is created with a 32-character trace ID
3. **Span Recording**: Individual workflow steps are recorded as spans within the trace
4. **Trace Flush**: Traces are flushed at execution completion or error

### Implementation

The LangFuse integration is implemented in `src/utils/langfuse_client.py` using the LangFuse OpenTelemetry SDK:

```python
from langfuse.types import TraceContext

# Create trace context with session_id
trace_context = TraceContext(
    session_id=f"workflow_exec_{execution_id}",
    user_id=f"article_{article_id}",
)

# Start trace as current span
span_cm = client.start_as_current_span(
    trace_context=trace_context,
    name=f"agentic_workflow_execution_{execution_id}",
    input={"execution_id": execution_id, "article_id": article_id},
    metadata={"workflow_type": "agentic_workflow", ...}
)
span = span_cm.__enter__()

# Explicitly associate with session (required in LangFuse 3.x)
span.update_trace(session_id=session_id)

# Store trace_id (32 chars) for debug links
trace_id = span.trace_id
```

### Session Association

In LangFuse 3.x with OpenTelemetry, two steps are required to associate a trace with a session:

1. **Pass session_id in TraceContext**: This provides context during span creation
2. **Call span.update_trace()**: This explicitly associates the trace with the session

Without the explicit `update_trace()` call, the session view in LangFuse will be empty even though traces exist.

### Trace Storage

The trace ID is stored in the database for debug link generation:

```python
# In agentic_workflow.py
trace_id_value = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
execution.trace_id = trace_id_value  # 32-char trace ID, not 16-char span ID
db_session.commit()
```

**Important**: Store the `trace_id` (32 characters), not the span `id` (16 characters). The span ID is insufficient for LangFuse trace lookups.

### Debug Links

Debug buttons in the UI generate LangFuse session URLs:

```python
# In workflow_executions.py
session_id = f"workflow_exec_{execution.id}"
agent_chat_url = f"{langfuse_host}/project/{project_id}/sessions/{session_id}"
```

**Example URL**: `https://us.cloud.langfuse.com/project/{project_id}/sessions/workflow_exec_86`

### Viewing Traces

- **Session View** (recommended): Shows all traces for an execution grouped together
- **Trace View**: Shows individual trace details with spans, inputs, outputs, and token usage

See [Debugging](../development/debugging.md) for detailed debugging instructions.

## Execution Methods: Celery (LangGraph state machine) vs Direct Testing

All workflow executions run the same LangGraph state machine (`src/workflows/agentic_workflow.py`); Celery and the direct API simply differ in how they trigger that graph.

### 1. Celery (Background + LangGraph state machine)

**When Used:**
- "Send to Workflow" button on the article page (default)
- Automated high-hunt-score triggers, scheduled jobs, and the executions retry endpoint

**Flow:**
```
User action / automated trigger
  → WorkflowTriggerService.trigger_workflow()
    → trigger_agentic_workflow.delay(article_id)  # Celery task
      → run_workflow() (LangGraph state machine)
```

**Characteristics:**
- ✅ **Production ready**: Queues work, scales across workers
- ✅ **Tracing**: LangFuse traces are emitted when configured
- ✅ **Background**: UI gets an immediate acknowledgement
- ⚠️ **Debugger friendly via LangFuse**: No embedded http debugger, lean on trace views

**Code references:**
- `src/services/workflow_trigger_service.py:120-165` (creates execution + dispatches Celery)
- `src/worker/celery_app.py:637-679` (`trigger_agentic_workflow` task)
- `src/web/routes/workflow_executions.py:1046-1105` (`/api/workflow/articles/{article_id}/trigger`)
- `src/web/routes/workflow_executions.py:694-770` (`/api/workflow/executions/{execution_id}/retry`)

**Note:** The UI still appends `use_langgraph_server` query flags for compatibility, but the backend ignores that parameter—the LangGraph graph always executes inside the Celery task now. The standalone LangGraph server referenced in earlier docs no longer exists.

### 2. Direct Execution (Testing - Single Agent)

**When Used:**
- Workflow config UI's "Test with Article" button
- Direct API calls to `POST /api/workflow/config/test-subagent`

**Flow:**
```
Test button → test_sub_agent() endpoint → llm_service.run_extraction_agent() → immediate result
```

**Characteristics:**
- ✅ **Immediate feedback**: Synchronous execution
- ✅ **Isolated**: Only a single agent runs (no Sigma or similarity stages)
- ⚠️ **No persistence**: Execution records are not written
- ⚠️ **No LangFuse traces**: Runs in-process, no background worker

**Code references:**
- `src/web/routes/workflow_config.py:579-680`
- `src/web/templates/workflow.html:2051-2087`

### Comparison Table

| Aspect | Celery (LangGraph state machine) | Direct Test |
|--------|----------------------------------|-------------|
| **Use Case** | Production workflows | Prompt/agent testing |
| **Execution** | Background async | Synchronous |
| **Speed** | Fast (queued) | Fastest |
| **Debugging** | LangFuse trace views | Console logs |
| **Traces** | Optional (LangFuse) | None |
| **Persistence** | Execution DB records | None |
| **Scope** | Full extraction → Sigma → similarity | Single agent |

### How to Choose

- **Production runs**: Use the Celery path (article page buttons, automated triggers, retries)
- **Debugging/replays**: Trigger a retry and inspect the LangFuse trace (the task still runs via Celery)
- **Agent/prompt testing**: Use the direct endpoint in the workflow config UI

## Code References

- **Sub-agent execution**: `src/workflows/agentic_workflow.py:859-1110`
- **Supervisor aggregation**: `src/workflows/agentic_workflow.py:1641-1680`
- **Database persistence**: `src/workflows/agentic_workflow.py:1695-1744`
- **SIGMA consumption**: `src/workflows/agentic_workflow.py:1772-1860`
- **Celery trigger task**: `src/worker/celery_app.py:637-679`
- **Workflow trigger service**: `src/services/workflow_trigger_service.py:120-165`
- **Retry execution trigger**: `src/web/routes/workflow_executions.py:694-770`
- **Manual trigger endpoint**: `src/web/routes/workflow_executions.py:1046-1105`
- **Direct test trigger**: `src/web/routes/workflow_config.py:579-680`
- **Database model**: `src/database/models.py:536-573` (AgenticWorkflowExecutionTable)
<!--stackedit_data:
eyJoaXN0b3J5IjpbNjUyNDE3NjkwXX0=
-->