# Observables

Observables are the **structured extraction output** of the Extract Agent: typed items (command lines, process lineage, detection queries) that downstream Sigma generation and similarity matching consume. They are stored per workflow execution in `extraction_result`.

**Relation to Huntables:** Huntables are enterprise-specific, telemetry-rich content that can drive detections; they are tailored to your org and workflow (ML junk filtering, agent prompts). Observables are the structured representation of that content — the `observables` array and `subresults` in `extraction_result`. See [Huntables](huntables.md) for the full definition and article-level hunt scores.

## Types emitted (active sub-agents)

- `cmdline`: command-line strings with arguments (CmdlineExtract)
- `process_lineage`: parent/child process chains (ProcTreeExtract)
- `hunt_queries`: EDR and Sigma-style detection query fragments (HuntQueriesExtract)
- `registry_artifacts`: Windows registry artifacts — persistence keys, config changes, defense evasion (RegistryExtract)
- `windows_services`: Windows service artifacts — service name, binary path, command line, start type (ServicesExtract)
- `scheduled_tasks`: Windows scheduled task artifacts — task name, action, trigger, run-as user (ScheduledTasksExtract)

*Deprecated (no longer extracted): `event_ids` — EventCodeExtract has been removed. An earlier agent "RegExtract" was also removed; the current RegistryExtract is active.*

## Data shape

`agentic_workflow_executions.extraction_result` stores merged observables and per-agent details:

```json
{
  "discrete_huntables_count": 2,
  "observables": [
    {"type": "cmdline", "value": "e.exe -d=\"E:\\\"", "source": "supervisor_aggregation"},
    {"type": "hunt_queries", "value": "DeviceProcessEvents | where ...", "source": "supervisor_aggregation"}
  ],
  "subresults": {
    "cmdline": {"items": ["e.exe -d=\"E:\\\""], "count": 1, "raw": {"cmdline_items": ["..."], "qa_corrections": {}}},
    "hunt_queries": {"items": ["DeviceProcessEvents | where ..."], "count": 1}
  },
  "content": "- e.exe -d=\"E:\\\"\n- DeviceProcessEvents | where ...",
  "summary": {"count": 2, "source_url": "https://...", "platforms_detected": ["Windows"]}
}
```

- Each entry in `observables` has `type` (matching a `subresults` key), `value`, and `source`; dict items may include `original_data`.
- `content` is a stitched, newline-delimited view of the observables; Sigma uses it when `discrete_huntables_count > 0` and content length is sufficient.

## Where to view observables

- **API**: `GET /api/workflow/executions/{execution_id}` → `extraction_result.observables` and `subresults`.
- **Workflow page**: per-step status and observable counts.
- **Article page**: extraction results and huntable counts after a workflow completes.

## Refreshing observables

1. Ensure the article exists (RSS ingestion or `POST /api/scrape-url`).
2. Trigger the workflow (`POST /api/workflow/articles/{article_id}/trigger`).
3. Wait for `status=completed`, then read `extraction_result` from the API or UI. Re-run the trigger if you change models, prompts, or input content.

_Last updated: 2026-05-01_
