# LangGraph Agent Chat UI - Quick Start

## 🚀 5-Minute Setup

### 1. Install LangGraph CLI (if not already installed)
```bash
pip install langgraph-cli
```

### 2. Start LangGraph Server
```bash
./scripts/start_langgraph_server.sh
```

Server starts on `http://localhost:2024`

### 3. Optional: Set Up LangSmith (FREE Developer Plan)

**LangChain offers a FREE Developer plan with:**
- ✅ 1 free seat
- ✅ Access to LangSmith Studio
- ✅ 5k base traces/month included

**To get started:**
1. Sign up at https://smith.langchain.com (free Developer plan)
2. Get your API key from https://smith.langchain.com/settings
3. Add to `.env`: `LANGSMITH_API_KEY=your_key_here`
4. Restart langgraph-server: `docker-compose restart langgraph-server`

**Note:** Works perfectly without LangSmith! However, the **🔍 Debug** button opens LangFuse traces (post-execution viewing), not interactive step-into debugging. For step-into debugging, use LangSmith Studio or Local Agent Chat UI.

### 4. Open Agent Chat UI (Optional)

**Option A: Use LangSmith Studio (FREE)**
1. Visit https://smith.langchain.com/studio/?baseUrl=http://localhost:2024
2. Create a workspace (free with Developer plan)
3. Connect to your workflow:
   - **Graph ID**: `agentic_workflow`
   - **Server URL**: `http://localhost:2024`

**Option B: Use Local UI**
```bash
npx create-agent-chat-app --project-name cti-chat
cd cti-chat
pnpm install
pnpm dev
```

### 5. Debug from Operational UI

**Debug Button (🔍 Debug):**
1. Go to **Workflow > Executions** in your FastAPI UI
2. Click **🔍 Debug** on any execution
3. Opens LangFuse trace viewer (post-execution analysis)
   - **Note:** Traces only exist if execution ran with LangFuse tracing enabled
   - If trace not found, search for `session_id: workflow_exec_{execution_id}` in LangFuse UI

**For Step-Into Debugging:**
- **Option A:** Use LangSmith Studio (if `LANGSMITH_API_KEY` configured)
  - Manually visit: https://smith.langchain.com/studio/?baseUrl=http://localhost:2024
  - Connect with Graph ID: `agentic_workflow`, Thread: `workflow_exec_{execution_id}`
- **Option B:** Use Local Agent Chat UI (see Setup section)
  - Connect with Server: `http://localhost:2024`, Graph: `agentic_workflow`, Thread: `workflow_exec_{execution_id}`

## 📋 What You Get

✅ **Time-travel debugging** - Step through execution history  
✅ **State inspection** - View/modify state at any point  
✅ **Tool visualization** - See LLM calls and tool results  
✅ **Human-in-the-loop** - Approve/reject at decision points  

## 🔧 Configuration

Environment variables (`.env`):
```bash
# Required
LANGGRAPH_SERVER_URL=http://localhost:2024
LANGGRAPH_PORT=2024

# Optional: LangSmith (FREE Developer plan available)
# Sign up at https://smith.langchain.com for free API key
# Includes 5k traces/month - perfect for personal projects!
LANGSMITH_API_KEY=your_langsmith_api_key_here
```

## 🐛 Troubleshooting

**Server won't start?**
- Check `langgraph.json` exists
- Verify PostgreSQL connection
- Port 2024 available?

**Can't connect?**
- Verify server is running: `curl http://localhost:2024/health`
- Check CORS settings
- Verify graph ID: `agentic_workflow`

See full documentation: [LANGGRAPH_INTEGRATION.md](./LANGGRAPH_INTEGRATION.md)

