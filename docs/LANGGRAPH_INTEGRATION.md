# LangGraph Agent Chat UI Integration

This document describes the integration of LangChain's Agent Chat UI for debugging agentic workflows.

## Overview

The agentic workflow is exposed via LangGraph's HTTP server, enabling:
- **Time-travel debugging**: Step through execution history
- **State inspection**: View/modify state at any point
- **Tool visualization**: See LLM calls, tool invocations, and results
- **Human-in-the-loop**: Approve/reject at decision points

## Architecture

### Components

1. **LangGraph Server** (`src/workflows/langgraph_server.py`)
   - Exposes workflow via LangGraph HTTP server
   - Uses PostgreSQL checkpointing for state persistence
   - Compatible with Agent Chat UI

2. **Configuration** (`langgraph.json`)
   - Defines workflow graph: `agentic_workflow`
   - Points to exposable workflow function

3. **Operational UI** (`src/web/templates/workflow.html`)
   - Manages configuration, monitoring, queue
   - "Debug" buttons launch Agent Chat UI for specific executions

4. **Agent Chat UI** (hosted or local)
   - Interactive debugging interface
   - Real-time state inspection
   - Tool call visualization

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `langgraph>=0.2.0`
- `langgraph-checkpoint>=0.2.0`
- `langgraph-checkpoint-postgres>=0.2.0`
- `langgraph-cli` (for server)

### 2. Configure Environment

Add to `.env`:
```bash
# Required
LANGGRAPH_SERVER_URL=http://localhost:2024
LANGGRAPH_PORT=2024

# Optional: LangSmith FREE Developer Plan
# Sign up at https://smith.langchain.com - includes:
#   - 1 free seat
#   - Access to LangSmith Studio
#   - 5k traces/month included
# Get API key from: https://smith.langchain.com/settings
LANGSMITH_API_KEY=your_langsmith_api_key_here
```

**Note:** All features work without LangSmith! The free Developer plan just adds cloud tracing and Studio access.

### 3. Start LangGraph Server

```bash
./scripts/start_langgraph_server.sh
```

Or manually:
```bash
langgraph dev --port 2024 --host 0.0.0.0
```

The server will:
- Read `langgraph.json` configuration
- Expose workflow at `http://localhost:2024`
- Support checkpointing via PostgreSQL

### 4. Connect Agent Chat UI

**Option A: Use LangSmith Studio (FREE Developer Plan)**
1. Sign up for free Developer plan at https://smith.langchain.com
2. Get your API key from https://smith.langchain.com/settings
3. Add `LANGSMITH_API_KEY` to your `.env`
4. Visit https://smith.langchain.com/studio/?baseUrl=http://localhost:2024
5. Create a workspace (free with Developer plan)
6. Connect to workflow:
   - **Graph ID**: `agentic_workflow`
   - **Server URL**: `http://localhost:2024`

**Option B: Deploy Local UI**
```bash
npx create-agent-chat-app --project-name cti-agent-chat
cd cti-agent-chat
pnpm install
pnpm dev
```

## Usage

### From Operational UI

1. Navigate to **Workflow > Executions** tab
2. Find an execution (running, completed, or failed)
3. Click **🔍 Debug** button
4. Agent Chat UI opens with execution context

### Direct Access

1. Start LangGraph server
2. Open Agent Chat UI
3. Connect with:
   - Graph: `agentic_workflow`
   - Server: `http://localhost:2024`
   - Thread: `workflow_exec_{execution_id}` (for existing execution)

### Creating New Executions

In Agent Chat UI:
1. Start a new conversation
2. Send initial state (or let workflow initialize):
   ```json
   {
     "article_id": 123,
     "min_hunt_score": 97.0,
     "ranking_threshold": 6.0,
     "similarity_threshold": 0.5
   }
   ```
3. Workflow executes step-by-step
4. Inspect state at each step

## Workflow Steps

The workflow executes these steps:

1. **junk_filter**: Remove non-huntable content
2. **rank_article**: LLM scores article (1-10)
3. **extract_agent**: Extract huntable behaviors
4. **generate_sigma**: Generate SIGMA rules
5. **similarity_search**: Compare against existing rules
6. **promote_to_queue**: Queue low-similarity rules

## Debugging Features

### State Inspection

- View state at any step
- See intermediate results
- Check error logs

### Time-Travel

- Navigate through execution history
- Fork from any point
- Re-run with modified state

### Tool Visualization

- See LLM API calls
- View prompt inputs/outputs
- Inspect tool results

### Human-in-the-Loop

- Approve/reject at decision points
- Modify state before continuing
- Interrupt for manual review

## API Endpoints

### Get Debug Info
```
GET /api/workflow/executions/{execution_id}/debug-info
```

Returns:
```json
{
  "execution_id": 123,
  "article_id": 456,
  "langgraph_server_url": "http://localhost:2024",
  "agent_chat_url": "https://chat.langchain.com/?graph=agentic_workflow&thread=workflow_exec_123&server=http://localhost:2024",
  "thread_id": "workflow_exec_123",
  "graph_id": "agentic_workflow"
}
```

## Troubleshooting

### Server Won't Start

- Check `langgraph.json` exists and is valid
- Verify PostgreSQL connection for checkpointing
- Check port 2024 is available

### Agent Chat UI Can't Connect

- Verify LangGraph server is running
- Check `LANGGRAPH_SERVER_URL` matches server URL
- Ensure CORS is configured (if using different domain)

### Checkpointing Errors

- Verify PostgreSQL connection string
- Check database has checkpoint tables
- Try MemorySaver as fallback (not persistent)

### State Not Persisting

- Check PostgreSQL checkpoint backend is initialized
- Verify `DATABASE_URL` includes PostgreSQL connection
- Check logs for checkpoint errors

## Best Practices

1. **Separate Concerns**
   - Use operational UI for management
   - Use Agent Chat UI for debugging

2. **Thread Management**
   - One thread per execution
   - Use execution ID as thread ID

3. **State Hygiene**
   - Don't store large blobs in state
   - Use database for persistent data
   - State should be checkpointable

4. **Error Recovery**
   - Failed executions can be debugged in Agent Chat UI
   - Use time-travel to replay from failure point
   - Modify state and retry

## References

- [LangGraph Documentation](https://docs.langchain.com/langgraph)
- [Agent Chat UI Documentation](https://docs.langchain.com/oss/python/langchain/ui)
- [LangGraph Checkpointing](https://langchain-ai.github.io/langgraph/how-tos/persistence/)

