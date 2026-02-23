# First Workflow

Run the full agentic pipeline against a real CTI article: OS detection → content filtering → ranking → extraction → Sigma generation → similarity search.

**Prerequisites**: Stack running via `./start.sh` (see [Installation](installation.md)).

## 0) Load a baseline preset (recommended for first run)

If you haven’t configured the workflow yet, load a preset so all LLM agents have prompts and models set. On the **Workflow** page, use **Import from file** and pick one of:

- **Anthropic** — `config/presets/AgentConfigs/anthropic-sonnet-4.5.json` or `config/presets/AgentConfigs/quickstart/Quickstart-anthropic-sonnet-4-6.json`
- **OpenAI / ChatGPT** — `config/presets/AgentConfigs/chatgpt-4o-mini.json` or `config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-4.1-mini.json`
- **LM Studio (local)** — `config/presets/AgentConfigs/lmstudio-qwen2.5-8b.json` or `config/presets/AgentConfigs/quickstart/Quickstart-LMStudio-Qwen3.json`

See [Configuration → Workflow baseline presets](configuration.md#workflow-baseline-presets-getting-started) for details.

## 1) Ingest a CTI Article

Use the manual scrape endpoint to pull a real article and capture its ID:

```bash
ARTICLE_ID=$(curl -s -X POST http://localhost:8001/api/scrape-url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-214a","force_scrape":true}' | jq -r '.article_id')
echo "Article ID: ${ARTICLE_ID}"
```

## 2) Trigger the Agentic Workflow

```bash
TRIGGER=$(curl -s -X POST "http://localhost:8001/api/workflow/articles/${ARTICLE_ID}/trigger")
EXECUTION_ID=$(echo "$TRIGGER" | jq -r '.execution_id')
echo "Execution ID: ${EXECUTION_ID}"
```

If an execution is already running for the article, the API returns an error. Wait for it to finish or clear the stuck run before retrying.

## 3) Monitor Execution

Watch status and extraction counts:

```bash
curl -s "http://localhost:8001/api/workflow/executions?article_id=${ARTICLE_ID}" \
  | jq '.executions[0] | {id, status, extraction_counts}'
```

When `status` is `completed`, pull the full payload:

```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, discrete_huntables: .extraction_result.discrete_huntables_count, observables: .extraction_result.observables}'
```

You can also view results at `http://localhost:8001/articles/${ARTICLE_ID}` — the "Send to Workflow" button mirrors the API trigger and the page surfaces all extraction outputs.

## 4) Review Sigma Rules

The workflow writes validated Sigma rules to the execution record:

```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, sigma_rules: .sigma_rules}'
```

In the UI, open `http://localhost:8001/articles/${ARTICLE_ID}#sigma` to jump to the Sigma section. Logs and similarity matches are also surfaced on the Workflow page.

## What Happens Under the Hood

The agentic workflow runs these stages in order:

1. **OS Detection** — classifies the article as Windows/Linux/macOS/cross-platform. Non-Windows articles terminate early with reason `non_windows_os_detected`.
2. **Content Filtering** — ML classifier + hunt score keywords determine if the article has actionable threat content.
3. **Chunking** — long articles are split into context-window-sized chunks for LLM processing.
4. **Sub-agent Extraction** — parallel LLM agents extract observables (IPs, domains, hashes, command lines, process trees, hunt queries).
5. **Supervisor Aggregation** — a supervisor agent merges and deduplicates sub-agent outputs.
6. **Sigma Generation** — generates detection rules from extracted observables, then runs similarity search against 5,247+ indexed SigmaHQ rules.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `execution_id` is null | Article already has a running execution | Wait or check `/api/workflow/executions?article_id=X` |
| Status stuck on `running` | Worker not processing tasks | Check `docker-compose logs workflow_worker` |
| Empty extraction results | Article filtered as non-huntable | Check `termination_reason` in execution record |
| No Sigma rules generated | Article had no extractable observables | Review extraction_result for empty observables |
