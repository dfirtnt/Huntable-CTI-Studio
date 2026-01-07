# Observables

Observables are the structured outputs of the Extract Agent. They represent the huntable behaviors that downstream Sigma generation and similarity matching consume.

## Types emitted
- `cmdline`: command-line strings with arguments
- `process_lineage`: parent/child process chains
- `registry_keys`: persistence and configuration keys
- `sigma_queries`: Sigma-like query fragments pulled directly from the article
- `event_ids`: Windows Event IDs and related log channels

## Data shape
`agentic_workflow_executions.extraction_result` stores merged observables and per-agent details:
```json
{
  "discrete_huntables_count": 4,
  "observables": [
    {"type": "cmdline", "value": "e.exe -d=\"E:\\\"", "source": "supervisor_aggregation"},
    {"type": "event_ids", "value": "Security 4688", "source": "supervisor_aggregation"}
  ],
  "subresults": {
    "cmdline": {"items": ["e.exe -d=\"E:\\\""], "count": 1, "raw": {"cmdline_items": ["..."], "qa_corrections": {}}},
    "event_ids": {"items": ["Security 4688"], "count": 1}
  },
  "content": "- e.exe -d=\"E:\\\"\n- Security 4688",
  "summary": {"source_url": "https://...", "platforms_detected": ["Windows"]}
}
```
`content` is a stitched, newline-delimited view of the observables; Sigma uses it when at least one huntable is present and the content length is sufficient.

## Where to view observables
- **API**: `GET /api/workflow/executions/{execution_id}` → `extraction_result.observables` and `subresults`.
- **Workflow page**: shows per-step status and observable counts.
- **Article page**: displays extraction results and huntable counts after a workflow completes.

## Refreshing observables
1. Ensure the article exists (via RSS ingestion or `POST /api/scrape-url`).
2. Trigger the workflow (`POST /api/workflow/articles/{article_id}/trigger`).
3. Wait for `status=completed`, then read `extraction_result` from the API or UI. Re-run the trigger if you update models/prompts or change input content.
