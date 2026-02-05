# Live Execution View Overhaul Plan

## Current Issues

### 1. **Step Progression Misleading**
- `current_step` is set at START of node, not completion
- `generate_sigma` step appears while `extract_agent` sub-agents still running
- No distinction between "step started" vs "step completed"

### 2. **Event Ordering Problems**
- LLM calls from extract agents appear after step changes to generate_sigma
- No context about which step an event belongs to
- Events appear out of logical order

### 3. **QA Result Duplication**
- Complex deduplication logic still allows duplicates
- Multiple QA results for same agent (CmdlineExtract + CmdLineQA)
- Misleading summaries (PASS but "QA failed without feedback")

### 4. **No Hierarchy/Context**
- Sub-agents (CmdlineExtract, ProcTreeExtract) shown at same level as main steps
- No grouping or parent-child relationships
- Hard to understand what's running when

### 5. **Polling Limitations**
- 1-second polling delay causes events to appear out of order
- No real-time event ordering guarantees

## Proposed Solution

### Phase 1: Enhanced Event Structure

Add context to all events:

```python
{
    "type": "llm_interaction",
    "step": "extract_agent",  # Parent workflow step
    "sub_step": "CmdlineExtract",  # Sub-agent if applicable
    "agent": "CmdlineExtract",
    "step_phase": "running",  # "starting", "running", "completed"
    "timestamp": "...",
    "messages": [...],
    "response": "..."
}
```

### Phase 2: Step Lifecycle Tracking

Track step start/end explicitly:

```python
# When step starts
{
    "type": "step_start",
    "step": "extract_agent",
    "timestamp": "..."
}

# When step completes
{
    "type": "step_complete", 
    "step": "extract_agent",
    "timestamp": "...",
    "duration_ms": 1234
}
```

### Phase 3: Sub-Agent Grouping

Group sub-agents under parent step:

```python
{
    "type": "sub_agent_start",
    "parent_step": "extract_agent",
    "sub_agent": "CmdlineExtract",
    "timestamp": "..."
}
```

### Phase 4: Simplified QA Deduplication

- Store QA results once per agent (not both agent_name and qa_name)
- Emit QA results grouped by parent step
- Fix summary generation to match verdict

### Phase 5: Frontend Display

- Hierarchical display: Main steps → Sub-agents
- Visual indicators for step phases (starting/running/completed)
- Group related events together
- Show step duration

## Implementation Priority

1. **Critical**: Fix step progression (don't show generate_sigma until extract_agent completes)
2. **High**: Add step context to all events
3. **High**: Fix QA result deduplication and summaries
4. **Medium**: Add step lifecycle events (start/complete)
5. **Medium**: Hierarchical display in frontend
