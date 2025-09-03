# CTI Scraper

Modern threat intelligence collection and analysis platform. Collects articles from security sources (RSS and web), processes and deduplicates content, stores it in a database, and exposes a FastAPI web UI and APIs, runs scheduled background tasks with Celery.

## Highlights

- RSS + web scraping with structured-data extraction and CSS fallbacks
- Content processing: cleaning, normalization, hashing, deduplication, quality scoring
- Async FastAPI app with dashboards, list/detail pages, and JSON APIs
- PostgreSQL storage via SQLAlchemy (async for web, sync for CLI)
- Celery workers for periodic source checks and collection

## Repository Layout

```
src/
├── web/                 # FastAPI app (templates in templates/)
├── core/                # Ingestion: RSS parser, modern/legacy scrapers, fetcher, processor
├── database/            # ORM models + managers (async + sync)
├── models/              # Pydantic domain models
├── worker/              # Celery app + config
├── utils/               # HTTP client, content utilities
└── cli/                 # Rich-based CLI commands

config/
├── sources.yaml         # Source definitions (identifiers, RSS, scraping config)

tests/                   # Unit/integration tests
nginx/                   # Reverse proxy config (docker)
docker-compose.yml       # Full stack: Postgres, Redis, web, workers, Nginx
```

## Quick Start

### Run the full stack (recommended)

Requires Docker. This brings up PostgreSQL, Redis, FastAPI web, Celery worker/beat, and Nginx.

```bash
docker compose up --build -d
# or use the helper script
./start_production.sh
```

Services once healthy:
- Web UI: http://localhost:8000
- Health: http://localhost:8000/health
- API: http://localhost:8000/api/*
- Nginx (optional): http://localhost

### Local development (web app)

The web app expects PostgreSQL (async). Either reuse the compose Postgres or point to your own:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+asyncpg://cti_user:cti_password_2024@localhost:5432/cti_scraper"
uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8000 --reload
```

### Local development (CLI only)

The CLI can run against SQLite by default (file `threat_intel.db`), or the same PostgreSQL instance as the web app.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Example: initialize sources from YAML
python -m src.cli.main init --config config/sources.yaml

# Collect content (RSS → modern scraping → legacy scraping)
python -m src.cli.main collect --tier 1 --dry-run

# Monitor continuously
python -m src.cli.main monitor --interval 300 --max-concurrent 5

# Analyze for techniques (TTPs)
python -m src.cli.main analyze --recent 10 --format text --quality

# Export articles
python -m src.cli.main export --format json --days 7 --output export.json
```

## Web Application

- Routes
  - `/` dashboard with basic stats and recent items
  - `/articles` list with search, filters, and pagination
  - `/articles/{id}` detail with optional TTP and quality analysis
  - `/analysis` aggregate analysis and quality distributions
  - `/sources` source management page

- JSON APIs
  - `GET /health` – service status
  - `GET /api/articles[?limit=N]` – list articles
  - `GET /api/articles/{id}` – article detail
  - `GET /api/sources` – list sources (supports filters)
  - `GET /api/sources/{id}` – source detail
  - `POST /api/sources/{id}/toggle` – toggle active status
  - `GET /api/sources/{id}/stats` – basic computed stats

## Ingestion & Processing

- RSS ingestion: `src/core/rss_parser.py` (feedparser + content extraction)
- Modern scraping: `src/core/modern_scraper.py` (JSON‑LD/opengraph/microdata + CSS selectors)
- Legacy fallback: basic CSS extraction
- Orchestration: `src/core/fetcher.py` (tiered strategy)
- Processing: `src/core/processor.py` (normalize, content hash + fingerprint, dedupe, quality checks)
- HTTP: `src/utils/http.py` (rate limiting, conditional GETs, optional robots.txt)

## Background Tasks (Celery)

The Celery app in `src/worker/celery_app.py` defines tasks to:
- Check all sources on a schedule
- Collect content from a specific source
- Cleanup/maintenance and daily reports

In Docker: `cti_worker` (worker) and `cti_scheduler` (beat) are started automatically. Outside Docker, run:

```bash
celery -A src.worker.celery_app worker --loglevel=info
celery -A src.worker.celery_app beat --loglevel=info
```

## Configuration

- `config/sources.yaml`: define sources with identifiers, URLs, optional RSS, and scraping config. Example snippet:

```yaml
version: "1.0"
sources:
  - id: "thehackernews"
    name: "The Hacker News"
    url: "https://thehackernews.com/"
    rss_url: "https://feeds.feedburner.com/TheHackersNews"
    tier: 1
    weight: 1.0
    check_frequency: 3600
    active: true
```

- Environment variables (commonly via `.env` or compose):
  - `DATABASE_URL` (web requires PostgreSQL async: `postgresql+asyncpg://...`)
  - `REDIS_URL` (for Celery broker/results)
  - `ENVIRONMENT`, `LOG_LEVEL`

## Database Access

For direct database queries and data analysis, see the [Database Query Guide](DATABASE_QUERY_GUIDE.md) for:

- Connection details and authentication
- Common SQL queries for articles and sources
- Database schema documentation
- Export and backup procedures
- Performance optimization tips

Quick example:
```bash
# View recent articles
docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "
SELECT a.title, s.name as source, a.published_at 
FROM articles a 
JOIN sources s ON a.source_id = s.id 
ORDER BY a.created_at DESC 
LIMIT 10;"
```

## Tests

```bash
pytest -q
```

Note: some tests (e.g., web app tests) assume a running instance at `http://localhost:8000`. Use Docker Compose or run uvicorn locally before executing integration tests.

## License

MIT License – see [LICENSE](LICENSE).

## Notes

- This project is for research and operational TI collection. Always respect websites’ terms and robots.txt where applicable.
- The previous simplified “pipeline-only” docs are obsolete; this README reflects the current FastAPI + PostgreSQL + Celery architecture.
