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

Each sub-agent (CmdlineExtract, SigExtract, etc.) runs and produces results:

```python
# Sub-agents run sequentially
subresults = {
    "cmdline": {
        "items": [...],      # Extracted command lines
        "count": 4,
        "raw": {...}         # Full CmdlineExtract output including qa_corrections
    },
    "sigma_queries": {...},
    "event_ids": {...},
    "process_lineage": {...},
    "registry_keys": {...}
}
```

**Storage**: In-memory `subresults` dictionary

### Step 2: Supervisor Aggregation

The supervisor agent collects all sub-agent outputs and aggregates them:

```python
# Supervisor aggregation (lines 689-720 in agentic_workflow.py)
all_observables = []  # Unified list
content_summary = []  # Text summary for SIGMA

for cat, data in subresults.items():
    items = data.get("items", [])
    for item in items:
        all_observables.append({
            "type": cat,
            "value": item,
            "source": "supervisor_aggregation"
        })
        content_summary.append(f"- {item}")

extraction_result = {
    "observables": all_observables,
    "summary": {
        "count": total_count,
        "source_url": article.canonical_url,
        "platforms_detected": ["Windows"]
    },
    "discrete_huntables_count": total_count,
    "subresults": subresults,  # Preserve detailed breakdown
    "content": "\n".join(content_summary),  # Text for SIGMA agent
    "raw_response": json.dumps(subresults, indent=2)
}
```

**Storage**: 
- In-memory: `state['extraction_result']`
- Database: `execution.extraction_result` (JSONB)

### Step 3: Database Persistence

The aggregated result is committed to the database:

```python
# Line 752 in agentic_workflow.py
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

The SIGMA generation agent reads from memory (not database), with fallback logic:

```python
# Lines 836-856 in agentic_workflow.py
extraction_result = state.get('extraction_result', {})  # From memory
content_to_use = None

if extraction_result and extraction_result.get('discrete_huntables_count', 0) > 0:
    # Prefer extracted content if we have meaningful huntables
    extracted_content = extraction_result.get('content', '')
    if extracted_content and len(extracted_content) > 100:
        content_to_use = extracted_content

# Fallback logic
if content_to_use is None:
    if sigma_fallback_enabled:
        content_to_use = filtered_content  # Use original filtered content
    else:
        # Skip SIGMA generation if fallback disabled and no extraction results
        return {'sigma_rules': [], 'termination_reason': 'no_sigma_rules'}
```

**Content Selection Priority:**
1. **Extracted content** (if `discrete_huntables_count > 0` and content length > 100)
2. **Filtered content** (if `sigma_fallback_enabled = True`)
3. **Skip SIGMA generation** (if fallback disabled and no extraction results)

**Why memory?**
- Faster access (no database query)
- Workflow is sequential (extraction → SIGMA in same execution)
- Database is for persistence/audit, not workflow execution

**Important:** If all sub-agents return 0 items and `sigma_fallback_enabled` is `False`, SIGMA generation is skipped and the workflow terminates with `termination_reason: 'no_sigma_rules'`.

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
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │Cmdline   │  │Sig       │  │Event     │  │Proc      │  ...
    │Extract   │  │Extract   │  │Extract   │  │Extract   │
    └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
         │             │             │             │
         └─────────────┴─────────────┴─────────────┘
                          │
                          ▼
         ┌──────────────────────────────┐
         │  subresults (in memory)      │
         │  {                            │
         │    "cmdline": {...},          │
         │    "sigma_queries": {...},    │
         │    ...                        │
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

**Example URL**: `https://us.cloud.langfuse.com/project/cmhk4f8nr02m9ad07cq29m3be/sessions/workflow_exec_86`

### Viewing Traces

- **Session View** (recommended): Shows all traces for an execution grouped together
- **Trace View**: Shows individual trace details with spans, inputs, outputs, and token usage

See [DEBUGGING_TOOLS_GUIDE.md](DEBUGGING_TOOLS_GUIDE.md#langfuse-workflow-debugging) for detailed debugging instructions.

## Execution Methods: Celery vs LangGraph Server vs Direct

The workflow can be executed via three different methods, each serving different purposes:

### 1. Celery (Production - Background Execution)

**When Used:**
- "Send to Workflow" button from article page (default)
- Automatic workflow triggers (high hunt score articles)
- Scheduled/background processing

**Flow:**
```
User Action / Auto Trigger
  → WorkflowTriggerService.trigger_workflow()
    → trigger_agentic_workflow.delay(article_id)  # Celery task
      → Background worker executes workflow
```

**Characteristics:**
- ✅ **Fast**: No debugging overhead
- ✅ **Non-blocking**: Returns immediately
- ✅ **Production-ready**: Optimized for performance
- ⚠️ **Limited debugging**: No time-travel, state inspection
- ⚠️ **Traces**: Only if LangFuse enabled separately

**Code:**
- Trigger: `src/services/workflow_trigger_service.py:157`
- Task: `src/worker/celery_app.py:527-563`
- Article page: `src/web/templates/article_detail.html:7127` (uses `use_langgraph_server=false`)

### 2. LangGraph Server (Debugging - HTTP API)

**When Used:**
- "Retry (Trace)" button from workflow executions page
- Manual workflow execution with `use_langgraph_server=true`
- Development/debugging scenarios

**Flow:**
```
User Action (with trace option)
  → POST /api/workflow/articles/{id}/trigger?use_langgraph_server=true
    → _trigger_via_langgraph_server()
      → HTTP POST to LangGraph Server API
        → LangGraph Server executes workflow
```

**Characteristics:**
- ✅ **Full debugging**: Time-travel, state inspection
- ✅ **Always creates traces**: LangFuse integration
- ✅ **Agent Chat UI**: Compatible with debugging interface
- ⚠️ **Slower**: Debugging overhead
- ⚠️ **Requires server**: LangGraph server must be running

**Code:**
- Endpoint: `src/web/routes/workflow_executions.py:495-564`
- Trigger: `src/web/routes/workflow_executions.py:616-686` (retry with trace)
- Server: `src/workflows/langgraph_server.py`

### 3. Direct Execution (Testing - Single Agent)

**When Used:**
- "Test with Article 1427" button from workflow config page
- Agent configuration testing
- Quick validation of agent prompts

**Flow:**
```
Test Button Click
  → POST /api/workflow/config/test-subagent
    → test_sub_agent() endpoint
      → llm_service.run_extraction_agent()  # Direct call
        → Returns result immediately
```

**Characteristics:**
- ✅ **Fastest**: No workflow overhead
- ✅ **Isolated**: Tests single agent only
- ✅ **Immediate feedback**: Synchronous response
- ⚠️ **No persistence**: Results not saved to database
- ⚠️ **No workflow context**: Doesn't run full workflow steps

**Code:**
- Endpoint: `src/web/routes/workflow_config.py:579-680`
- Frontend: `src/web/templates/workflow.html:2051-2087`

### Comparison Table

| Aspect | Celery | LangGraph Server | Direct Test |
|--------|--------|------------------|-------------|
| **Use Case** | Production | Debugging | Testing |
| **Execution** | Background (async) | HTTP API (async) | Synchronous |
| **Speed** | Fast | Slower (debugging) | Fastest |
| **Debugging** | Limited | Full (time-travel) | None |
| **Traces** | Optional (LangFuse) | Always | Optional (LangFuse) |
| **Persistence** | Database | Database + checkpoints | None |
| **Scope** | Full workflow | Full workflow | Single agent |
| **When to Use** | Production, scheduled | Debugging, development | Prompt testing |

### How to Choose

- **Production workflows**: Use Celery (default from article page)
- **Debugging issues**: Use LangGraph Server (retry with trace)
- **Testing prompts**: Use Direct Test (config page test button)

## Code References

- **Sub-agent execution**: `src/workflows/agentic_workflow.py:590-671`
- **Supervisor aggregation**: `src/workflows/agentic_workflow.py:689-736`
- **Database persistence**: `src/workflows/agentic_workflow.py:750-753`
- **SIGMA consumption**: `src/workflows/agentic_workflow.py:836-843`
- **Celery trigger**: `src/worker/celery_app.py:527-563`
- **LangGraph Server trigger**: `src/web/routes/workflow_executions.py:495-564`
- **Direct test trigger**: `src/web/routes/workflow_config.py:579-680`
- **Database model**: `src/database/models.py:479-515`

