# AGENTS.md

This document defines the operating contract for autonomous agents working in this repository.
It is authoritative. If instructions conflict, this file takes precedence.

---

## Purpose

Agents are expected to operate with **bounded autonomy**, prioritizing determinism, safety, and
machine-verifiable correctness while minimizing human intervention.

Autonomy is allowed only where explicitly defined below.

---

## Start Here

Before proposing or making changes, read in this order:

1. `AGENTS.md`
2. `README.md`
3. `docs/index.md`
4. `docs/development/agent-orientation.md`
5. The code and docs directly tied to the change

Minimum task-specific reading:

| Change type | Read first | Verify with |
|---|---|---|
| UI or page behavior | `src/web/modern_main.py`, `src/web/routes/__init__.py`, relevant `src/web/routes/*.py`, relevant templates/static assets, `docs/development/testing.md`, **`.cursor/agents/ui-designer.md` (UX contract)** | `python3 run_tests.py ui` or `python3 run_tests.py e2e` |
| API behavior | `src/web/routes/__init__.py`, relevant route module, `src/database/models.py`, `docs/reference/api.md` | `python3 run_tests.py api` |
| Workflow execution | `src/workflows/agentic_workflow.py`, `src/services/workflow_trigger_service.py`, `src/worker/celery_app.py`, `docs/architecture/workflow-data-flow.md` | `python3 run_tests.py integration` plus browser verification if UI changed |
| Workflow config / presets / prompts | `src/config/workflow_config_schema.py`, `src/config/workflow_config_loader.py`, `config/presets/AgentConfigs/README.md`, `src/prompts/` | relevant config/unit/integration tests plus UI verification if edited via UI |
| Persistence / contracts | `src/database/models.py`, `docs/reference/schemas.md`, affected routes/services | targeted unit/integration/api tests |
| Source ingestion / scraping | `src/core/fetcher.py`, `src/core/rss_parser.py`, `src/core/modern_scraper.py`, `src/services/source_sync.py`, `docs/guides/source-config.md` | unit/integration tests |
| Source auto-healing | `src/services/source_healing_service.py`, `src/services/source_healing_coordinator.py`, `docs/internals/source-healing.md` | `tests/services/test_source_healing_service.py` |
| Scheduled jobs / workers | `src/worker/celery_app.py`, `src/services/scheduled_jobs_service.py`, `docs/reports/SCHEDULED_JOBS_REPORT.md` | integration tests |
| Tests / test infrastructure | `run_tests.py`, `docs/development/testing.md`, `tests/README.md`, `tests/pytest.ini` | run the affected suites |

---

## Repo Map

Use this map to orient before searching broadly:

| Path | Purpose |
|---|---|
| `src/web/` | FastAPI app, page routes, API routes, templates, and static assets |
| `src/workflows/` | LangGraph workflow execution and workflow state transitions |
| `src/worker/` | Celery app, task queues, and periodic task registration |
| `src/services/` | Core business logic for LLM calls, Sigma generation, similarity, scheduling, healing, and orchestration |
| `src/config/` | Workflow config schema, loaders, and migrations |
| `src/database/` | SQLAlchemy models and database access layers |
| `src/core/` | Ingestion, scraping, processing, and source management |
| `src/prompts/` | Seed/default prompts only -- NOT live runtime prompts. Live prompts live in the DB workflow config's `agent_prompts` field. Disk files are read only on config bootstrap, empty-prompt fallback, or explicit reset via `/api/workflow/config/prompts/{bootstrap,reset-to-defaults}`. Loader: `src/utils/default_agent_prompts.py`. To change live behavior, edit via the workflow config UI (creates a versioned entry) or the config API. See `src/prompts/README.md`. |
| `config/` | Versioned source YAML, workflow presets, eval article data, provider catalogs |
| `tests/` | Pytest suites, Playwright specs, fixtures, and test infrastructure |
| `docs/` | Human-facing docs; useful orientation aid but subordinate to code when they diverge |
| `docs/solutions/` | Documented solutions to past problems (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`) |
| `src/huntable_mcp/` | Read-only Model Context Protocol server for articles, SIGMA, sources, workflow/queue visibility (`run_mcp.py`, `python3 -m src.huntable_mcp`); see `docs/reference/mcp-tools.md` |
| `.claude/skills/` | Project-scoped Claude Code skills (auto-discovered as slash commands); see individual `SKILL.md` files |

---

## Canonical Sources Of Truth

When artifacts disagree, trust them in this order:

1. Runtime code and enforced schemas
2. Executable tests
3. Focused reference docs
4. General overview docs

Canonical files for common questions:

- Runtime app entrypoint: `src/web/modern_main.py`
- Route surface: `src/web/routes/__init__.py`
- Workflow implementation: `src/workflows/agentic_workflow.py`
- Worker and schedules: `src/worker/celery_app.py`
- Workflow config contract: `src/config/workflow_config_schema.py`
- Persistence contract: `src/database/models.py`
- Test runner and environment policy: `run_tests.py`
- Pytest markers and defaults: `tests/pytest.ini`
- Workflow presets: `config/presets/AgentConfigs/README.md`

Do NOT treat high-level counts, inventories, or generated endpoint summaries as authoritative if code disagrees.

---

## Core Principles

- Determinism over creativity
- Verification over explanation
- Minimal change over expansive refactors
- Explicit contracts over inference
- Machine-checkable outcomes over qualitative judgment

---

## Operating Doctrine

**Workflow (MANDATORY)**  
Recon → Plan → Execute → Verify → Report

- Recon: gather context strictly from repository artifacts
- Plan: propose a minimal, scoped approach
- Execute: apply changes within the Autonomy Envelope
- Verify: validate outcomes using machine-executable checks
- Report: summarize outcome and classification

Skipping steps is prohibited.

---

## Recon Rules

- Read all relevant files before proposing changes
- Prefer existing patterns, schemas, and conventions
- Do NOT invent new abstractions unless explicitly required
- If intent cannot be inferred from artifacts, STOP and report a SPECIFICATION blocker
- Read the nearest contract file before changing structured data or workflow behavior

---

## Autonomy Envelope

The agent MAY act autonomously without user confirmation when ALL conditions are met:

- Change scope is limited to:
  - Prompts
  - Tests
  - UI behavior
  - Documentation
  - Non-destructive code changes
- No secrets, credentials, or sensitive data involved
- No data deletion or irreversible migration
- Verification is machine-executable
- Exit condition is explicitly defined

The agent MUST stop and report when ANY condition is met:

- Schema, contract, or intent ambiguity exists
- Multiple materially different solutions exist and local precedent does not resolve the choice
- A destructive or irreversible action is required
- Verification cannot be automated

---

## Execution Constraints

- **Always pin package versions.** Never use unpinned versions (e.g., `package>=1.0.0` or bare `package`). Specify exact versions in `package.json`, `pyproject.toml`, `requirements.txt`, or equivalent. Unpinned versions break determinism and cause CI failures when upstream dependencies change.

- Do NOT infer missing requirements
- Do NOT “fix forward” by adding speculative behavior
- Prefer deletions, tightening, or constraint enforcement over additions
- All changes must be reviewable and diffable
- Prefer the existing startup, CLI, and workflow entrypoints over ad-hoc scripts when validating behavior
- **ASCII only** in source files, shell scripts, config, and commit/PR messages. No Unicode
  ellipsis (`...` not the single-character form), em-dash (`--`), curly quotes, or other
  Unicode punctuation. Unicode in shell scripts is a silent correctness hazard: under
  `set -u`, bytes like `...` get absorbed into identifier parsing and produce
  `unbound variable` failures rather than syntax errors. Unicode is acceptable only in
  genuinely user-facing display strings (UI labels, rendered markdown, chat output).

---

## Canonical Commands

Use these commands by default unless the task clearly requires something narrower:

```bash
./setup.sh --no-backups
./start.sh
curl http://localhost:8001/health
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
python3 run_tests.py ui
python3 run_tests.py e2e
python3 run_tests.py all
```

Notes:

- `run_tests.py` is the canonical test entrypoint.
- `run_tests.py` ensures `.venv` exists and auto-starts isolated test containers for stateful suites.
- API/UI/E2E tests must not be run against the primary development database.
- `run_tests.py ui` runs two independent sections (pytest `tests/ui/` + Node.js `tests/playwright/`). Use `--skip-playwright-js` or `--playwright-only` to run one section at a time. See [docs/development/testing.md](docs/development/testing.md).

---

## Common Traps

- Source configuration precedence is **database first after initial seed**. `config/sources.yaml` seeds new installs, but existing installations use DB state unless manually synced.
- Workflow config is a **v2 schema contract** enforced by `src/config/workflow_config_schema.py`. Preserve canonical key names and required prompt blocks.
- Presets under `config/presets/AgentConfigs/` are full workflow snapshots, not partial overrides.
- Startup performs data-shaping work such as source seeding checks, eval article seeding, and settings normalization. Consider startup side effects when debugging.
- UI-visible changes require browser-level verification; API or unit tests alone are insufficient.

---

## UI Stability Contracts

The Playwright suite and JS `onclick`/`onchange` bindings treat the items below as hard contracts. Renaming or removing any of them silently breaks tests or runtime wiring. **A spec in `docs/superpowers/specs/` must be approved before touching them.**

### Contract-grade DOM IDs

| Group | IDs |
|---|---|
| Config form | `#workflowConfigForm`, `#save-config-button` |
| Tab system | `#tab-config`, `#tab-executions`, `#tab-queue`, `#tab-content-config`, `#tab-content-executions`, `#tab-content-queue` |
| Pipeline step sections | `#s0`–`#s6` (scrollable root: `#config-content`) |
| Sub-agent accordion panels | `#sa-cmdline`, `#sa-proctree`, `#sa-huntqueries`, `#sa-registry` |
| Sub-agent enable toggles | `#toggle-{agentname}-enabled` (e.g. `#toggle-cmdlineextract-enabled`) |
| Prompt containers (JS-populated) | `#{agentprefix}-agent-prompt-container`, `#{agentprefix}-agent-qa-prompt-container` |
| Config preset / version modals | `#configPresetListModal`, `#configVersionListModal`, `#configVersionList`, `#configVersionSearch`, `#configVersionPrevBtn`, `#configVersionNextBtn`, `#configVersionPageInfo` |
| Per-agent model containers | `#{agentprefix}-agent-model-container` (e.g. `#sigma-agent-model-container`, `#os-detection-model-container`) |
| Step controls | `#junkFilterThreshold`, `#similarityThreshold`, `#sigma-fallback-enabled` |

### Contract-grade JS functions

Changing a signature or removing a function listed here breaks `onclick`/`onchange` bindings in the HTML or inter-file calls without any static error.

| Function | Called from |
|---|---|
| `toggle(id)` | Step section headers (`onclick="toggle('s0')"` etc.) |
| `toggleSA(id)` | Sub-agent accordion headers (`onclick="toggleSA('sa-cmdline')"` etc.) |
| `scrollToStep(n)` | Rail node clicks |
| `switchTab(tab)` | Tab nav buttons and cross-tab deep links |
| `loadConfig()` | Reset button (`onclick="loadConfig()"`) |
| `autoSaveConfig()` | `onchange` on ~20 config inputs |
| `autoSaveModelChange()` | `onchange` on provider/model selects |
| `showConfigPresetList()` | Presets button |
| `showConfigPresetListForScope(scope)` | Sub-agent Save/Load preset buttons |
| `showConfigVersionList()` | Versions button |
| `onAgentProviderChange(agentPrefix)` | Provider select `onchange` for every agent |
| `handleExtractAgentToggle(agentName)` | Sub-agent enable checkbox `onchange` |
| `renderAgentPrompts()` | Called by `loadConfig()` to inject prompt panels |
| `saveAgentPrompt2(agentName)` | Save button inside dynamically rendered prompt panels |
| `showPromptHistory(agentName)` | History button inside dynamically rendered prompt panels |
| `testSubAgent(agentName, id)` | Sub-agent test buttons |
| `testRankAgent(id)`, `testSigmaAgent(id)` | Step 2 / Step 4 test buttons |
| `promptForArticleId(defaultId)` | Used by all test buttons to prompt for article ID |
| `pushModal(modalId)` / `popModal()` | Modal stack manager — used across the page |

### agentPrefix token map

The `agentPrefix` string is used as a key in DOM IDs, `onchange` handlers, and API calls. Renaming a prefix requires updating all three simultaneously.

| Agent | agentPrefix |
|---|---|
| OS Detection | `osdetectionagent` |
| LLM Ranking | `rankagent` |
| ExtractAgent supervisor | `extractagent` |
| CmdlineExtract | `cmdlineextract` |
| ProcTreeExtract | `proctreeextract` |
| HuntQueriesExtract | `huntqueriesextract` |
| RegistryExtract | `registryextract` |
| SIGMA Agent | `sigmaagent` |
| QA variants | `{agentprefix}qa` (e.g. `cmdlineqa`, `rankqa`) |

### CSS variable contracts

All pipeline accent colors are defined in `src/web/static/css/theme-variables.css`. New UI code must reference these variables — no raw hex values.

| Variable | Use |
|---|---|
| `--step-0` … `--step-6` | Per-step accent color (border beams, badges, glow) |
| `--sc` | Scoped alias set per step section (`#s0 { --sc: var(--step-0); }` etc.) — enables uniform child styling without per-step CSS repetition |
| `--panel-bg-*` | Background layer stack for nested panels |

### What requires a spec before code changes

- Renaming or removing any contract-grade DOM ID or JS function above
- Changing an `agentPrefix` token
- Adding or removing a pipeline step (extending/shrinking the `s0`–`s6` / `sa-*` namespace)
- Changing the `toggle()` / `toggleSA()` open-state model (CSS class, ID format, or no-op guard logic)
- Changing the modal stack protocol (`pushModal` / `popModal`)

Changes within a step's content (labels, layout, new controls) do not require a spec — only the structural anchors above are frozen.

---

## User Request Playbooks (Agent-Ready)

- **Mutating work** (writes, `sync-sources`, disabling sources): get explicit user confirmation first; state what will change.
- **Default**: prefer read-only (`SELECT`, health/ingestion endpoints).

### Adding a new source

Use the `/add-source` Claude Code skill (`.claude/skills/add-source/SKILL.md`) for guided, repeatable source addition. The skill automates RSS discovery, selector inspection, YAML generation, and safe sync.

Manual steps (or what the skill does under the hood):

1. Edit `config/sources.yaml`:
   - Add an entry with a unique `id`.
   - Keep `allow`, `post_url_regex`, and `title_filter_keywords` consistent with existing sources to avoid scraping noise.
2. Sync YAML -> PostgreSQL (without deleting existing rows or overwriting existing configs):
   ```bash
   ./run_cli.sh sync-sources --config config/sources.yaml --no-remove --new-only
   ```
3. Verify it is active:
   ```bash
   curl -s http://localhost:8001/api/health/ingestion | jq '.ingestion.source_breakdown[] | {name, total: .total_articles, active: .active}'
   ```
   - Confirm the new source appears with `active: true` (or update to `active: true` if needed).

### Querying the database (read-only by default)

1. Connect to Postgres:
   ```bash
   docker exec cti_postgres psql -U cti_user -d cti_scraper
   ```
2. Run `SELECT` with `LIMIT` (no `INSERT`/`UPDATE`/`DELETE` without explicit write approval).

**Sources:**
```sql
SELECT id, name, url, rss_url, active, created_at
FROM sources
ORDER BY name;
```

**Recent articles:**
```sql
SELECT
  a.id,
  a.title,
  s.name AS source_name,
  a.published_at,
  a.created_at
FROM articles a
JOIN sources s ON a.source_id = s.id
ORDER BY a.created_at DESC
LIMIT 20;
```

**Search title/content:**
```sql
SELECT
  a.id,
  a.title,
  s.name AS source_name,
  a.published_at
FROM articles a
JOIN sources s ON a.source_id = s.id
WHERE
  a.title ILIKE '%malware%'
  OR a.content ILIKE '%malware%'
ORDER BY a.published_at DESC
LIMIT 10;
```

3. If the user asks for training/classification-specific filtering, ensure the query considers `article_metadata.training_category` (used for training gates).

### Release branch protection

`main` is held **read-only between releases** via GitHub branch protection
(`lock_branch: true`, `enforce_admins: true`, `allow_force_pushes: false`,
`allow_deletions: false`). Feature work lands on `dev-io`; `main` only moves during
release cuts. Admin accounts are not exempt -- even `git push --force` from an admin
is rejected while the lock is in place.

Two helper scripts wrap the GitHub REST API to flip state:

- `scripts/release_unlock.sh` -- DELETEs the protection object (idempotent; treats
  "Branch not protected" as a no-op).
- `scripts/release_lock.sh` -- PUTs the full protection payload, restoring the lock.

Release flow:

```bash
# On dev-io, working tree clean, in sync with origin:
scripts/release_cut.py 5.4.0 Triton --summary "<one-line>"
#   - bumps pyproject.toml
#   - rolls docs/CHANGELOG.md [Unreleased] -> dated section
#   - updates docs/reference/versioning.md history
#   - updates README.md version line
#   - runs scripts/verify_release_tag.py as a pre-flight guard
#   - commits as `release: vX.Y.Z "Codename"` and creates annotated tag

scripts/release_unlock.sh      # remove protection
git push origin dev-io
# open PR dev-io -> main; merge after CI green
git push origin v5.4.0         # triggers .github/workflows/release.yml
scripts/release_lock.sh        # restore read-only lock
```

`.github/workflows/release.yml` re-runs the verifier on the pushed tag and
then creates the GitHub Release from the matching `docs/CHANGELOG.md`
section. If either fails, the tag stays but no Release is published; fix
the discrepancy, delete the tag, and re-cut.

All scripts default to `REPO=dfirtnt/Huntable-CTI-Studio` and `BRANCH=main`;
override via environment variables for forks or other branches. The lock/
unlock scripts require `gh` CLI authenticated with `repo` scope.

**Do not** attempt to land commits on `main` outside this flow. If a commit reaches
`main` unintentionally, cherry-pick it to `dev-io`, reset `main` to the last release
tag, and force-push with explicit user confirmation -- this is a destructive action
and outside the Autonomy Envelope.

### Release tagging convention

Tags are the machine identifier; codenames are human flavor. Keep them separate
so `git describe`, `git tag --sort=-v:refname`, PyPI-style parsers, and shell
globs all work without special cases.

- **Canonical tag name:** `vMAJOR.MINOR.PATCH` only (e.g. `v5.3.0`, `v5.4.1`).
  No codename suffix, no prefix variants (`kepler-v4.2`, `v5.0.0-ganymede-start`
  are historical artifacts -- do not extend the pattern).
- **Codename:** lives in the annotated tag *message* and the `docs/CHANGELOG.md`
  heading, not the tag name.
- **Annotated, not lightweight:** always `git tag -a`, never a lightweight tag.
  Signed (`git tag -s`) preferred once signing is set up.
- **Pre-releases:** `vMAJOR.MINOR.PATCH-rc.N` (e.g. `v6.0.0-rc.1`), cut from a
  `release/vMAJOR` branch forked off `dev-io`.
- **Marker tags** (for non-release events like "Ganymede work begins here") go
  under a `codename/` namespace: `codename/ganymede-start`. Grep-able, but
  will not collide with release tools that filter `v*.*.*`.

Cut a release tag from the release-cut commit on `main`:

```bash
git tag -a v5.3.0 -m "Callisto (5.3 line) -- <one-line summary>"
git push origin v5.3.0     # triggers release.yml guards + GitHub Release
```

The `release.yml` CI workflow enforces the pieces a human is most likely to
miss: tag version matching `pyproject.toml`, and a dated `[X.Y.Z]` section in
`docs/CHANGELOG.md`.

---

## Diff-Only Mode

When modifying prompts, schemas, rules, or configuration files:

- Output MUST be a unified diff
- No prose, commentary, or explanation unless explicitly requested
- If no safe improvement exists, output an empty diff

---

## Verification Requirements

Verification MUST consist of one or more of the following:

- Tests passing (unit, integration, or evals)
- Deterministic output matching an expected schema
- UI behavior confirmed via tooling or documented reproduction steps

If verification criteria are not met, the task is NOT complete.

---

## Exit Conditions (MANDATORY)

Every task MUST terminate with exactly one classification:

- **PASS** — verification criteria satisfied
- **NO-OP** — no safe or meaningful change possible
- **BLOCKED** — progress prevented by external constraint

If none apply, continue autonomously until retry limits are reached.

---

## Retry & Escalation Policy

- Maximum of **7 retries per failure class**
- On retry exhaustion, classify the blocker as one of:
  - **ENVIRONMENT** — tooling, infra, runtime limitations
  - **SPECIFICATION** — ambiguous or missing requirements
  - **LOGIC** — conflicting constraints or rules

When BLOCKED:
- Report evidence
- Do NOT propose speculative fixes
- Do NOT continue retries

---

## Tooling & Verification

- Use your MCP tools to perform testing and verification
- Do NOT assume tool success without checking outputs
- Treat tool errors as ENVIRONMENT blockers unless proven otherwise

---

## Reporting Format

Final output MUST include:

- Exit classification (PASS / NO-OP / BLOCKED)
- Evidence (test results, diffs, logs, or schema validation)
- Blocker classification if applicable

No additional narrative unless requested.

---

## Prohibited Behaviors

- Acting outside the Autonomy Envelope
- Introducing undocumented behavior
- Making judgment calls without explicit thresholds
- Masking uncertainty with verbosity
- Continuing execution when blocked

---

## Final Note

You are a bounded, deterministic execution agent.

When uncertain: stop.  
When blocked: classify.  
When complete: verify and exit.
