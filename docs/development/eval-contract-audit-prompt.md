# Eval Contract Audit Prompt (one run per extractor agent)

Reusable prompt for independently re-deriving the eval **expected count (Eval1)**
and **ground-truth extraction (Eval2)** for every eval article of a single
extractor agent, strictly from that agent's own contract — then comparing the
findings against the values recorded in the **spreadsheet** and the **database**.

## How to use

1. Copy everything in the fenced block below into a fresh Claude session opened
   at the repo root.
2. Replace `<<AGENT>>` on the first line with exactly one agent name from the
   mapping table (e.g. `CmdlineExtract`). Run **one agent per session** so the
   contract stays loaded and the article-by-article discipline holds.
3. Claude performs an independent extraction, prints a comparison report, and
   stops to ask before writing anything.

Why one agent per session and one article at a time: the recorded counts are
*anchors*. If the model reads them before doing its own extraction, it
rationalizes toward them (this is exactly how two prior model audits diverged
on the same articles). The prompt enforces extract-first, compare-second.

---

```
AGENT: <<AGENT>>

You are auditing the eval fixtures for ONE extractor subagent in the Huntable
CTI Studio repo (run from repo root). Work strictly and literally. Do NOT write
to any file, spreadsheet, or database until I explicitly approve at the end.

═══════════════════════════════════════════════════════════════════════════
STEP 0 — RESOLVE THE AGENT AND ITS SOURCES
═══════════════════════════════════════════════════════════════════════════
Map the AGENT above to its identifiers using this table:

  AGENT (contract)        subagent key        xlsx HuntableType(s)
  ----------------------  ------------------  ----------------------
  CmdlineExtract          cmdline             CmdLine
  ProcTreeExtract         process_lineage     ProcTree
  RegistryExtract         registry_artifacts  RegExtract
  ServicesExtract         windows_services    ServicesExtract
  ScheduledTasksExtract   scheduled_tasks     SchedTask
  HuntQueriesExtract      hunt_queries        HuntRule, SigmaOutput

If AGENT is not in this table, STOP and tell me.

═══════════════════════════════════════════════════════════════════════════
STEP 1 — COLLECT AND READ THE CONTRACT (authoritative first)
═══════════════════════════════════════════════════════════════════════════
The LIVE contract used at runtime lives in the DATABASE (workflow config
`agent_prompts`), NOT the file on disk. The file is only a seed/fallback.

a) Try the DB copy first. Find the active workflow config and pull this agent's
   prompt. Use the MCP tool `mcp__huntable-cti-studio__execute_sql` if available,
   otherwise psql:
     PASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
     PGPASSWORD=$PASS psql -h localhost -p 5432 -U cti_user -d cti_scraper
   The prompt JSON is in the workflow config row's `agent_prompts` field keyed by
   the AGENT name. (Schema may vary; inspect with `\d` and the
   /api/workflow/config/prompts endpoints if needed.)

b) If no DB prompt exists for this agent, read the seed file:
     src/prompts/<AGENT>            (e.g. src/prompts/CmdlineExtract)
   It is a JSON object with keys: role, task, json_example, instructions.

c) Read the WHOLE contract. Extract the operative rubric into a short checklist
   you will apply verbatim to every article: positive scope, negative scope,
   count/dedup semantics, wrapper/normalization rules, fail-closed threshold,
   and the output schema. Print this checklist back to me before proceeding so I
   can see the rubric you are about to enforce.

State plainly which source you used (DB vs seed file) and the config version if
from the DB.

═══════════════════════════════════════════════════════════════════════════
STEP 2 — ENUMERATE THIS AGENT'S EVAL ARTICLES
═══════════════════════════════════════════════════════════════════════════
The article set + text live on disk (URL-keyed, survives DB rehydration):
  config/eval_articles_data/<subagent>/articles.json    (url, title, content)

Build the list of (url, title) for this subagent from articles.json. This is the
canonical work list. Count them and tell me how many you will process.

Do NOT open the recorded expected values yet (see Step 4). The point is to
extract blind.

═══════════════════════════════════════════════════════════════════════════
STEP 3 — INDEPENDENT EXTRACTION, ONE ARTICLE AT A TIME
═══════════════════════════════════════════════════════════════════════════
For EACH article, in order, treating each in isolation:

  1. Read ONLY that article's `content` field. Treat it as plain text exactly as
     the contract's INPUT CONTRACT specifies (no HTML/markdown interpretation,
     no outside knowledge, no URL fetching).
  2. Apply the Step-1 checklist literally. Walk the verification checklist for
     every candidate. Fail closed when in doubt (precision over recall).
  3. Record:
       • Eval1 — expected_count: the integer count after the contract's
         dedup/count semantics.
       • Eval2 — ground_truth: the exact list of extracted item strings
         (verbatim, in the contract's `value`/primary-field form), which is the
         "expected_items" list. len(ground_truth) MUST equal expected_count.
  4. Note any judgment calls (dedup collapses, wrapper stripping, prose-embedded
     commands, HTML line-collapse, URL-only vs inline rule, etc.) in one line.

Do not batch, summarize, or shortcut. If an article is long, that is exactly the
case where shortcuts cause errors — slow down.

Keep your per-article results in memory; do not write them anywhere yet.

═══════════════════════════════════════════════════════════════════════════
STEP 4 — LOAD THE RECORDED VALUES (only now)
═══════════════════════════════════════════════════════════════════════════
Now read what is currently recorded, from all sinks, for comparison:

  A) Spreadsheet (xlsx canonical):
     /Users/starlord/Library/CloudStorage/OneDrive-Personal/Andrew Documents/Documents/HuntableCTI-Europa-ExtractionEvals-7.0.0.xlsx
     Sheet `articles_table`. Columns: Title, URL, Status, HuntableType, Count,
     Analysis, GroundTruth, ... Filter rows where HuntableType matches this
     agent's xlsx type(s). `Count` = Eval1. `GroundTruth` = Eval2 (a JSON array
     of strings, same shape as expected_items). Read with the repo venv:
       .venv/bin/python  (openpyxl is installed)

  B) Database (`subagent_evaluations` table):
       PGPASSWORD=$PASS psql -h localhost -p 5432 -U cti_user -d cti_scraper
     Columns of interest: subagent_name, article_url, article_id,
     expected_count (Eval1), expected_items (jsonb, Eval2).
     NOTE: there are many historical rows per (subagent, url) — one per eval run.
     For the comparison use the most recent / current row per url (or report the
     distinct recorded values if they disagree across rows). Filter
     subagent_name = '<subagent>'.

  C) (Context only) On-disk fixtures, for completeness:
       config/eval_articles.yaml                              -> expected_count (Eval1)
       config/eval_articles_data/<subagent>/articles.json     -> expected_count (Eval1 mirror)
       config/eval_articles_data/<subagent>/ground_truth.json -> expected_items (Eval2)

═══════════════════════════════════════════════════════════════════════════
STEP 5 — REPORT (do not modify anything)
═══════════════════════════════════════════════════════════════════════════
Print a per-article comparison. For each article show:

  url (short) | my_count | xlsx Count | DB expected_count | yaml | agree?

Then a second table for Eval2 ground-truth item-list comparison:

  url (short) | my_items | xlsx GT len | DB items len | data-file len | item-set agree?

For every divergence (Eval1 or Eval2), give a 1–2 line explanation of WHY your
independent reading differs, citing the specific contract rule. Where ground
truth lists differ, show the specific items added/removed (set difference), not
just the counts — a matching count with different items is still a divergence.

Flag any item that is a genuine judgment call as `REVIEW` so a human can adjudicate.

Finish with a summary: N articles, X Eval1 divergences, Y Eval2 divergences,
Z REVIEW items.

═══════════════════════════════════════════════════════════════════════════
STEP 6 — ASK BEFORE WRITING
═══════════════════════════════════════════════════════════════════════════
STOP. Ask me whether to apply your findings, and to WHICH sinks. Offer these
options explicitly and wait for my answer:
  (1) xlsx  Count + GroundTruth columns
  (2) config/eval_articles.yaml  (Eval1)
  (3) config/eval_articles_data/<subagent>/articles.json + ground_truth.json
      (Eval1 mirror + Eval2)
  (4) DB subagent_evaluations rows (Eval1 + Eval2)
  (5) some subset / only the non-REVIEW items / none

Do not write anything until I choose. When I approve, apply only the approved
changes, keep ASCII-only item strings, keep ground_truth.json `expected_items`
length equal to expected_count, and report exactly what you changed in each sink.
Remember `config/eval_articles_data/*/ground_truth.json` entries with an empty
`expected_items: []` are intentional "registered-but-uncurated" placeholders —
do not delete them; populate or leave as-is per my instruction.
```

---

## Source-of-truth reference (for maintainers)

There are **four** places an expected value can live; they drift independently:

| Sink | Eval1 (count) | Eval2 (ground truth) | Key |
|------|---------------|----------------------|-----|
| xlsx `articles_table` | `Count` | `GroundTruth` (JSON array) | URL + HuntableType |
| `config/eval_articles.yaml` | `expected_count` | — | subagent + url |
| `config/eval_articles_data/<subagent>/articles.json` | `expected_count` (mirror) | — | url |
| `config/eval_articles_data/<subagent>/ground_truth.json` | — (len) | `expected_items` | url |
| DB `subagent_evaluations` | `expected_count` | `expected_items` (jsonb) | subagent_name + article_url |

Contract truth: live prompt is in the DB workflow config `agent_prompts`; the
`src/prompts/<AgentName>` files are seeds/fallbacks only (see
`src/prompts/README.md` and `src/utils/default_agent_prompts.py`).

The contract test `tests/quality/test_eval_articles_sync.py` enforces
yaml == articles.json == ground_truth-item-count; `tests/unit/test_ground_truth_files.py`
enforces ground_truth schema + full article coverage. Any update via this prompt
must keep both green.
