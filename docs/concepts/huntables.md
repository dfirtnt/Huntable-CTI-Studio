# Huntables.

## What is a “Huntable”?

**Huntables** are enterprise-specific, telemetry-rich observables extracted from CTI content—think command lines, process chains, registry paths, services, scheduled tasks, etc.—that can drive detections.

For the purposes of this application, “huntables” are distinct from the more industry-standard term “observables” in that huntables are **tailored to your organization and workflow**. As you train the machine learning model used for junk filtering and tune your agent prompts and parameters, huntables become more tailored to your needs.

Out of the box, the application supports these:

- **Command lines** — Literal command lines observable in an EDR, EventCode 4688 (security.evtx if configured), and/or EventCode 1 (Sysmon.evtx).
- **Process trees** — Lineage information such as parent–child relationships.
- **Hunt queries** — EDR, Splunk, SIEM, or SIGMA queries found in intel articles.

In the workflow, these are emitted by the Extract Agent sub-agents as typed **observables** (`cmdline`, `process_lineage`, `hunt_queries`) and stored in `extraction_result`. See [Observables](observables.md) for the extraction schema and API.

**Where huntables are tracked:** Article metadata holds regex-based `threat_hunting_score` and ML-based `ml_hunt_score` (how “huntable” an article is); each workflow execution holds `discrete_huntables_count` and the observables in `extraction_result`.

## Scoring signals

- **Threat hunting score** (regex-driven; see [Scoring](../internals/scoring.md))
  - Perfect discriminators: `rundll32`, `msiexec`, `lsass.exe`, `.lnk`, `MZ`, `%WINDIR%`.
  - LOLBAS executables and registry/Windows path patterns add supporting points.
  - Negative indicators (e.g. “what is”, “best practices”, marketing) reduce the score.
- **ML hunt score** (chunk-driven; see [ML Hunt Scoring](../ML_HUNT_SCORING.md))
  - Articles are chunked (1,000 chars, 200 overlap); each chunk is classified huntable/not.
  - Default metric: weighted average of confidences for huntable chunks, normalized to 0–100.

## Where huntables appear

- **Article page**: Hunt scores (regex + ML) and “Send to Workflow”; after a run, extraction results and huntable counts.
- **Workflow executions**: `extraction_result.observables`, `discrete_huntables_count`, and `content` (used by Sigma when huntables exist).
- **API**: `GET /api/workflow/executions/{id}` → `extraction_result` with `discrete_huntables_count`, `subresults`, and merged `observables`.

## Producing huntables

1. Ingest an article (RSS, scrape, or browser extension).
2. Trigger the workflow (`POST /api/workflow/articles/{article_id}/trigger` or “Send to Workflow” on the article page).
3. Extract Agent sub-agents emit typed observables; the supervisor aggregates them into `observables` and sets `discrete_huntables_count`.
4. Sigma generation uses the aggregated `content` when `discrete_huntables_count > 0` and content length is sufficient.
