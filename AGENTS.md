# AGENTS.md

Repository contract for OpenCode sessions. Contains only what an agent is likely to miss.
When artifacts disagree, trust: runtime code > enforced schemas > passing tests > docs.

---

## Orientation

| Path | Purpose |
|---|---|
| `src/web/modern_main.py` | FastAPI app lifespan, startup side effects, wiring |
| `src/web/routes/__init__.py` | Route surface -- all route modules |
| `src/workflows/agentic_workflow.py` | LangGraph 7-step pipeline with early-exit gates |
| `src/worker/celery_app.py` | Celery broker, worker tasks, periodic job registration |
| `src/config/workflow_config_schema.py` | v2 config contract (canonical key names, prompt blocks) |
| `src/database/models.py` | SQLAlchemy tables + stored JSON field contracts |
| `src/core/fetcher.py`, `modern_scraper.py`, `rss_parser.py` | Ingestion pipeline |
| `run_tests.py` | Canonical test entrypoint -- manages `.venv`, auto-starts test containers |
| `pyproject.toml` | Pytest markers, Ruff config, mypy config, Vulture config, project metadata |
| `config/sources.yaml` | Source definitions (seeds DB on first install, DB is source of truth after) |
| `config/presets/AgentConfigs/` | Workflow presets (full snapshots, not partial overrides) |
| `src/prompts/` | Seed prompt defaults -- loaded into DB on bootstrap/reset, not read at runtime |
| `docs/solutions/` | Documented solutions to past problems (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`) |

Package manager: **uv** (not pip). CI uses `uv sync --frozen`, `uv run`.
CLI entrypoint: `./run_cli.sh <command>`.
MCP server: `.mcp.json` at project root auto-wires `scripts/run_mcp_server.sh` for supported clients.

---

## Change-Type Quick Reference

| Change type | Read first | Verify with |
|---|---|---|
| UI or page behavior | `.cursor/agents/ui-designer.md` (UX contract), templates, routes | `python3 run_tests.py ui` or `python3 run_tests.py e2e` |
| API behavior | route module, `src/database/models.py`, `docs/reference/api.md` | `python3 run_tests.py api` |
| Workflow execution | `agentic_workflow.py`, `workflow_trigger_service.py`, `celery_app.py` | `python3 run_tests.py integration` (+ browser if UI) |
| Workflow config / presets / prompts | `workflow_config_schema.py`, `workflow_config_loader.py`, `config/presets/AgentConfigs/README.md` | config/unit/integration tests (+ UI if edited via UI) |
| Persistence / contracts | `src/database/models.py`, `docs/reference/schemas.md` | targeted unit/integration/api tests |
| Source ingestion / scraping | `src/core/fetcher.py`, `rss_parser.py`, `modern_scraper.py`, `source_sync.py` | unit/integration tests |
| Source auto-healing | `source_healing_service.py`, `source_healing_coordinator.py` | `tests/services/test_source_healing_service.py` |
| Scheduled jobs / workers | `celery_app.py`, `scheduled_jobs_service.py` | integration tests |
| Tests / test infrastructure | `run_tests.py`, `docs/development/testing.md`, `pyproject.toml[tool.pytest.ini_options]` | run the affected suites |

Pytest markers live in `pyproject.toml[tool.pytest.ini_options.markers]` (moved from `tests/pytest.ini`).
Key markers by cost: `unit` (stateless) < `integration` (containers) < `api` < `ui` < `e2e`.

---

## Commands

```bash
./setup.sh --no-backups
./start.sh
curl http://localhost:8001/health
python3 run_tests.py smoke       # quick health check, stateless
python3 run_tests.py unit        # stateless, no containers
python3 run_tests.py api         # container-managed
python3 run_tests.py ui          # pytest + Playwright sections
python3 run_tests.py ui --playwright-only   # skip pytest UI section
python3 run_tests.py integration # container-managed
python3 run_tests.py all         # full suite
```

`run_tests.py` manages `.venv`, strips cloud LLM keys from test env, and auto-starts
isolated test containers (postgres:5433, redis:6380, web:8002). It re-execs with
`.venv/bin/python3` if the system `python3` is <3.10.

Lint: `ruff check && ruff format --check` (CI enforces).
Typecheck: `uv run mypy src --config-file pyproject.toml`.
Dead code: `uv run vulture src scripts vulture_whitelist.py --min-confidence 80`.

---

## Common Traps

- **Source config precedence**: `config/sources.yaml` seeds new installs only. Existing
  installs use DB state. Manually sync with `./run_cli.sh sync-sources --config config/sources.yaml --new-only`.
- **Workflow config**: v2 schema enforced by `workflow_config_schema.py`. Preserve canonical
  key names and required prompt blocks. Presets are full snapshots, not partial overrides.
- **Startup side effects**: source seeding, eval article seeding, settings normalization --
  consider these when debugging startup.
- **UI changes require browser verification** (API/unit tests alone are insufficient).
  Must read `.cursor/agents/ui-designer.md` first -- no exceptions. Card containers use
  `.card` / `.card-elevated` / `.card-interactive`, not raw Tailwind utilities.
- **Sigma deduplication does NOT use pgvector**. Article->Sigma matching (RAG) does.
  Sigma->Sigma dedup uses plain SQL `WHERE canonical_class = ?` + deterministic
  `SigmaNoveltyService.similarity = (Jaccard x Containment) - Filter`. See
  `src/services/sigma_novelty_service.py::retrieve_candidates`.
- **ASCII only** in source files, config, shell scripts, and commit messages.
  No Unicode ellipsis, em-dash, curly quotes. Hazards in shell under `set -u`.
- **Always pin package versions** (`==` not `>=`). CI enforces via `lint.yml`.
  Exception: transitive security pins where `==` would cause solver conflicts because the
  package is shared across multiple direct deps (e.g. `langchain-core` — pulled by
  langgraph, langfuse, and langchain simultaneously). Use `>=` only for those cases;
  all other CVE fixes must use `==`. `uv.lock` SHA-256 hashes provide supply-chain
  protection for the actual installed version in all cases — the attack window for `>=`
  pins is specifically `uv lock` re-runs, not normal `uv sync` installs.

---

## UI Stability Contracts

**Requires a spec (`docs/superpowers/specs/`) before renaming or removing:**

### Contract-grade DOM IDs

`#workflowConfigForm`, `#save-config-button`, tabs (`#tab-config` / `#tab-content-*`),
pipeline steps `#s0`-`#s6` (root: `#config-content`),
sub-agent panels `#sa-cmdline`, `#sa-proctree`, `#sa-huntqueries`, `#sa-registry`, `#sa-services`, `#sa-scheduledtasks`,
enable toggles `#toggle-{agentname}-enabled`,
prompt containers `#{agentprefix}-agent-prompt-container` / `-qa-prompt-container`,
preset/version modals `#configPresetListModal` etc.,
model containers `#{agentprefix}-agent-model-container`,
step controls `#junkFilterThreshold`, `#similarityThreshold`, `#sigma-fallback-enabled`

### Contract-grade JS functions

`toggle(id)`, `toggleSA(id)`, `scrollToStep(n)`, `switchTab(tab)`, `loadConfig()`,
`autoSaveConfig()`, `autoSaveModelChange()`, `showConfigPresetList[ForScope](scope)`,
`showConfigVersionList()`, `onAgentProviderChange(agentPrefix)`,
`handleExtractAgentToggle(agentName)`, `renderAgentPrompts()`,
`saveAgentPrompt2(agentName)`, `showPromptHistory(agentName)`,
`testSubAgent(agentName, id)`, `testRankAgent(id)`, `testSigmaAgent(id)`,
`promptForArticleId(defaultId)`, `pushModal(modalId)`, `popModal()`

### agentPrefix token map

| Agent | agentPrefix |
|---|---|
| OS Detection | `osdetectionagent` |
| LLM Ranking | `rankagent` |
| ExtractAgent supervisor | `extractagent` |
| CmdlineExtract | `cmdlineextract` |
| ProcTreeExtract | `proctreeextract` |
| HuntQueriesExtract | `huntqueriesextract` |
| RegistryExtract | `registryextract` |
| ServicesExtract | `servicesextract` |
| ScheduledTasksExtract | `scheduledtasksextract` |
| SIGMA Agent | `sigmaagent` |
| QA variants | `qa-{agentprefix}` (e.g. `qa-cmdlineextract`, `qa-rankagent`) |

---

## User Request Playbooks

### Adding a source

```bash
# 1. Edit config/sources.yaml with unique id, allow/regex/keywords
# 2. Sync without removing existing rows:
./run_cli.sh sync-sources --config config/sources.yaml --no-remove --new-only
# 3. Verify:
curl -s http://localhost:8001/api/health/ingestion | jq '.ingestion.source_breakdown[] | {source_name, articles_count}'
```

Use the `add-source` Claude Code skill (`.claude/skills/add-source/SKILL.md`) for guided
RSS discovery and YAML generation.

### Querying the database

```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper
```

```sql
-- Sources
SELECT id, name, url, rss_url, active, created_at FROM sources ORDER BY name;
-- Recent articles
SELECT a.id, a.title, s.name AS source_name, a.published_at, a.created_at
FROM articles a JOIN sources s ON a.source_id = s.id
ORDER BY a.created_at DESC LIMIT 20;
-- Search
SELECT a.id, a.title, s.name AS source_name, a.published_at
FROM articles a JOIN sources s ON a.source_id = s.id
WHERE a.title ILIKE '%malware%' OR a.content ILIKE '%malware%'
ORDER BY a.published_at DESC LIMIT 10;
```

Default: read-only (SELECT with LIMIT). No INSERT/UPDATE/DELETE without explicit write approval.

---

## Release Flow

`main` is read-only between releases (GitHub branch protection locked by scripts).
Feature work lands on `dev-io`.

```bash
# On dev-io, working tree clean:
scripts/release_cut.py 7.1.0 "Codename" --summary "<one-line>"

scripts/release_unlock.sh              # remove protection
git push origin dev-io                 # create PR dev-io -> main
git push origin v7.1.0                 # triggers release.yml
scripts/release_lock.sh                # restore read-only lock
```

Tags: annotated `git tag -a` only. Canonical format: `vMAJOR.MINOR.PATCH` (no codename in tag
name). Codename goes in the tag message and `docs/CHANGELOG.md` heading.
Pre-releases: `vMAJOR.MINOR.PATCH-rc.N` from a `release/vMAJOR` branch.
Marker tags: `codename/ganymede-start` namespace.

Helper: `scripts/release_lock.sh` / `scripts/release_unlock.sh` (wraps GitHub REST API, needs `gh`).
`REPO=dfirtnt/Huntable-CTI-Studio` and `BRANCH=main` defaults; override via env vars.

Do not land commits on `main` outside this flow.

---

## Exit Classification

Every task ends with exactly one:

- **PASS** -- verification satisfied
- **NO-OP** -- no safe change possible
- **BLOCKED** -- external constraint (classify as ENVIRONMENT / SPECIFICATION / LOGIC)
