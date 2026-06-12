---
name: eval-fixture-audit
description: >
  Audit and correct the eval fixtures (Eval1 expected counts + Eval2 ground-truth
  item lists) for one extractor subagent in Huntable CTI Studio: CmdlineExtract,
  ProcTreeExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract, or
  HuntQueriesExtract. Use this skill whenever the user asks to "audit the evals",
  "run the eval audit", "check/fix/populate ground truth", "reconcile eval
  fixtures", "are the evals set up right", mentions Eval1/Eval2 counts or
  expected_items drift, or names any extractor together with evals, fixtures,
  ground truth, or the evals spreadsheet — even if they don't say "audit". Also
  use it for re-audits after an extractor contract/spec change. Operator-gated
  propose-and-confirm: it extracts blind, reports divergences, and writes nothing
  until the operator approves sink by sink.
---

# Eval Fixture Audit (one extractor per run)

Independently re-derive the eval **expected count (Eval1)** and **ground-truth
item list (Eval2)** for every eval article of a single extractor agent, strictly
from that agent's spec — then compare against all recorded sinks, adjudicate
divergences with the operator, and apply only approved corrections.

Run ONE agent per session. The recorded counts are *anchors*: if you read them
before doing your own extraction, you will rationalize toward them (two prior
model audits diverged on the same articles for exactly this reason). The
discipline is extract-first, compare-second.

## Architectural principle (governs every step)

- The SPEC for what an extractor should extract is its contract doc:
  `docs/contracts/<agent>-extract.md`, layered on the shared baseline
  `docs/contracts/extractor-standard.md`. The operator's adjudication decisions
  define the spec; the doc is the durable record of them.
- Eval ground truth is derived from SPEC + article text and exists for
  **regression tracking**. It must be stable: scores are only comparable
  run-to-run while the spec holds still.
- The live DB config (`agentic_workflow_config.agent_prompts`) and the seed
  (`src/prompts/<AGENT>`) are prompt-side artifacts. They churn with
  experimentation and are IRRELEVANT to this audit. Never extract against them;
  never treat their wording as the rubric.
- Two kinds of ground-truth edits — never conflate them:
  - **FIXTURE CORRECTION** — GT was wrong per the current spec. Fix freely;
    score comparability is preserved.
  - **SPEC CHANGE** — the operator decides a rule itself should move. Requires a
    doc edit + GT re-audit + CHANGELOG entry, and creates a known discontinuity
    in eval scores. Deliberate event only.

## Step 0 — Resolve the agent

Read `references/agent-map.md` for the agent ↔ subagent-key ↔ xlsx-HuntableType
↔ doc-path mapping, all sink locations, DB queries, and write formats. If the
requested agent is not in the table, stop and tell the operator.

## Step 1 — Load the spec from docs and print the rubric  ⛔ STOP gate

1. Read `docs/contracts/extractor-standard.md` and
   `docs/contracts/<agent>-extract.md` in full. The rubric is their union; the
   agent doc wins on conflict.
2. Diff the dropin (`docs/contracts/<agent>-extract-dropin.md`) against the
   agent doc. Report any rule-level divergence as a doc-consistency bug — do not
   resolve it yourself.
3. Print the operative rubric back to the operator as a short checklist —
   positive scope, negative scope, dedup/count semantics, fail-closed threshold,
   output schema — citing the doc section each rule comes from.
4. Optional hygiene (report-only, never changes the rubric): note where the seed
   `src/prompts/<AGENT>` has drifted from the doc. FYI for later prompt work.

**STOP. Wait for the operator to confirm the rubric before extracting anything.**

## Step 2 — Enumerate articles

Load `config/eval_articles_data/<subagent_key>/articles.json`. List
(url, title, expected_count, content_len). State how many you will process.
Flag expected_count=0 rows — confirming zero is as meaningful as finding items.

Do NOT open `ground_truth.json` or any recorded values yet.

## Step 3 — Blind extraction against the spec

For EACH article, in isolation:

1. Read ONLY its `content`. Treat as plain text — no HTML/markdown
   interpretation, no outside knowledge, no URL fetching.
2. Apply the Step-1 rubric literally. Walk the verification checklist for every
   candidate. Fail closed on doubt.
3. Record: my_count, my_items (verbatim primary-field strings), notes (one line
   per judgment call — dedup collapses, wrapper stripping, prose-embedded
   candidates, borderline rejections).
4. ASCII-only item strings; real single backslashes in Windows paths.

For more than ~4 articles, fan out with the Workflow tool: one agent per
article, strict StructuredOutput schema, the merged spec text passed via a /tmp
file, each agent loading its article from articles.json by index. Tell agents
explicitly: long articles get MORE care, not less — length is where shortcuts
cause errors.

## Step 4 — Load recorded values (only now)

Load all five sinks independently (paths and queries in
`references/agent-map.md`):

- **xlsx** — the most-drifted sink; expect pathologies. Report them
  (see `references/hazards.md`), do not auto-fix.
- **DB** `subagent_evaluations` — latest row per URL. This is *fixture* data
  (in scope), unlike the contract-side config row (out of scope).
- **Repo fixtures** — `eval_articles.yaml`, `articles.json` (count mirror),
  `ground_truth.json` (items). Entries with `expected_items: []` are intentional
  registered-but-uncurated placeholders: populate or leave per operator
  instruction, never delete.

## Step 5 — Report (no writes)

Produce:

1. **Eval1 counts table**: url | mine | xlsx | DB | yaml | a.json | gt.json |
   verdict.
2. **Eval2 item-set table**: url | mine | gt.json | overlap | only-mine |
   only-gt | agree?  Match using loose normalization (HTML-entity decode,
   whitespace collapse, case-fold) but display originals. Show the actual
   added/removed items — a matching count with different items is still a
   divergence. Flag NORMALIZED DUPLICATES explicitly (see hazards).
3. **Per-divergence explanation**: 1–2 lines citing the specific doc clause.
   Classify each as (i) fixture error, (ii) my-extraction error, or
   (iii) **REVIEW** — a genuine judgment call only the operator can make.
   REVIEW items are spec territory: both readings are defensible, so the
   operator's ruling may become a doc edit.

Summary line: N articles, X Eval1 divergences, Y Eval2 divergences, Z REVIEW.

## Step 6 — Adjudication, then writes  ⛔ STOP gate

Walk the operator through REVIEW items one at a time, with verbatim article
excerpts on request. For each ruling, state which kind it is:

- **FIXTURE CORRECTION** → update sinks; no doc change.
- **SPEC CHANGE** → queue a doc edit (Step 7) and note the score-comparability
  discontinuity.

**STOP. Offer write targets explicitly and wait:**
(1) xlsx Count+GroundTruth, (2) eval_articles.yaml, (3) articles.json +
ground_truth.json, (4) DB latest rows, (5) subset/none.

Before ANY xlsx write, read `references/hazards.md` (OneDrive/Excel clobber,
backup procedure, flat-array format). Use the write formats in
`references/agent-map.md`. Verify cross-sink consistency after writing.

## Step 7 — Spec changes (only if Step 6 produced any)

Order matters; the doc leads:

1. Edit `docs/contracts/<agent>-extract.md` — canonical statement of the new
   rule.
2. Mirror the edit to `docs/contracts/<agent>-extract-dropin.md`.
3. Re-audit ground truth for items newly eligible/ineligible under the new rule
   (curated delta sweep — beware normalized-duplicate inflation), and apply
   approved deltas to all sinks per Step 6.
4. Add a CHANGELOG entry (`docs/CHANGELOG.md`, Unreleased, Keep-a-Changelog
   format) — this is the era marker for score comparability.
5. **Prompt-side propagation** (separate concern; do only if the operator asks):
   derive the seed from the doc, push to DB via
   `PUT /api/workflow/config/prompts` (proper version bump + history row), and
   regenerate the 9 quickstart presets. The drift-guard test ties seed↔presets —
   never commit a seed edit without the preset regen. Details in
   `references/hazards.md`.

## Scope discipline

- Stage with explicit `git add <path>`, never `-A` — this working tree
  accumulates unrelated changes from parallel sessions.
- Separate commits: substantive fixture/spec changes vs mechanical
  preset/doc-mirror sync.
- Never push without permission.
