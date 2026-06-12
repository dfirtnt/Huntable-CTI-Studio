# Agent map, sink locations, queries, and write formats

## Agent resolution table

| AGENT (contract)      | subagent key        | xlsx HuntableType(s)  |
|-----------------------|---------------------|-----------------------|
| CmdlineExtract        | cmdline             | CmdLine               |
| ProcTreeExtract       | process_lineage     | ProcTree              |
| RegistryExtract       | registry_artifacts  | RegExtract            |
| ServicesExtract       | windows_services    | ServicesExtract       |
| ScheduledTasksExtract | scheduled_tasks     | SchedTask             |
| HuntQueriesExtract    | hunt_queries        | HuntRule, SigmaOutput |

## Spec docs (authoritative, in load order)

1. `docs/contracts/extractor-standard.md` — baseline for all extractors
2. `docs/contracts/<agent>-extract.md` — agent spec; wins conflicts
   (file names are kebab-case: `cmdline-extract.md`, `proctree-extract.md`,
   `registry-extract.md`, `services-extract.md`, `scheduled-tasks-extract.md`,
   `huntquery-extract.md`)
3. `docs/contracts/<agent>-extract-dropin.md` — portable mirror; consistency
   check only

## Repo fixtures

- `config/eval_articles.yaml` → `subagents.<subagent_key>` list of
  `{url, expected_count}` (Eval1)
- `config/eval_articles_data/<subagent_key>/articles.json` → list of
  `{url, title, content, expected_count}` (article text + Eval1 mirror)
- `config/eval_articles_data/<subagent_key>/ground_truth.json` → list of
  `{url, expected_items}` (Eval2). `expected_items: []` = intentional
  registered-but-uncurated placeholder.

## Database (fixture data only — the config row is out of audit scope)

Connection:

```bash
PASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
PGPASSWORD=$PASS psql -h localhost -p 5432 -U cti_user -d cti_scraper
```

Latest fixture row per URL (there are many historical rows — one per eval run):

```sql
WITH latest AS (
  SELECT DISTINCT ON (article_url) article_url, id, expected_count,
         expected_items, created_at, workflow_config_version
  FROM subagent_evaluations
  WHERE subagent_name = '<subagent_key>'
  ORDER BY article_url, created_at DESC
)
SELECT * FROM latest ORDER BY article_url;
```

Optional seed-drift FYI (Step 1.4 — report-only, never the rubric):

```sql
SELECT version, agent_prompts->'<AGENT>'
FROM agentic_workflow_config WHERE is_active = true;
```

## xlsx canonical sheet

Path:
`/Users/starlord/Library/CloudStorage/OneDrive-Personal/Andrew Documents/Documents/HuntableCTI-Europa-ExtractionEvals-7.0.0.xlsx`

- Sheet `articles_table`; filter rows where `HuntableType` matches the agent's
  type(s). Columns: Title, URL, Status, HuntableType, Count, Analysis,
  GroundTruth.
- Read/write with `.venv/bin/python` + openpyxl. To READ, copy to /tmp first if
  the OneDrive path misbehaves; load with `data_only=True` for verification
  reads, and WITHOUT `data_only` for edit-in-place (preserves formulas).
- See `hazards.md` before any write — Excel must be closed.

## Write formats (apply only operator-approved deltas)

- **xlsx**: `Count` = len(items); `GroundTruth` =
  `json.dumps(items, ensure_ascii=False)` — a FLAT JSON array of strings.
  Back up first: `shutil.copy2(src, src + '.bak-YYYY-MM-DD-<scope>')`.
- **yaml**: `yaml.safe_dump(data, sort_keys=False, allow_unicode=True)`
- **gt.json / articles.json**:
  `json.dumps(obj, indent=2, ensure_ascii=False) + '\n'`
- **DB**: `UPDATE` the latest row per URL only (preserve eval-run history):

  ```sql
  UPDATE subagent_evaluations
  SET expected_count = <N>, expected_items = '<json>'::jsonb
  WHERE id = (
    SELECT id FROM subagent_evaluations
    WHERE subagent_name = '<subagent_key>' AND article_url = '<url>'
    ORDER BY created_at DESC LIMIT 1
  );
  ```

After writing, re-verify every touched sink and print a cross-sink consistency
table (yaml = a.json = gt.json items-len = xlsx Count = xlsx GT-len = DB count =
DB items-len).

## Prompt-side propagation targets (Step 7.5 only, on operator request)

- Seed: `src/prompts/<AGENT>` (JSON dict; key sets vary by agent — usually some
  subset of {role, task, json_example, instructions}). Verify it loads via
  `from src.utils.default_agent_prompts import get_default_agent_prompts`.
- Live DB: `PUT http://localhost:8001/api/workflow/config/prompts` with
  `{agent_name, prompt (JSON-string), instructions, change_description}`.
  The endpoint locks the active row, bumps the config version, writes an
  AgentPromptVersionTable history row, and carries sibling agents forward.
  Never hand-write the config row with SQL.
- Quickstart presets: `config/presets/AgentConfigs/quickstart/Quickstart-*.json`
  (9 files). Each embeds `<AGENT>.Prompt.prompt` as a JSON-encoded copy of the
  seed: inner string via `json.dumps(seed)` (default separators), outer file via
  `json.dumps(obj, indent=2, ensure_ascii=False)` (+ trailing newline if the
  original had one) — this round-trips byte-identically, so the diff is one
  line per file.
