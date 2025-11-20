# CTIScraper Project Instructions (with Prohibited Commands / Behaviors)

communication:
  radical_conciseness: "Lead with conclusion."
  format_preference: "Use lists, tables, or code over prose."
  reporting_style: "Plan → Action → Result."
  acknowledgement_only: ["Got it.", "I understand. Use acknowledgement_only when the user sends single-sentence confirmations, not tasks."]

precedence_rules:
  - "User safety overrides autonomy (no file deletion, no secrets exposure)."
  - "Always validate your code before you finish. For UI features, ALWAYS verify with Playwright or DevTools before stating ready for user. Validation = run tests relevant to the change (unit/UI/E2E) and inspect diff for unintended effects"
  - "Max retries: 7 total. After 7 retries, provide status report and await further instructions. User instructions override this limit (e.g., 'keep trying until done')."

style_rules:
  - "No hype or hyperbole."
  - "Never say phrases like 'Your system is production ready' or 'You're absolutely right!'."
  - "Maintain factual tone and professional language."
  - "Don't tell user how the app 'should' behave until you have verified with your own testing."

doctrine:
  workflow: "Recon → Plan → Execute → Verify → Report."
  principles:
    - "Read before write, re-read after write."
    - "Account for dependencies system-wide."
    - "Autonomous correction up to 7 retries. After 7 retries, provide status report and await further instructions. User instructions override this limit."
    - "Extreme Ownership: NEVER tell user a feature is ready or "should" work. You must verify. If the change affects UI, verify with Playwright. Otherwise run unit tests."
  status_indicators:
    success: "✅"
    self_corrected: "⚠️"
    blocker: "🚧"

environment:
  docker_first: true
    - When building application code it will always be run in Docker. 
    - When writing scripts, tests or other utilities, you may use local python venv.
      - Temporary scripts should be saved under utils/temp/ 
  database:
    container: "cti_postgres"
    name: "cti_scraper"
    user: "cti_user"
    connect: "psql -U cti_user -d cti_scraper"
  worker:
    name: "cti_worker"
    framework: "Celery"

database_rules:
  enforce: 
    - "Use cti_postgres container, cti_scraper database only."
    - "Agents must not create new columns or tables without user request. This includes both direct schema changes and migrations (Alembic), unless user explicitly requests it (e.g., 'run the migration script')."
  key_columns:
    articles: ["canonical_url", "content_hash"]
    sources: ["identifier"]
    source_checks: ["success"]
  schema_context:
    articles.classification: "Stored in article_metadata.training_category JSON field: ['chosen', 'rejected', 'unclassified']"
    annotations.annotation_type: ["huntable", "not_huntable"]
    annotations.article_id: "links annotations to articles"

ux_guidelines:
  theme: 
    - "Dark mode across all pages and panels."
    - "Use white or light grey text when background is dark."
  modals:
    - "Escape key and click-away must always close active modal."
    - "Inputs submit on 'Enter' key."
  layout:
    - "Responsive tables and scrollable overflow on narrow viewports."
    - "Consistent spacing and contrast for accessibility."
  UX:
    - "LMStudio model select dropdowns must list model names in alphabetical order."

scoring_rules:
  regenerate_after: "Any hunt scoring system or keyword rule updates."
  command: "./run_cli.sh rescore --force"
  trigger: "User or Celery worker following rule updates."

sources:
  config_file: "config/sources.yaml"
  preferences:
    - "Prefer RSS; fallback to scraping when unavailable."
    - "Monitor source health in database."

user_shortcuts:
  mdu:
    description: "Update all Markdown documentation to reflect current codebase."
  lg:
    description: "Commit + push with full GitHub hygiene."
    workflow:
      - "Run mdu to sync Markdown docs post-update."
      - "If modifying functions with branching logic or new CLI/API endpoints (smoke, UI, E2E), pause and suggest required pytest updates. Ask user if they want you to write those tests before proceeding."
      - "Scan for hardcoded secrets or credentials. Do not proceed if found."
      - "Ensure .gitignore and .env.example completeness."
      - "Check dependency versions and CVEs; update if possible."
      - "Update README.md, LICENSE, CHANGELOG.md."
      - "Add docstrings, type hints, and remove debug prints."
      - "Verify repository cleanliness before final commit."
  lgl:
    description: "Commit + push (lite, minimal checks)."
  rs:
    description: "Rescore all articles via CLI. Use --force"
  bs: 
    description: "BE SURE! Don't tell user things are done when you haven't tested them. Use tools available like curl, playwright, browsertools, etc. to validate completion before telling user it is ready for use/testing"

dev_workflow:
  safety: "Never delete files, volumes, or data without user confirmation."
  documentation: "All docs must be in Markdown."
  strong_prohibition: “Never rename directories.”

classification:
  articles: ["chosen", "rejected", "unclassified"]
  annotations: ["huntable", "not_huntable"]
  enforcement: 
    - "Never mix article and annotation classification types."
    - "Classifications are only set by application users. Never infer or auto-assign classifications."

clarification_protocol:
  steps:
    - "Identify confusion."
    - "Explain the distinction clearly."
    - "Offer a correct alternative."
    - "Confirm understanding before proceeding."
    - “Limit to 1 question per clarification at a time. Iterate through until you have what you need from user.”

error_handling:
  hierarchy:
    critical: "Requires immediate stop and alert user."
    non_critical: "Retry automatically up to 7 times. After 7 retries, provide status report and await further instructions. User instructions override this limit."
    deferred: "Log for later review."
  output_schema:
    format: "JSON"
    fields: ["status", "attempts", "verification_evidence", "timestamp"]

prohibited_commands:
  precedence: "Overrides any allow-listed command or shortcut. Non-bypassable."
  rationale: "Prevents destructive or unsafe operations regardless of user intent."
  commands:
    - pattern: "rm -rf /"                           # Prevent full system deletion
    - pattern: "docker system prune -a"             # Prevent complete Docker wipe
    - pattern: "docker volume rm .*"                # Prevent volume deletions
    - pattern: "docker volume prune"                # Prevent all volume pruning
    - pattern: "docker compose down -v"             # Prevent volume removal in compose teardown
    - pattern: "drop database"                      # Prevent database destruction
    - pattern: "DELETE FROM .*"                     # Block all DELETE statements. Must ask for permission.
    - pattern: "git push --force"                   # Prevent overwriting remote history
    - pattern: "playwright test --headed"           # Disallow headed mode in CI/CD
    - pattern: "git reset --hard"
    - pattern: "docker compose down --rmi all"
    - pattern: "truncate table .*"
    - pattern: "drop table .*"

  behaviors:
    - "Never modify files outside project root."
    - "Never rename directories."
    - "Never commit secrets or API keys."
    - "Never run with elevated privileges unless explicitly required."
    - "Never bypass verification checks before success report."
    - "Never overwrite configuration files without user confirmation."
    - "Never delete or recreate Docker volumes without user confirmation."
  enforcement:
    action_on_violation: "halt"
    report_to_user: true
    log_path: "logs/security_policy_violations.log"

web_app_testing:
  primary: "Playwright E2E within Docker."
  dev_tools: "Cursor IDE MCPs for debugging."
  reference_doc: "WebAppDevtestingGuide.md"
  coverage:
    - "Source management"
    - "Article processing"
    - "API endpoints"
    - "UI interactions"
    - "Performance and accessibility"
  artifacts: ["videos", "traces", "reports"]