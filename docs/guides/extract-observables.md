# Extract Observables

Run the Extract Agent on any article to produce huntable observables that downstream Sigma generation consumes.

## Prerequisites
- Stack is running (`./start.sh` and web reachable on `http://localhost:8001`)
- Article exists (from RSS collection, UI upload, or `POST /api/scrape-url`)

## 1) Get or create an article
Manual scrape example:
```bash
ARTICLE_ID=$(curl -s -X POST http://localhost:8001/api/scrape-url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-214a","force_scrape":true}' | jq -r '.article_id')
```

## 2) Trigger the workflow
```bash
EXECUTION_ID=$(curl -s -X POST "http://localhost:8001/api/workflow/articles/${ARTICLE_ID}/trigger" | jq -r '.execution_id')
```
If an execution is already running, the endpoint returns a 400 with the existing execution ID; wait for it to finish or clear the stuck run.

## 3) Monitor extraction
```bash
curl -s "http://localhost:8001/api/workflow/executions?article_id=${ARTICLE_ID}" \
  | jq '.executions[0] | {id,status,extraction_counts}'
```
When `status` is `completed`, pull the full extraction payload:
```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{discrete_huntables:.extraction_result.discrete_huntables_count, observables:.extraction_result.observables, subresults:.extraction_result.subresults}'
```

## 4) Where results show up
- **API**: `GET /api/workflow/executions/{execution_id}` exposes merged observables, per-agent `subresults`, and synthesized `content`.
- **Article page**: `http://localhost:8001/articles/${ARTICLE_ID}` renders extraction results after completion.
- **Workflow page**: lists executions with observable counts per agent.

## Re-running extraction
Re-trigger the workflow to apply new prompts or models. The latest execution retains its own `extraction_result`; prior executions remain in the history table for auditing.

## Cmdline Attention Preprocessor
For command-line extraction, the **CmdlineExtract** sub-agent can use an optional attention preprocessor that surfaces LOLBAS-aligned snippets earlier in the LLM prompt. Enable or disable it in Workflow Config → Cmdline Extract agent. See [Cmdline Attention Preprocessor](../features/CMDLINE_ATTENTION_PREPROCESSOR.md).
