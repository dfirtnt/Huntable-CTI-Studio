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

Heads-up: `expected_items` is frequently NULL on historical rows even where
`expected_count` is set — many past eval runs wrote only the count. Populating it to
match `ground_truth.json` is a no-content **alignment**, not a divergence; do it with
operator approval and don't report it as drift.

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
- Read/write with `.venv/bin/python` + openpyxl (not in the base venv — install if
  the import fails: `.venv/bin/pip install openpyxl`). To READ, copy to /tmp first if
  the OneDrive path misbehaves; load with `data_only=True` for verification
  reads, and WITHOUT `data_only` for edit-in-place (preserves formulas).
- See `hazards.md` before any write — Excel must be closed.

## Write formats (apply only operator-approved deltas)

- **xlsx**: `Count` = len(items); `GroundTruth` =
  `json.dumps(items, ensure_ascii=False)` — a FLAT JSON array of strings.
  Back up first: `shutil.copy2(src, src + '.bak-YYYY-MM-DD-<scope>')`.
- **yaml**: `yaml.safe_dump(data, sort_keys=False, allow_unicode=True)` reflows the
  ENTIRE file. For a single-value change or for appends, prefer a **surgical text
  edit** anchored on the `<subagent_key>:` line (the URL may appear under several
  subagents — anchor on the section, not the bare URL) to keep the diff to the lines
  you changed.
- **gt.json / articles.json**: ⚠️ **The existing fixtures are NOT format-uniform —
  three serializations are live across agents** (verified 2026-06-12):
  - `indent=2, ensure_ascii=False, + '\n'` — cmdline, process_lineage,
    registry_artifacts, hunt_queries/gt
  - `indent=2, ensure_ascii=True, NO trailing newline` — scheduled_tasks/articles,
    windows_services/articles, hunt_queries/articles
  - `indent=2, ensure_ascii=False, NO trailing newline` — scheduled_tasks/gt,
    windows_services/gt

  So **DETECT the target file's exact serialization first** (probe indent /
  ensure_ascii / trailing-newline against the raw bytes) and match it, OR surgically
  text-edit just the changed value / append. Blindly re-dumping with the wrong
  `ensure_ascii` re-encodes every `content` field (`\uXXXX` ⇄ literal UTF-8) — a
  massive spurious diff that collides with parallel sessions. `ensure_ascii=False +
  '\n'` is the preferred shape for NEW files only; never impose it on an existing
  file mid-audit.
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

  Some eval URLs have NO row yet — the eval set grew after the last eval run (seen
  for ProcTree arts 8 & 9, 2026-06-12). For those, `INSERT` instead of `UPDATE`:

  ```sql
  INSERT INTO subagent_evaluations
    (subagent_name, article_url, expected_count, expected_items, status,
     workflow_config_version, created_at)
  VALUES
    ('<subagent_key>', '<url>', <N>, '<json>'::jsonb, 'completed',
     <active_config_version>, NOW());
  ```

  (`status='completed'` matches existing fixture rows; `<active_config_version>` =
  current active `agentic_workflow_config.version`.) Check existence per URL first;
  UPDATE where a row exists, INSERT where none does.

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
  (9 files). Each embeds `<AGENT>.Prompt.prompt` as a JSON-string copy of the seed
  dict. **The drift-guard test
  (`tests/config/test_subagent_traceability_contract.py::…parses_and_matches_source`)
  compares SEMANTICALLY** — `json.loads(embedded) == json.loads(seed_file)` — NOT
  byte-for-byte. So you don't need byte-identity; you need the embedded string to
  parse back to the seed dict. To keep the diff to one line per file, **detect the
  existing embedding's serialization and match it** rather than assuming: for
  ProcTreeExtract (2026-06-12) it was COMPACT
  `json.dumps(seed, separators=(',',':'))`, NOT the "default separators" form
  (which inserts `, ` / `: ` spaces, yields a longer string, and does not reproduce
  the existing embedding). Safest regeneration = surgical raw-text replace per
  preset: `old_escaped = json.dumps(old_inner)`, `new_escaped =
  json.dumps(new_inner)`, `raw.replace(old_escaped, new_escaped)` (assert it appears
  exactly once), leaving every other key byte-untouched. Verify after:
  `json.loads(preset['<AGENT>']['Prompt']['prompt']) == new_seed` for all 9.
