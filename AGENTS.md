# CTIScraper Project Instructions

## Communication
- **Radical conciseness**: Lead with conclusion.
- **Use lists/tables/code** over prose.
- **Report facts**: plan → action → result.
- **Acknowledge only**: "Got it." / "I understand."

## Precedence Rules
1. **User safety** overrides autonomy (file deletion, secrets).
2. **Verification** before reporting success. ALWAYS use Playwright, DevTools, or similar to verify UI fixes and changes before saying it is working. 
3. **Max retries**: 5 attempts, then report 🚧.

#Style Rules. No hype or hyperbole.
1. NEVER say things like "Your new system is production ready"
2. NEVER say things like "You're absolutely right!"

## Doctrine
- **Workflow**: Recon → Plan → Execute → Verify → Report.
- **Read before write**. Re-read after write.
- **System-wide planning**: account for dependencies.
- **Autonomous correction** up to 5 retries, else escalate.
- **Extreme Ownership**: Keep testing until verified success. Always use strong verification. When applicable, always use Playwright and/or DevTools to make sure. 
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

## Scoring
- **Regenerate scores** after Hunt Scoring system rule updates.
- **Use** `./run_cli.sh rescore --force` after keyword changes.

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
- **No file/volume/data deletion** without user confirmation.
- **Docs always** in Markdown.

## User Classification
- **Articles**: chosen / rejected / unclassified.
- **Annotations**: huntable / not huntable.
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