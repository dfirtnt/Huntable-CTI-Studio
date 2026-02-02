# Huntables

Huntables are repeatable, telemetry-rich observables extracted from CTI content (e.g. command lines, process chains, Sigma-style queries, EDR query patterns) that can drive detections. They are tracked at two levels:
- **Extraction results**: `discrete_huntables_count`, typed `observables`, and `subresults` are stored on each workflow execution.
- **Article metadata**: Regex-based `threat_hunting_score` and ML-based `ml_hunt_score` describe how “huntable” an article is before and after chunk analysis.

## What counts as a huntable
For the purposes of this application, "huntables" are distinct from the more industry standard term "observables" in that "huntables" are tailored to your workflow as you train the machine learning model used for junk filtering and as you tune your agent prompts. Out of the box in the Callisto release, huntables are:

- Structured process and command-line patterns (cmd.exe, powershell patterns, LOLBAS usage)
- Process lineage / parent-child chains with arguments
- EDR and Sigma-style detection queries
- Behavior patterns more than single IOCs (IPs/hashes are not scored as huntable by themselves)

## Scoring signals
- **Threat hunting score** (regex driven; see `../internals/scoring.md`)
  - Perfect discriminators such as `rundll32`, `msiexec`, `lsass.exe`, `.lnk`, `MZ`, `%WINDIR%` carry the most weight.
  - LOLBAS executables (`certutil.exe`, `schtasks.exe`, `wmic.exe`, etc.) and registry/Windows path patterns add supporting points.
  - Negative indicators (`what is`, `best practices`, marketing language) reduce the score.
- **ML hunt score** (chunk-driven; see `../ML_HUNT_SCORING.md`)
  - Articles are chunked (1,000 chars, 200 overlap) and each chunk is classified huntable/not.
  - Default metric: weighted average of confidences for huntable chunks, normalized to 0–100.

## Where huntables live
- **Article page**: Hunt scores are displayed alongside metadata; the “Send to Workflow” action runs extraction.
- **Workflow executions**: `extraction_result.observables` contains merged observables and per-type counts; `content` is the synthesized text Sigma consumes when huntables exist.
- **API**: `GET /api/workflow/executions/{id}` exposes `discrete_huntables_count`, per-agent `subresults`, and the merged observable list.

## Producing huntables
1. Ingest an article (RSS, scrape endpoint, or browser extension).
2. Trigger the workflow (`POST /api/workflow/articles/{article_id}/trigger` or from the article page).
3. Extract Agent sub-agents emit typed observables; the supervisor aggregates them and stores huntable counts.
4. Sigma generation uses the aggregated content when `discrete_huntables_count > 0` and the content length is sufficient.
