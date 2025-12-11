# CTI Scraper Documentation

Use this index to find accurate docs for the current codebase.

## Directory Structure (current)
```
docs/
├── deployment/            # Docker + setup
├── development/           # Dev and testing guides
├── features/              # Feature-specific docs
├── operations/            # Backup/source management/verification
├── archive/               # Historical notes
├── API_ENDPOINTS.md       # REST API reference
├── RAG_SYSTEM.md          # RAG design and usage
├── LANGGRAPH_INTEGRATION.md / LANGGRAPH_QUICKSTART.md
├── WORKFLOW_DATA_FLOW.md  # Pipeline flow
└── README.md              # This index
```

## Quick Navigation
- Getting started: `../README.md` → `deployment/GETTING_STARTED.md`
- Architecture: `deployment/DOCKER_ARCHITECTURE.md`
- Docker/ports: `development/PORT_CONFIGURATION.md`
- Dev setup: `development/DEVELOPMENT_SETUP.md`
- Testing: `../tests/TESTING.md`, `../tests/QUICK_START.md`, `development/WEB_APP_TESTING.md`
- Backup/restore: `operations/BACKUP_AND_RESTORE.md`
- Sources config: `operations/SOURCE_CONFIG_PRECEDENCE.md`, `config/sources.yaml`
- AI/Workflow: `RAG_SYSTEM.md`, `LANGGRAPH_INTEGRATION.md`, `LANGGRAPH_QUICKSTART.md`, `WORKFLOW_DATA_FLOW.md`
- SIGMA/OS detection/content filtering: files under `features/`

## Contributing
- Add new docs to the right subdir.
- Update this README and `../docs/DOCUMENTATION.md` when adding/removing files.
- Keep examples aligned with `docker-compose.yml`, `Dockerfile`, and current CLI (`./run_cli.sh --help`).

_Last verified: Dec 2025_
