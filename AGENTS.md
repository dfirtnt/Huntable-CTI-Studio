# CTIScraper Project Instructions (with Prohibited Commands / Behaviors)

communication:
  radical_conciseness: "Lead with conclusion."
  format_preference: "Use lists, tables, or code over prose."
  reporting_style: "Plan → Action → Result."
  acknowledgement_only: ["Got it.", "I understand."]

precedence_rules:
  - "User safety overrides autonomy (no file deletion, no secrets exposure)."
  - "Always validate your code before you finish. For UI features, ALWAYS verify with Playwright or DevTools before stating ready for user."
  - "Max retries: 7 total (5 autonomous retries, then escalate)."

style_rules:
  - "No hype or hyperbole."
  - "Never say phrases like 'Your system is production ready' or 'You're absolutely right!'."
  - "Maintain factual tone and professional language."

doctrine:
  workflow: "Recon → Plan → Execute → Verify → Report."
  principles:
    - "Read before write, re-read after write."
    - "Account for dependencies system-wide."
    - "Autonomous correction up to 5 retries before escalation."
    - "Extreme Ownership: Verify with Playwright/DevTools before success."
  status_indicators:
    success: "✅"
    self_corrected: "⚠️"
    blocker: "🚧"

environment:
  docker_first: true
  database:
    name: "cti_postgres"
    connect: "psql -U cti_user -d cti_scraper"
  worker:
    name: "cti_worker"
    framework: "Celery"

database_rules:
  enforce: "Use cti_postgres only."
  key_columns: ["canonical_url", "identifier", "success"]
  schema_context:
    articles.classification: ["chosen", "rejected", "unclassified"]
    annotations.label: ["huntable", "not huntable"]
    annotations.article_id: "links annotations to articles"

ux_guidelines:
  theme: "Dark mode across all pages and panels."
  modals:
    - "Escape key and click-away must close modals."
    - "Inputs submit on 'Enter' key."
  layout:
    - "Responsive tables and scrollable overflow on narrow viewports."
    - "Consistent spacing and contrast for accessibility."

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
    run_context: "Repository root only."
    workflow:
      - "Run mdu to sync Markdown docs post-update."
      - "Assess if updates require new or modified tests (smoke, UI, E2E). If yes, pause and prompt user."
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

dev_workflow:
  safety: "Never delete files, volumes, or data without user confirmation."
  documentation: "All docs must be in Markdown."

classification:
  articles: ["chosen", "rejected", "unclassified"]
  annotations: ["huntable", "not huntable"]
  enforcement: "Never mix article and annotation classification types."

clarification_protocol:
  steps:
    - "Identify confusion."
    - "Explain the distinction clearly."
    - "Offer a correct alternative."
    - "Confirm understanding before proceeding."

error_handling:
  hierarchy:
    critical: "Requires immediate stop and alert user."
    non_critical: "Retry automatically up to 5 times."
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
    - pattern: "DELETE FROM .*"                     # Block direct SQL deletes without WHERE clause
    - pattern: "git push --force"                   # Prevent overwriting remote history
    - pattern: "playwright test --headed"           # Disallow headed mode in CI/CD
  behaviors:
    - "Never modify files outside project root."
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