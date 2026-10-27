# First Workflow

Run the full agentic pipeline against a real CTI article: source-Sigma import -> Platform Detection -> junk filter -> ranking -> extraction -> Sigma generation -> similarity search.

**Prerequisites**: Stack running via `./start.sh` (see [Installation](installation.md)).

## 0) Load a quickstart preset (recommended for first run)

Enable and test a provider in **Settings -> Agentic Workflow Configuration** first. API providers need a usable key; Codex needs its managed login; LM Studio needs its server running with the exact model loaded. A preset supplies workflow settings and prompts, not credentials or global provider switches.

On **Workflow -> Config**, open the config actions menu and choose **Import Preset** (or **Import Preset from file** in the preset modal). Pick a matching preset:

- **Anthropic**: `config/presets/AgentConfigs/quickstart/Quickstart-anthropic-sonnet-4-6.json`
- **OpenAI API**: `config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-4.1-mini.json`
- **Codex subscription**: `config/presets/AgentConfigs/quickstart/Quickstart-codex-gpt-6-luna.json`, if your login lists `gpt-6-luna`
- **LM Studio (local)**: `config/presets/AgentConfigs/quickstart/Quickstart-LMStudio-Qwen3.json`, which assigns `qwen/qwen3-8b`

Import replaces the active workflow configuration. All 14 quickstart presets disable ranking, enable all seven extractors, and store Windows as the platform selection. Review those settings and thresholds after import; enable ranking if you want the ranking stage described below to run. Use **Export Preset** before import to keep a file copy of your current configuration.

See [Configuration -> Workflow Presets](configuration.md#workflow-presets) for the full list, exact model IDs, and shared thresholds.

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

If an execution is already running for the article, the API returns an error. Wait for it to finish or clear the stuck run before retrying. Note that ingestion can also start a workflow automatically when an article's RegexHunt score exceeds the auto-trigger threshold (default 100, above the maximum possible score, so auto-trigger is off until you lower it in Settings → Workflow), so a run may already exist before you trigger one manually if the threshold has been lowered.

The same threshold gates manual triggers: if the API replies that the article's RegexHunt score is not above the auto-trigger threshold, re-run with `?force=true`:

```bash
TRIGGER=$(curl -s -X POST "http://localhost:8001/api/workflow/articles/${ARTICLE_ID}/trigger?force=true")
```

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

You can also view results at `http://localhost:8001/articles/${ARTICLE_ID}`. The "Reprocess" button mirrors the API trigger and the page surfaces all extraction outputs.

## 4) Review Sigma Rules

The workflow writes validated Sigma rules to the execution record:

```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, sigma_rules: .sigma_rules}'
```

In the UI, open `http://localhost:8001/workflow#executions` and click **View** on the row matching `${EXECUTION_ID}` to see the validated Sigma YAML, logs, and similarity matches. (The article page at `/articles/${ARTICLE_ID}` surfaces the extracted observables but not the Sigma rules.)

## What Happens Under the Hood

The agentic workflow runs these stages in order:

**Pre-pass: Source Sigma Import** scans `articles.content` directly for complete publisher-authored Sigma, preserves the exact YAML and provenance, and records whether destination-repository policy permits delivery. This step does not call an LLM and does not route source rules through generation.

1. **Platform Detection**: classifies the article as Windows/Linux/macOS/cross-platform using the deterministic entity/keyword registry (with an LLM adjudicator for low-confidence cases). Since v7.5.0 this is a router, not a gate: non-Windows articles are not terminated; instead, Windows-only extractors (RegistryExtract, ServicesExtract, ScheduledTasksExtract) are skipped with structured reason records, and Linux evidence still generates Sigma.
2. **Junk Filter**: ML classifier + hunt score keywords determine if the article has actionable threat content. Low-scoring articles terminate early with reason `no_huntable_content`.
3. **LLM Ranking**: LLM scores the article for relevance and huntability. Articles below the ranking threshold terminate early with reason `rank_below_threshold`.
4. **Sub-agent Extraction**: sequential LLM agents extract observables (command lines, process trees, hunt queries, registry artifacts, Windows services, scheduled tasks, network indicators).
5. **Aggregation**: code in the extract step merges and deduplicates sub-agent outputs.
6. **Sigma Generation**: generates detection rules from the extracted observables.
7. **Similarity Search + Queue Promotion**: new rules are scored against indexed SigmaHQ rules; novel rules are promoted to the Sigma review queue.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `execution_id` is null | Article already has a running execution | Wait or check `/api/workflow/executions?article_id=X` |
| Trigger refused: score not above threshold | Article's RegexHunt score <= auto-trigger threshold | Re-run the trigger with `?force=true`, or lower the threshold in Settings → Workflow |
| Status stuck on `running` | Worker not processing tasks | Check `docker compose logs workflow_worker` |
| Empty extraction results | Article filtered as non-huntable | Check `termination_reason` in execution record |
| No Sigma rules generated | Article had no extractable observables | Review extraction_result for empty observables |

_Last updated: 2026-09-24_
_Last reviewed: 2026-09-01_
