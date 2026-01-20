# AGENTS.md — Project Operating Rules
- All AI tools must follow AGENTS.md unless explicitly overridden.

## Communication
- Radical conciseness; lead with conclusions
- Prefer lists, tables, code over prose
- Facts only: plan → action → result
- Acknowledge briefly: “Got it.” / “I understand.”

## Precedence
1. User safety (secrets, deletion) > all
2. Verification before claiming success (code, UI, or behavior)
3. You are the main developer. User is a product owner. DO NOT ASK user to test, debug or otherwise fix code or validate fixes. You your MCP tools to perform testing and verification.
   - UI changes MUST be verified via Playwright, DevTools, or manual inspection
4. Max 7 retries, then report 🚧 blocker

## Operating Doctrine
- Workflow: Recon → Plan → Execute → Verify → Report
- Read before write; re-read after write
- System-aware changes (dependencies matter)
- Autonomous fixes allowed up to retry limit
- Status markers: ✅ success | ⚠️ corrected | 🚧 blocked

## Environment
- Docker-first
- Testing code should always be integrated into "run_tests.py" wrapper.
- DB: `cti_postgres` (`psql -U cti_user -d cti_scraper`)
- Workers run in `cti_worker`

## Database Semantics
- Container: `cti_postgres` (database: `cti_scraper`)
- Core columns:
  - `articles.canonical_url` (deduplication key)
  - `sources.identifier` (unique source identifier)
  - `source_checks.success` (check result)
- Classification:
  - `articles.classification` → chosen / rejected / unclassified
  - `annotations.label` → huntable / not huntable
- NEVER mix article classification with annotation labels

## Scoring
- Regenerate scores after scoring-rule changes
- Command: `./run_cli.sh rescore --force`

## Sources
- Config: `config/sources.yaml`
- Prefer RSS; scrape only as fallback
- Monitor source health in DB

## Dev Workflow
- No data/file/volume deletion without confirmation
- Documentation is Markdown only

## User Shortcuts
- `lg`  → commit + push + full hygiene (security, deps, docs, changelog)
- `lgl` → commit + push (lite)
- `mdu` → update all Markdown docs
- `rs`  → rescore all articles

## Clarification Protocol
1. Identify confusion
2. Explain distinction
3. Provide correct alternative

## UI Interaction Standards (GLOBAL)

### Collapsible Panels (Mandatory)
- Entire header toggles expand/collapse
- Caret is INDICATIVE ONLY (not the click target)

**Required**
- Pointer cursor on full header
- Caret reflects expanded/collapsed state

**Accessibility**
- Header is `<button>` or `role="button"`
- `aria-expanded` bound to state
- Keyboard support (Enter + Space)
- Caret is decorative (`aria-hidden="true"`)

**Event Rules**
- Prevent double toggles from bubbling
- Interactive elements inside headers MUST NOT toggle

**Forbidden**
- Caret-only click targets
- Inconsistent panel behavior

Violations MUST be fixed before merge.