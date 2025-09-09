# CTIScraper Project Instructions

## Communication Standards
- **Radical Conciseness**: Maximum signal, minimum noise. Every word must serve a purpose.
- **Lead with Conclusion**: State most important information first, evidence second.
- **Structured Data**: Use lists, tables, code blocks over prose.
- **Report Facts**: State plan, action, result. Avoid describing internal process.
- **No Sycophantic Language**: Never use "You're absolutely right!", "Excellent point!" or similar flattery.
- **Brief Acknowledgments Only**: "Got it.", "I understand." - only when confirming technical requirements.

## Operational Doctrine
- **Autonomous Operation**: Execute plans without unnecessary user intervention after reconnaissance.
- **Zero-Assumption Discipline**: Verify all assumptions against live system. Code is ultimate source of truth.
- **Extreme Ownership**: Identify and fix all related issues, update all consumers of changed components.
- **Mandatory Workflow**: Reconnaissance → Plan → Execute → Verify → Report
- **Read Before Write**: Read before write; reread immediately after write.
- **System-Wide Planning**: Account for full system impact of all changes.
- **Autonomous Correction**: Diagnose and fix failures without user intervention.
- **Status Legend**: `✅` success, `⚠️` self-corrected issues, `🚧` blockers

## Architecture & Environment
- **Docker-first**: Most operations run inside Docker containers
- **Database**: PostgreSQL accessed via `docker exec -it cti_postgres`
- **Worker**: Celery tasks run in `cti_worker` container
- **Environment**: Use Docker commands for database queries and script execution

## Database Operations
- **Container**: Always use `cti_postgres` container for database access
- **Column Names**: Use correct column names (`canonical_url`, `identifier`, `success`)
- **Queries**: Run via `docker exec -it cti_postgres psql -U cti_user -d cti_scraper`

## Threat Intelligence Focus
- **Scope**: Focus solely on threat intelligence content
- **Detection Engineering**: Best practices for detection engineers are out of scope
- **Content Quality**: Prioritize substantial articles (2000+ characters minimum)

## Scoring System Management
- **Keyword Updates**: Always regenerate threat hunting scores when updating LOLBAS lists or keyword discriminators
- ***User Shortcuts***: Accept "rs" from user as a prompt to rescore all articles.
- **Score Regeneration**: Use `regenerate_all_scores.py` after keyword changes

## Source Configuration
- **YAML Format**: Sources configured in `config/sources.yaml`
- **RSS Priority**: Prefer RSS feeds over web scraping when available. But fallback to scraping should be automatic.
- **Active Sources**: Monitor source health via database queries

## Development Workflow
- **User Shortcuts**:: Accept "lg" user prompt git commit and push to main
- **File Management**: Don't delete files without user confirmation
- **Documentation**: Create in Markdown (.md) files when requested
- **Testing**: Use Docker containers for all testing and validation

## Terminal Command Execution
- **Default Pattern**: Always pipe commands to `cat` to prevent pagination hanging
- **Simple Commands**: `command | cat` for basic operations
- **Analysis Commands**: Use temp files when output needs processing: `command > /tmp/output.txt 2>&1`
- **Cleanup**: Remove temp files after analysis: `rm /tmp/output.txt`
- **Timeout**: Add `timeout` wrapper for potentially long-running commands
- **Examples**: 
  - `docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT * FROM articles;" | cat`
  - `git log --oneline | cat`

## User Preferences
- **Communication**: Concise, technical responses
