# Design: `source-healing` skill

- **Date:** 2026-05-18
- **Status:** Approved (design); pending implementation plan
- **Topic:** Operator-invoked skill to diagnose and repair troubled CTI sources
- **Author:** Andrew Skatoff (via Claude Code brainstorming)

## Problem

CTI sources silently degrade: an RSS feed goes empty, a site migrates domains,
a blog switches to JS rendering, a `post_url_regex` stops matching. The result
is sources that are `active` but ingest **0 articles**, or that rack up
**recurring fetch failures**, with no guided way to diagnose and fix them.

Today there is **no API or CLI surface** to update a source's rich config
(`body_selectors`, `post_url_regex`, `use_playwright`, `wp_json`, discovery
strategies). The source endpoints only cover `/toggle`, `/collect`,
`/lookback`, `/check_frequency`, `/min_content_length`. Repairing the valuable
config requires a targeted DB write or new code.

## Prior art (and why it was deprecated)

A full automated self-healing subsystem existed and was removed in commit
`aa3881da` (2026-05-01): ~7,372 lines — `source_healing_service.py` (1,368
lines), `source_healing_coordinator.py`, `source_healing_config.py`,
`healing_event` model, `heal_source` / `check_sources_for_healing` Celery
tasks, `/heal` `/reset-healing` `/healing-history` endpoints, settings UI.
Preserved in branch `dev-io-6.2.1-self-healing-sources`. DB columns
`healing_exhausted` and `healing_attempts` were kept in the ORM for schema
compatibility.

Stated reason: **"Feature was not ready for production release."** The fatal
flaw was the **delivery vehicle, not the logic**: an always-on Celery loop
mutating live source configs via a headless LLM call, triggered at 100
consecutive failures, with no human in the loop.

The **reusable gold** is pure knowledge: the 5 diagnostic probes and the
symptom→fix playbook. This design keeps 100% of that logic and swaps the
vehicle for an operator-driven skill — the human becomes the safety mechanism
the old design lacked.

## Approved decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Apply posture | **Propose & confirm.** Operator-invoked only; the skill applies a fix only after per-source approval. No Celery, no scheduler, no auto-trigger. |
| 2 | Apply mechanism | **Targeted DB `UPDATE` via psql, no new production code.** Rollback snapshot captured before any write. DB is runtime truth, so no `sources.yaml` sync step. |
| 3 | Triggering | **Both.** `source-healing` (no arg) scans + triages all active sources; `source-healing <id\|identifier\|name>` targets one directly. |
| 4 | Troubled criteria (triage) | **Balanced.** Active AND (`total_articles = 0` OR `consecutive_failures >= 10` OR `last_success` older than 7 days / null). Tunable in the skill doc. |
| 5 | Diagnosis engine | **Agent + playbook, no extra LLM.** Claude runs the 5 probes via curl/Bash + web fetch and applies the playbook in-conversation. No API keys, no cost, fully auditable. |

## Skill packaging

Repo skill following the `cut-release` / `Create-Huntable-Agent` precedent
(SKILL.md + `references/`), not the flat single-file `add-source` shape:

```
.claude/skills/source-healing/
  SKILL.md              # triggers + workflow steps + safety rules (lean)
  references/
    playbook.md         # symptom→fix table, 5 probe recipes, canonical config shapes
```

Rationale: the playbook + probe recipes + canonical config JSON shapes are
dense reference knowledge (~250 lines, lifted from the deprecated service's
prompt). Keeping it in `references/` keeps the description-triggered `SKILL.md`
small and the workflow readable; the agent reads `playbook.md` only once it is
actually healing a source.

**Trigger phrases** (skill `description`): "heal a source", "fix a
broken/failing source", "this source has 0 articles", "diagnose troubled
sources", "why isn't \<source\> collecting", "source-healing".

## Workflow / data flow

**Mode A — triage** (`/source-healing`, no argument):

1. Query the `sources` table via `docker exec cti_postgres psql` (the pattern
   documented in `docs/guides/source-config.md`) for active sources matching
   the balanced net: `total_articles = 0` OR `consecutive_failures >= 10` OR
   `last_success` older than 7 days (or null). Cross-reference the
   `list_sources` MCP tool for the human-readable summary.
2. Present a ranked troubled table: name, id, triggering signal,
   `consecutive_failures`, `last_success`, article count.
3. Operator picks one source, or "all" → the skill iterates **one at a time**,
   still confirming each.

**Mode B — target** (`/source-healing <id|identifier|name>`): skip to step 4.

4. **Snapshot** — `SELECT` the full source row (`url`, `rss_url`, `config`,
   `active`); write it to `logs/source_healing/<date>-<identifier>.snapshot.json`
   and echo it. Captured **before any write**; this is the rollback artifact.
5. **Probe** — the agent runs the 5 probes itself via `curl`/Bash + web fetch
   (no separate LLM, no Celery):
   - **P1 HTTP** — status; redirect chain (`final_url`); on `403`, retry with
     full browser headers; bot-protection fingerprint (CloudFront / Akamai /
     generic WAF).
   - **P2 RSS** — item/entry count; sample titles; **sample article URLs** (to
     learn the *real* post-URL pattern — never guess it).
   - **P3 Sitemap** — discover sitemap(s); sample post URLs + observed pattern.
   - **P4 WP-JSON** — `GET /wp-json/wp/v2/posts?per_page=5`; returns posts?
   - **P5 Page analysis** — visible-text length vs raw-HTML size (JS-render
     signal); sample post links on the listing page.
6. **Diagnose** — apply the ordered playbook (`references/playbook.md`) → root
   cause + one concrete field-level change (`url`, `rss_url`, or a `config`
   merge). Reference a working similar source for selector patterns when needed.
7. **Propose** — show the operator: diagnosis, exact change (`old → new`), and
   the validation plan.
8. **Confirm** — operator approves / edits / rejects (per source, every time).
9. **Apply** — targeted parameterized SQL `UPDATE` on that single source `id`.
   `config` is **read-modify-write merged**, not blind-overwritten (untouched
   keys preserved).
10. **Validate** — trigger a single-source collect (existing
    `/{source_id}/collect` endpoint or `./run_cli.sh collect`); re-check fetch
    success / article delta.
11. **Decide** — success → report & done. Failure → show rollback (restore
    snapshot via SQL), then either stop with a "platform limitation" verdict
    or, with approval, try the next playbook hypothesis. **Bounded: ≤ 3
    attempts** (mirrors the old "3+ rounds, same outcome → platform
    limitation" rule).
12. **Audit** — append outcome to `logs/source_healing/<date>-<identifier>.md`
    (lightweight trail; replaces the deprecated `healing_events` DB table).

## Diagnostic playbook (carried forward verbatim)

`references/playbook.md` encodes the deprecated service's symptom→fix matrix,
since it is pure knowledge:

| Signal | Fix |
|--------|-----|
| RSS returns 200 but 0 items | set `rss_url` → `null` (force scrape fallback) |
| Short visible text + large HTML | `config.use_playwright: true` |
| 0 URLs found but sitemap has them | add `discovery.strategies` sitemap/listing with observed selectors |
| URLs found but all filtered out | rewrite `post_url_regex` from **observed** sample URLs |
| Pages fetched, 0 content extracted | fix `body_selectors` (model on a working similar source) |
| WP-JSON returns posts | set top-level `config.wp_json` fast path |
| Redirect chain to new domain | update `url` to final redirect target |

Plus the **"cannot fix via config"** list — bot protection (Cloudflare/WAF),
missing Playwright browsers, Python code bugs, platform capability gaps →
reported, never attempted.

Canonical config shapes (copied exactly from the deprecated prompt so proposed
fixes are structurally valid):

- WP-JSON: `{"wp_json": {"endpoints": ["https://<site>/wp-json/wp/v2/posts?per_page=50"], "url_field_priority": ["link", "guid.rendered"]}}`
- Listing discovery: `{"discovery": {"strategies": [{"listing": {"urls": ["https://<site>/blog/"], "post_link_selector": "h2.entry-title a"}}]}}`
- Sitemap discovery: `{"discovery": {"strategies": [{"sitemap": {"urls": ["https://<site>/post-sitemap.xml"]}}]}}`
- Enable JS rendering: `{"use_playwright": true}`

## Safety / blast radius

- **Operator-invoked only.** No Celery, scheduler, or auto-trigger — this is
  the specific property whose absence got the old feature deprecated.
- Single-source scope per apply; **rollback snapshot captured before any write**.
- Parameterized SQL only; `config` is merged, not clobbered.
- **Never touches** `active`, `name`, or `identifier` (operator-only fields).
- **Never fabricates URLs** — only uses URLs observed in probe/sitemap data.
- Bounded retry (≤ 3) → then a "platform limitation" verdict.
- Writes to **DB only** (runtime truth). `config/sources.yaml` will drift for
  the healed source — expected per `docs/guides/source-config.md`. The skill
  *offers* an optional final step to also patch the YAML entry for new-build
  parity, default **skip**.

## Verification approach

A markdown skill has no unit harness, so correctness is anchored two ways:

- **Schema validity** — proposed `config` shapes are checked against the
  scraper's expected keys / `src/config/workflow_config_schema.py` so a fix
  cannot be structurally invalid (e.g. `wp_json` placed under
  `discovery.strategies` is a known silent no-op).
- **Live dry-run self-check** — the skill doc prescribes a first-run sanity
  test: run against a currently-troubled live source (e.g. *Google Cloud
  Threat Intelligence*, id 6, 0 articles; or *Sekoia.io*, 215 failures)
  through Propose **without approving Apply**, to confirm probes + playbook
  produce a sane diagnosis.

## Out of scope (YAGNI)

- No Celery task, scheduler, or any automated trigger.
- No new API endpoint or CLI command (decision 2).
- No revival of the `healing_events` / `healing_attempts` DB tables — the audit
  trail is a log file.
- No multi-source batch auto-apply — "all" iterates with per-source confirm.
- No bot-protection bypass — explicitly reported as unfixable.

## References

- Deprecation commit: `aa3881da`
- Preserved old implementation: branch `dev-io-6.2.1-self-healing-sources`
- Source config precedence: `docs/guides/source-config.md`
- Skill precedent: `.claude/skills/cut-release/`, `.claude/skills/add-source/`
