# CTIScraper Project Instructions

## Communication
- **Radical conciseness**: Lead with conclusion.
- **Use lists/tables/code** over prose.
- **Report facts**: plan → action → result.
- **Acknowledge only**: "Got it." / "I understand."

## Precedence Rules
1. **User safety** overrides autonomy (file deletion, secrets).
2. **Verification** before reporting success.
3. **Max retries**: 3 attempts, then report 🚧.

## Doctrine
- **Workflow**: Recon → Plan → Execute → Verify → Report.
- **Read before write**. Re-read after write.
- **System-wide planning**: account for dependencies.
- **Autonomous correction** up to 3 retries, else escalate.
- **Extreme Ownership**: Keep testing until verified success.
- **Status**: ✅ success | ⚠️ self-corrected | 🚧 blocker.

## Environment
- **Docker-first**.
- **DB**: `cti_postgres` container, `psql -U cti_user -d cti_scraper`.
- **Worker**: Celery in `cti_worker`.

## Database
- **Always use** `cti_postgres`.
- **Key columns**: `canonical_url`, `identifier`, `success`.
- **Schema context**:
  - `articles.classification` → chosen/rejected/unclassified
  - `annotations.label` → huntable/not huntable
  - `annotations.article_id` → links annotations to articles

## Threat Intel Scope
- **Focus**: threat intel only.
- **SIGMA rule generation** + pySigma validation (≤3 attempts).
- **Detection engineering best practices**: out of scope.

## Scoring
- **Regenerate scores** after LOLBAS/keyword updates.
- **Use** `./run_cli.sh rescore` after keyword changes.
- **Sync** `src/utils/content_filter.py` when keywords change.
- **Shortcut**: `rs` = rescore all articles (via CLI).

## Sources
- **Config**: `config/sources.yaml`.
- **Prefer RSS**; automatic fallback to scraping.
- **Monitor source health** in DB.

## User Shortcut Commands
- **`lg`** = commit + push + full GitHub hygiene:
  - **Security & Setup**: Scan for hardcoded credentials/API keys, create comprehensive .gitignore, add .env.example, move config to external files
  - **Dependency Security**: Check requirements for latest versions and CVE vulnerabilities, update if patches available, alert if no patches
  - **Documentation & Standards**: Create professional README.md, add LICENSE (MIT), pin dependencies, add type hints/docstrings, remove debug prints
  - **Repository Files**: Add Update CHANGELOG.md
  - **Final Verification**: Ensure no secrets in code, comprehensive .gitignore, professional README, proper license, documented dependencies/code
- **`lgl`** = commit + push (lite).
- **`mdu`** = update all MD docs to match codebase.
- **`rs`** = rescore all articles (via CLI).

## Dev Workflow
- **No file deletion** without confirmation.
- **Docs always** in Markdown.

## Command Execution
- **Default**: `command | cat` to avoid paging.
- **Long output**: `> /tmp/out.txt`; clean with `rm`.
- **Add timeout wrapper**: `timeout 30s command`.
- **Always check exit codes**: `$?` after each command.
- **Examples**:
  - `docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT * FROM articles;" | cat`
  - `git log --oneline | cat`

## Classification
- **Articles**: chosen / rejected / unclassified.
- **Chunks**: huntable / not huntable.
- **Never mix**.

### Clarification Protocol
1. **Identify confusion**.
2. **Explain distinction**.
3. **Offer correct alternative**.

## Web App Testing
- **Primary**: Docker Playwright E2E.
- **Dev**: IDE MCPs for debugging.
- **Comprehensive Guide**: See `WebAppDevtestingGuide.md` for:
  - Tool selection and usage patterns
  - Development workflows and best practices
  - Debugging strategies and troubleshooting
  - CTIScraper-specific test scenarios
  - Performance optimization and quality assurance
- **CI/CD**: GitHub Actions.
- **Artifacts**: save videos, traces, reports.
- **Key areas**: source mgmt, article processing, API, UI, perf, accessibility.