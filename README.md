# CTI Scraper

Modern threat intelligence collection and analysis platform. Collects articles from security sources (RSS and web), processes and deduplicates content, stores it in a database, and exposes a FastAPI web UI and APIs, runs scheduled background tasks with Celery.

## Highlights

- RSS + web scraping with structured-data extraction and CSS fallbacks
- Content processing: cleaning, normalization, hashing, deduplication, quality scoring
- Async FastAPI app with dashboards, list/detail pages, and JSON APIs
- PostgreSQL storage via SQLAlchemy (async for web, sync for CLI)
- Celery workers for periodic source checks and collection
- **Robots.txt compliance** with per-source configuration and rate limiting
- **Source tiering system** (premium/standard/basic) for priority management

## Repository Layout

```
src/
├── web/                 # FastAPI app (templates in templates/)
│   ├── modern_main.py   # Main FastAPI application
│   ├── templates/       # HTML templates
│   └── static/          # Static assets
├── core/                # Ingestion: RSS parser, modern/legacy scrapers, fetcher, processor
│   ├── rss_parser.py    # RSS/Atom feed parser
│   ├── modern_scraper.py # JSON-LD and structured data extraction
│   ├── fetcher.py       # Hierarchical content fetcher
│   ├── processor.py     # Content processing pipeline
│   ├── source_manager.py # Source configuration management
│   ├── features/        # Feature extraction modules
│   └── models/          # Core-specific models
├── database/            # ORM models + managers (async + sync)
│   ├── models.py        # SQLAlchemy models
│   ├── async_manager.py # Async database manager
│   └── manager.py       # Sync database manager
├── models/              # Pydantic domain models
│   ├── source.py        # Source models (with tier support)
│   └── article.py       # Article models
├── worker/              # Celery app + config
├── utils/               # HTTP client, content utilities
│   └── http.py          # Enhanced HTTP client with robots.txt support
└── cli/                 # Rich-based CLI commands
    └── main.py          # CLI interface

config/
├── sources.yaml         # Source definitions (identifiers, RSS, scraping config, robots rules)
├── models.yaml          # Model configuration
└── recommended_models.yaml # Recommended model settings

tests/                   # Unit/integration tests
├── api/                 # API tests
├── ui/                  # UI tests
├── integration/         # Integration tests
├── unit/                # Unit tests
└── utils/               # Test utilities

nginx/                   # Reverse proxy config (docker)
├── nginx.conf           # Nginx configuration
└── ssl/                 # SSL certificates

docker-compose.yml       # Full stack: Postgres, Redis, web, workers, Nginx
```

## Quick Start

### Run the full stack (Docker)

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

### CLI Commands (via Docker)

Run CLI commands through Docker:

```bash
# Example: initialize sources from YAML
docker compose exec web python -m src.cli.main init --config config/sources.yaml

# Collect content (RSS → modern scraping → legacy scraping)
docker compose exec web python -m src.cli.main collect --dry-run

# Monitor continuously
docker compose exec web python -m src.cli.main monitor --interval 300 --max-concurrent 5

# Export articles
docker compose exec web python -m src.cli.main export --format json --days 7 --output export.json
```

## Web Application

- Routes
  - `/` dashboard with basic stats and recent items
  - `/articles` list with search, filters, and pagination
  - `/articles/{id}` detail with optional TTP and quality analysis
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
- Orchestration: `src/core/fetcher.py` (multi-strategy)
- Processing: `src/core/processor.py` (normalize, content hash + fingerprint, dedupe, quality checks)
- HTTP: `src/utils/http.py` (rate limiting, conditional GETs, **robots.txt compliance with per-source configuration**)

## Robots.txt Compliance & Rate Limiting

The platform now includes comprehensive robots.txt compliance and rate limiting:

- **Per-source robots.txt configuration** in `config/sources.yaml`
- **Automatic rate limiting** based on robots.txt crawl-delay directives
- **Configurable request limits** per source (requests per minute)
- **User agent customization** per source
- **Lenient enforcement** - logs warnings but allows requests for research purposes

Example robots configuration:
```yaml
robots:
  enabled: true
  user_agent: "CTIScraper/2.0"
  respect_delay: true
  max_requests_per_minute: 10
  crawl_delay: 1.0
```

## Background Tasks (Celery)

The Celery app in `src/worker/celery_app.py` defines tasks to:
- Check all sources on a schedule
- Collect content from a specific source
- Cleanup/maintenance and daily reports

In Docker: `cti_worker` (worker) and `cti_scheduler` (beat) are started automatically.

## Configuration

- `config/sources.yaml`: define sources with identifiers, URLs, optional RSS, scraping config, and robots.txt rules. Example snippet:

```yaml
version: "1.0"
sources:
  - id: "thehackernews"
    name: "The Hacker News"
    url: "https://thehackernews.com/"
    rss_url: "https://feeds.feedburner.com/TheHackersNews"
    tier: 2  # Source tier (1=premium, 2=standard, 3=basic)
    check_frequency: 3600
    active: true
    robots:
      enabled: true
      user_agent: "CTIScraper/2.0"
      respect_delay: true
      max_requests_per_minute: 10
      crawl_delay: 1.0
```

- `config/models.yaml`: Model configuration for content processing
- `config/recommended_models.yaml`: Recommended model settings for different use cases

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

- This project is for research and operational TI collection. Always respect websites' terms and robots.txt where applicable.
- **Robots.txt compliance is now enabled by default** with configurable per-source settings.
- **Source tiering system** allows prioritization of premium sources (tier 1) over basic sources (tier 3).
- The previous simplified "pipeline-only" docs are obsolete; this README reflects the current FastAPI + PostgreSQL + Celery architecture.
