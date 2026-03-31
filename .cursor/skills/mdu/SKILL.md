---
name: mdu
description: "Update all Markdown documentation to reflect code and session changes. Use this skill whenever the user says \"mdu\", asks to \"update docs\", \"sync documentation\", \"refresh changelog\", \"update the changelog\", \"docs are stale\", \"add this to the changelog\", or any request to align documentation with recent code changes. Also trigger when the user mentions MkDocs build, doc drift, nav sync, or documentation freshness after making code changes -- even if they just say something like \"ok the feature is done, clean up the docs\" or \"make sure the docs match\". Handles changelog entries, README updates, docs/ page updates, mkdocs.yml nav sync, and strict build verification."
---

# MDU — Markdown Documentation Updater

Update all Markdown documentation to accurately reflect the current state of the codebase. The goal is **factual alignment between code and docs** — not stylistic polish.

## Philosophy

Documentation is subordinate to code. When docs and code disagree, code wins. This skill exists to close that gap efficiently: read the diff, update only affected docs, verify the build.

## Scope boundaries

**In scope:** `docs/CHANGELOG.md`, `README.md`, all files under `docs/`, `mkdocs.yml` nav entries.

**Off limits:** `AGENTS.md` and `CLAUDE.md` are manually maintained — never modify them. They define the agent operating contract and are outside the documentation update cycle.

---

## Standard run

When the user says "mdu" or asks to update/sync docs, follow this sequence.

### Step 1: Detect what changed

Understand the scope of recent changes before touching any docs.

```bash
# On a feature branch:
git diff main..HEAD --name-only
git log main..HEAD --oneline

# On main after recent commits:
git diff HEAD~3..HEAD --name-only
git log --oneline -5
```

Map each changed file to its documentation surface using this routing:

| Change type | Docs to check |
|---|---|
| UI or page behavior | Feature docs, guides, README quick-start |
| API endpoints or behavior | `docs/reference/api.md`, relevant guides |
| Workflow execution or state | `docs/architecture/workflow-data-flow.md`, feature docs |
| Workflow config / presets | `docs/getting-started/configuration.md`, preset README |
| Database models or schemas | `docs/reference/schemas.md` |
| Source ingestion or scraping | `docs/guides/source-config.md`, `docs/guides/add-feed.md` |
| Tests or test infra | `docs/development/testing.md` |
| CLI commands | `docs/reference/cli.md` |
| MCP tools | `docs/reference/mcp-tools.md` |
| ML / model changes | `docs/ml-training/`, `docs/reference/ml-features.md` |
| New dependencies | README (stack section), relevant setup/install docs |

If a change doesn't fit these categories, use judgment to identify affected docs — but don't force-update docs that aren't actually stale.

### Step 2: Update the changelog

Add entries to `docs/CHANGELOG.md` under `## [Unreleased]`, in the appropriate subsection.

**Subsection rules:**
- `### Added` — New features, endpoints, tests, docs, sources, CLI commands
- `### Changed` — Modifications to existing behavior, UI redesigns, dependency updates, refactors, doc updates that reflect code changes
- `### Fixed` — Bug fixes, crash fixes, regression fixes, correctness improvements

If a subsection doesn't exist yet under `[Unreleased]`, create it. The order is: Changed, Added, Fixed (matching the existing convention).

**Entry format — every entry follows this pattern:**

```markdown
- **Feature/component name** (YYYY-MM-DD): Description with `code references`, `file/paths`, `API endpoints`, and `CLI commands` in backticks. Reference test files when tests were added. Use markdown links for doc cross-references: [page name](relative/path.md).
```

The date is always today's date. Be specific — name the endpoint, the file, the config key. Include enough context that someone reading the changelog months later understands both what changed and why.

**Examples of the quality bar** (drawn from this project's actual changelog):

```markdown
### Added
- **ML model rollback** (2026-03-30): `POST /api/model/rollback/{version_id}` restores any prior model version — copies the versioned `.pkl` artifact to the live path, flips `is_current` in DB, clears the `ContentFilter` lru_cache, and runs a background chunk re-score. New `is_current` column on `ml_model_versions` with incremental migration.
- **Tests** (2026-03-30): 10 unit tests (`test_ml_model_versioning_rollback.py`) for `activate_version` / `set_version_artifact`; 16 API tests (`test_model_rollback_api.py`) covering rollback endpoint, paginated versions, and version search.

### Fixed
- **Uvicorn reload crash** (2026-03-30): `--reload` watched all files including `.pkl` model artifacts, causing cascading restarts during retrain. Added `--reload-include '*.py'` and `--reload-exclude` for `models/*`, `tests/*`, `scripts/*`, `*.pkl` in both `docker-compose.yml` and `docker-compose.dev2.yml`.
- **`run_sync` false positive** (2026-03-30): Substring match `"running event loop" in str(e)` incorrectly caught `"no running event loop"` from background threads. Replaced with explicit boolean check.

### Changed
- **Documentation** (2026-03-27): MkDocs nav adds [Source healing (internals)](internals/source-healing.md). [API reference](reference/api.md) documents `GET /sigma-queue`, `GET /api/embeddings/stats` (`sigma_corpus`).
```

**Grouping:** When multiple changes relate to the same feature area (e.g., three test files for a new endpoint), combine them into a single entry rather than creating three separate ones. When changes span different categories (a feature + its tests + its docs), the feature goes in Added, the tests can be a sub-bullet or a separate entry depending on significance.

### Step 3: Update affected docs

For each doc identified in Step 1:

1. **Read the doc first.** Understand its current structure and claims.
2. **Read the code it describes.** Code is the source of truth — verify before rewriting.
3. **Update only the stale parts.** Surgical edits, not rewrites.
4. If a significant new feature has no doc page and warrants one, create it. Minor changes don't need their own page.

**README specifics:**
- Keep quick-start instructions, stack description, and port numbers current
- Ensure links to `docs/`, `./start.sh`, and other entry points resolve
- The README is a landing page — don't turn it into a feature catalog

### Step 4: Sync mkdocs.yml nav

If new doc pages were created or existing pages were moved/renamed:

1. Read `mkdocs.yml` to understand the current nav structure and naming conventions
2. Add new entries in the logically correct section, following the `- Title: path/to/page.md` pattern
3. Don't reorganize or reorder existing nav entries unless asked

### Step 5: Verify the build

This is a **read-only verification step** — `mkdocs build` generates a temporary `site/` directory but does not modify any source files. Always run it, even if you haven't changed any docs (it validates that existing docs are still clean).

```bash
cd /Users/starlord/Huntable-CTI-Studio && python3 -m mkdocs build --strict 2>&1
```

If the venv doesn't have mkdocs, use `./run_mkdocs.sh` which handles venv setup automatically.

**This step is a gate.** If `mkdocs build --strict` fails:
- Read the error output
- Fix broken links, missing nav references, or malformed markdown
- Rebuild and repeat until it passes
- Report what was broken and how you fixed it

### Step 6: Report

Summarize what was updated:
- Changelog entries added (count by category)
- Doc pages updated or created (list with brief reason)
- Nav entries added to mkdocs.yml (if any)
- Build result (pass, or what was fixed)

Do NOT commit or push. The user manages git workflow separately.

---

## Full true-up mode

Trigger this mode when the user asks for a "full true-up", "full doc review", "deep doc sync", "weekly doc alignment", or "audit the docs". This is the heavy-duty version — an end-to-end code-to-docs reconciliation.

### Why this mode exists

Small changes accumulate. The standard run catches drift from recent commits; the full true-up catches everything else — stale examples, removed features still documented, version numbers that drifted, internal links that broke.

### Process

Execute in order. Complete each step before starting the next. Verify claims against code before rewriting docs.

**1. Factual consistency audit**

For every file under `docs/`, compare its claims against current code:
- CLI flags and commands: run with `--help` or read argparse/click definitions
- API endpoints: check `src/web/routes/__init__.py` and route modules
- Configuration keys: check `src/config/workflow_config_schema.py`
- Environment variables: check code, Docker Compose files, `.env.example`
- File paths and function names: verify they exist

**2. Dependency and version drift**

Cross-reference versions and package names across:
- `pyproject.toml` / `requirements*.txt`
- `Dockerfile` / `docker-compose*.yml`
- Any docs that mention specific versions or dependency names

**3. Stale or redundant content**

Identify docs that:
- Reference removed features, deprecated APIs, or deleted files
- Duplicate content better covered elsewhere (prefer cross-reference over duplication)
- Contain internally conflicting information

**4. README and CLI alignment**

- README quick-start matches actual `./start.sh` / `./setup.sh` behavior
- CLI `--help` output matches `docs/reference/cli.md`
- API route docstrings match `docs/reference/api.md`

**5. Internal link sweep**

Check that all markdown links (`[text](path.md)`) resolve to existing files. Check that backticked code references (file paths, function names) still exist in the codebase.

**6. Per-issue report**

For each inaccuracy:
- **Where:** file and section
- **Issue:** what's wrong
- **Source of truth:** what the code/config actually says
- **Fix:** the specific correction applied (or proposed, if it needs human judgment)

**7. Summary**

- **Accurate:** files/sections confirmed up to date
- **Updated:** files changed, with brief reason per file
- **Needs human:** issues outside the autonomy envelope (ambiguous intent, multiple valid approaches)

---

## Guardrails

- Never modify `AGENTS.md` or `CLAUDE.md`
- Never commit or push — the user manages git separately
- Never add stylistic polish (rewording for "flow", restructuring for aesthetics) unless explicitly asked
- Never invent documentation for features you haven't verified exist in the code
- Never run dependency or security checks — those belong to other workflows
- Never add speculative "coming soon" or "planned" content
- Root `CHANGELOG.md` is a redirect to `docs/CHANGELOG.md` — don't add entries to the root file
