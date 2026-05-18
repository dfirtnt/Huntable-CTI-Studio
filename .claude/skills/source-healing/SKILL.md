---
name: source-healing
description: >
  Diagnose and repair troubled CTI intelligence sources in Huntable CTI Studio —
  sources that ingest 0 articles or rack up recurring fetch failures. Use this
  skill whenever the user says "heal a source", "fix a broken/failing source",
  "this source has 0 articles", "why isn't <source> collecting", "diagnose
  troubled sources", "source-healing", or whenever a source has stopped
  producing articles, has stale content, redirects, switched to JS rendering, or
  is accumulating failures — even if the user doesn't say the word "heal".
  Operator-invoked and propose-and-confirm: it diagnoses, proposes one concrete
  config fix, and applies it only after the operator approves. It never
  auto-applies, never runs on a schedule.
---

# Source Healing

A guided workflow to find why a CTI source stopped collecting and fix it
safely. You (Claude) are the diagnostic engine: you run probes, apply the
playbook in `references/playbook.md`, and propose one concrete fix. A human
approves every change.

## Why this is a skill and not a background job

An automated version of this existed (Celery loop + headless LLM mutating live
configs) and was removed because unattended config mutation was not
production-safe. The valuable part — the probes and the symptom→fix playbook —
is pure knowledge and lives on here. The safety comes from the delivery
vehicle: an operator runs this, sees the diagnosis, and approves the fix. Keep
that property. Do not add scheduling, auto-apply, or batch-without-confirm.

## Operating rules (read before touching anything)

These exist because a source config is live production state and the fixes are
inferred, not certain:

- **Propose, then confirm.** Never write a change until the operator approves
  that specific change for that specific source.
- **Snapshot before any write.** The pre-change row is the only way back.
- **One source at a time.** "Heal all" iterates and re-confirms each source.
- **Never modify `active`, `name`, or `identifier`.** Activation is an
  operator decision; identity changes break references. You only ever touch
  `url`, `rss_url`, and `config`.
- **Never invent URLs.** Only use URLs you actually observed in probe output
  (RSS sample links, sitemap entries, redirect targets). A guessed
  `post_url_regex` or domain silently breaks collection.
- **Merge config, don't replace it.** Read the existing `config`, change only
  the keys the fix requires, write the merged result back.
- **Bound the effort.** At most 3 fix attempts per source. If the same class
  of failure survives 3 attempts, report it as a platform limitation rather
  than trying more permutations — some problems (bot protection, code bugs)
  cannot be fixed by config.
- **DB is runtime truth.** Write fixes to the database. `config/sources.yaml`
  is only a new-build seed; it will drift and that is expected. Offer a YAML
  patch only as an optional final step, defaulting to skip.

## Workflow

### Mode select

- **No argument → triage.** Scan all active sources, rank the troubled ones,
  let the operator pick.
- **`source-healing <id | identifier | name>` → target.** Jump straight to
  step 4 for that source.

### Step 1 — Triage (triage mode only)

Query the database directly (the MCP `list_sources` summary is a useful
cross-check but does not expose `consecutive_failures` / `last_success`
cleanly). Use the project's psql pattern:

```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -t -A -F'|' -c "
  SELECT id, identifier, name, total_articles, consecutive_failures,
         last_success, active
  FROM sources
  WHERE active = true
    AND ( total_articles = 0
       OR consecutive_failures >= 10
       OR last_success IS NULL
       OR last_success < now() - interval '7 days' )
  ORDER BY consecutive_failures DESC, total_articles ASC;"
```

This is the **balanced** net: a source is "troubled" if it is active and has
never produced an article, OR has failed ≥ 10 times in a row, OR has not had a
successful collect in over 7 days. These thresholds are deliberately tunable —
if the operator wants a wider or narrower net, adjust the `WHERE` clause and
say so.

Present the results as a ranked table (name, id, the signal that flagged it,
`consecutive_failures`, `last_success`, article count). Ask which source to
heal. "All" is allowed but means "iterate, confirming each".

### Step 2 — Capture rollback snapshot

Before anything else, snapshot the full source row so any change is
reversible:

```bash
mkdir -p logs/source_healing
docker exec cti_postgres psql -U cti_user -d cti_scraper -t -A -c "
  SELECT row_to_json(s) FROM (
    SELECT id, identifier, name, url, rss_url, config, active
    FROM sources WHERE id = <ID>) s;" \
  > "logs/source_healing/$(date +%F)-<identifier>.snapshot.json"
```

Echo the snapshot to the operator. If this file is empty or the source id does
not exist, stop — do not proceed blind.

### Step 3 — Probe

Run the five diagnostic probes from `references/playbook.md` ("Probe recipes").
Run them with `curl` / web fetch directly; you are the diagnostic engine, so no
separate model call is needed. The probes establish ground truth:

1. **HTTP** — status, redirect chain, bot-protection fingerprint
2. **RSS** — item count, sample titles, **real article URL pattern**
3. **Sitemap** — available sitemaps and sample post URLs
4. **WP-JSON** — does `/wp-json/wp/v2/posts` return content?
5. **Page analysis** — visible-text vs HTML size (JS-render), listing links

Record the raw probe findings; the operator should see what you saw.

### Step 4 — Diagnose

Apply the ordered playbook in `references/playbook.md` ("Diagnostic playbook")
to the probe findings. Produce: a one-paragraph root cause and exactly one
proposed change to `url`, `rss_url`, or a `config` merge. If a working similar
source exists (same platform/CMS), use its config as the model for selectors —
do not invent selectors from scratch.

If the evidence points to something config cannot fix (see "What this cannot
fix" in the playbook), say so plainly and stop. That is a successful
diagnosis, not a failure.

### Step 5 — Propose

Show the operator, compactly:

- **Diagnosis:** the root cause, grounded in specific probe output
- **Proposed change:** the field and `old → new` value (the exact merged
  `config` if applicable)
- **Validation plan:** that you will trigger a single-source collect and check
  the article delta
- **Rollback:** the snapshot path

Then ask for approval. Accept "approve", an edited value, or "reject".

### Step 6 — Apply (only after approval)

Apply the approved change with a targeted, parameterized update to that one
source. For a scalar field:

```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "
  UPDATE sources SET rss_url = NULL, updated_at = now() WHERE id = <ID>;"
```

For a `config` change, always read-modify-write the **whole object** so
untouched keys survive:

1. `SELECT config FROM sources WHERE id = <ID>;`
2. Merge the fix's keys into that JSON yourself (in the agent / `jq`),
   preserving every existing key; for nested keys merge deeply, don't replace
   the parent.
3. Write the full merged object back: `UPDATE sources SET config = '<full
   merged json>', updated_at = now() WHERE id = <ID>;`

Note `sources.config` is a Postgres `JSON` column, **not `JSONB`** — the `||`
merge operator does not apply, which is the other reason to merge in the agent
layer and write the complete object. Never `SET config = '<just the patch>'`;
that destroys every other key.

### Step 7 — Validate

First, preview the fix with a **dry run** — this exercises discovery and fetch
for just this source but writes nothing, so it confirms the fix works before
any article hits the database:

```bash
./run_cli.sh collect --source <identifier> --dry-run
```

If the dry run shows the source now discovering/fetching articles, run the real
collection:

```bash
./run_cli.sh collect --source <identifier>   # or: curl -s -X POST \
  http://localhost:8001/api/sources/<ID>/collect
```

Re-query `total_articles` / `consecutive_failures` / `last_success`. Success =
the collect succeeded and (for 0-article sources) new articles appeared, or
(for failing sources) the failure cleared. If the dry run shows nothing, the
fix did not work — go to Step 8 without writing real articles.

### Step 8 — Decide and record

- **Success:** report what changed and the new state. Append an outcome line
  to `logs/source_healing/$(date +%F)-<identifier>.md`.
- **No improvement:** show the operator the rollback command (restore from the
  snapshot), restore on their approval, and either stop with a platform-
  limitation verdict or, if attempts remain (≤ 3 total) and the playbook has
  another hypothesis, propose the next fix (back to Step 5).
- Always leave an audit line in the per-source log: timestamp, change, outcome.

### Optional — YAML parity

Offer (default: skip) to also patch the source's entry in
`config/sources.yaml` so a future clean build inherits the fix. This is
cosmetic for the running system since the DB is authoritative.

## First-run self-check

Before trusting this on a source you care about, rehearse it: target a
currently-troubled live source and go through Steps 2–5 **without approving the
apply**. Confirm the probes return real data and the diagnosis is sane. If you
want to see whether a hypothesized fix would help without changing anything,
`./run_cli.sh collect --source <identifier> --dry-run` shows what collection
would do with the *current* config and writes nothing. Good candidates are
whatever Step 1 surfaces today (e.g. a 0-article source, or one with a high
`consecutive_failures` count).

## Reference

`references/playbook.md` — the five probe recipes, the ordered symptom→fix
playbook, canonical `config` shapes to copy exactly, and the list of problems
config cannot fix. Read it before Step 3.
