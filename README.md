# Huntable CTI Studio

The documentation has been reorganized under `/docs` and is published with MkDocs Material.

- **Quickstart**: `docs/quickstart.md` (Docker-first run, ingest → workflow → Sigma → pytest)
- **Docs site**: `mkdocs serve` to preview locally; navigation mirrors `/docs` (concepts, how-tos, reference, internals).
- **UI**: http://localhost:8001 (OpenAPI at `/docs`; LangGraph debug port on `:2024` when that service is enabled)
- **Stack**: FastAPI + PostgreSQL/pgvector + Redis + Celery + optional LangGraph server; start with `./start.sh`.

For full details, begin at `docs/index.md`.
