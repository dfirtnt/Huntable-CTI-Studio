# Known hazards and failure modes

Every item below was hit during a real audit (CmdlineExtract, 2026-06). Read
this file before Step 4 reporting and again before any Step 6 write.

## OneDrive xlsx: Excel autosave clobbers your writes

The canonical spreadsheet lives on OneDrive and is often open in Excel. Excel
holds its own in-memory copy; when it autosaves (or OneDrive syncs Excel's
buffer), it overwrites whatever you wrote to disk — last-writer-wins, silently.
During the cmdline audit this erased two separate rounds of corrected values.

- Before any xlsx write, ask the operator to CLOSE the workbook in Excel and
  confirm.
- Back up first: `shutil.copy2(src, src + '.bak-YYYY-MM-DD-<scope>')`.
- After writing, copy the file to /tmp and re-verify with
  `openpyxl.load_workbook(..., data_only=True)`.
- The other four sinks (yaml, articles.json, ground_truth.json, DB) are never
  at risk — Excel doesn't touch them. If the xlsx later looks reverted, check
  those four before assuming data loss.

## xlsx GroundTruth format: flat array, not extractor output

Correct cell value: a FLAT JSON array of strings —
`["cmd one", "cmd two"]`, written via `json.dumps(items, ensure_ascii=False)`.

Observed corruptions (report; fix only the rows in your audit scope unless the
operator approves a wider sweep):

- Extractor-output object shape: `{"cmdline_items": [{"value": ..., ...}]}` or
  `{"commands": [...]}` — someone pasted raw model output.
- Schema-key fragments: a cell containing literally `["cmdline_items","count"]`.
- Raw unquoted string (not JSON at all).
- `Count` out of sync with `len(GroundTruth)`.
- Duplicate rows for the same URL (update all, flag for dedup).
- Rows for URLs not in the fixture (other audits/experiments — leave alone).

## Normalized duplicates

CTI articles often state the same command/artifact twice in different
normalizations: observed-telemetry form (`whoami /groups`) vs analyst-cleaned
form (`whoami.exe /groups`), differing wrappers, casing, or paths. Spec dedup
rules typically treat variants as DISTINCT entries, which is correct for
literal extraction — but blind agents and hand curation frequently disagree on
which form(s) belong in GT. Always flag variant pairs explicitly in the Step 5
report instead of silently adding both, and let the operator rule. Watch
especially for an item that equals an existing GT entry after wrapper
stripping — adding it creates a duplicate the extractor can never satisfy.

## Anchoring

Never open ground_truth.json, the xlsx, or DB expected values before finishing
blind extraction. Two prior audits of the same articles diverged because the
model read the recorded counts first and rationalized toward them.

## Seed-rule leak into the rubric / fan-out prompt

The rubric is the DOC (`docs/contracts/<agent>-extract.md`), never the seed
(`src/prompts/<AGENT>`). The seed routinely carries extra rules the doc does not —
agent-specific SKIPs added during prompt experimentation. During the ProcTree audit
(2026-06-12) a seed-only rule (a blanket `schtasks.exe`-parent SKIP that exists in
the seed but NOT the contract, and in fact contradicts it) was pasted from memory
into the per-article fan-out prompt, silently contaminating the "operative rubric."
The operator caught it; it forced a kill + relaunch of the extraction workflow.

Guardrails:

- Build the fan-out prompt's rule list ONLY from the merged doc spec written to
  /tmp (Step 3). Do not paste rules from the seed or from memory.
- After drafting the prompt, diff its rules against the doc. Any rule present in the
  prompt but absent from the doc is a leak — remove it (or, if the operator wants it,
  ratify it as a SPEC CHANGE in the doc FIRST, then it is legitimately the rubric).
- If a leak is found after extraction has started, kill the run and relaunch — do not
  try to mentally subtract the leaked rule from already-produced results.

## Curated-truth DB rows must not stamp config provenance

When a fixture correction expands an eval set (new articles) or replaces stale
DB expected values, the operator may direct an INSERT/UPDATE into
`subagent_evaluations`. Those rows are **operator-curated truth**, not eval-run
results. They differ from eval-run rows by what's NULL:

|                              | eval-run row | curated-truth row |
|------------------------------|--------------|-------------------|
| `actual_count`, `score`,     | populated    | **NULL**          |
| `workflow_execution_id`,     |              |                   |
| `matched/missed/extra_count` |              |                   |
| `workflow_config_id`,        | populated    | **NULL**          |
| `workflow_config_version`    | (legit prov.) | (no prov. to claim) |

Stamping curated rows with the currently-active `workflow_config_id`/`_version`
out of habit creates **false provenance** — the row reads as "produced by an
eval run against config vX" when it was never run by any config. The next eval
reads `expected_count`/`expected_items` from the latest row per URL via
`DISTINCT ON ... ORDER BY created_at DESC`; nothing in that path needs the
config columns, so leaving them NULL is correct and honest.

Detection: a curated insert has `COUNT(actual_count) = 0` across its latest
rows. A real eval run has all of `actual_count`, `score`, and
`workflow_execution_id` populated. The first sign someone confused the two is
usually a `created_at` cluster of identical timestamps (curated batches) sharing
one `workflow_config_version` (the active one when the operator ran the audit).

## Placeholders are intentional

`expected_items: []` in ground_truth.json marks a registered-but-uncurated
article. Do not delete; do not treat as "GT says zero items". Populate only
with operator approval.

## Workflow fan-out quality

When fanning out per-article agents: pass the merged spec text via a /tmp file
(not inline duplication), use a strict StructuredOutput schema with an
`article_index` echo, require ASCII-only items, and state explicitly that long
articles get MORE care. Agents' self-reported `count` can disagree with
`len(items)` — trust the items list. Cross-check a sample of agent output
against the raw article text yourself; agents have mis-split items (dropped a
leading token) and missed valid items adjacent to corrupted text. For the
hardest articles (heavy obfuscation, corrupted blocks), do a first-person
read of the relevant regions rather than trusting any agent run.

## Spec-change propagation (Step 7.5)

The contract test `test_preset_prompt_parses_and_matches_source`
(tests/config/test_subagent_traceability_contract.py) asserts every quickstart
preset's embedded prompt equals the seed file. A seed edit without preset
regeneration fails CI and blocks /lg. Regenerate all 9 presets in the same
commit as the seed change, or in an immediately following mechanical commit.

The DB config row churns constantly (operator experimentation bumps the config
version daily). Pushing the seed to the DB via the PUT endpoint makes the rule
live *now*, but expect later drift — the doc and seed are the durable record,
and periodic re-syncs are normal.

## Score-comparability eras

Eval scores are comparable only within a spec era. A SPEC CHANGE creates a
discontinuity: GT before and after measures different rules. The era boundary
must be visible — CHANGELOG entry plus the git history of the contract doc and
ground_truth.json. Never let a spec change ride silently inside a "fixture
correction" commit.

## Test environment

Fixture-validation tests need env vars:

```bash
export APP_ENV=test
export POSTGRES_PASSWORD=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@localhost:5432/cti_scraper_test"
```

Relevant suites after fixture edits: `tests/quality/test_eval_articles_sync.py`,
`tests/unit/test_ground_truth_files.py`, `tests/unit/test_eval_set_size_counting.py`;
after spec/seed edits also `tests/config/test_subagent_traceability_contract.py`
and `tests/config/test_recent_prompt_changes.py`.
