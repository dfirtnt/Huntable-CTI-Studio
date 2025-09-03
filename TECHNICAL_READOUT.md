# CTI Scraper - Technical Readout

## Project Overview

**CTI Scraper** is a modern threat intelligence collection and analysis platform designed to aggregate, process, and analyze cybersecurity content from multiple sources. The system provides both automated collection capabilities and a web-based interface for threat intelligence analysts.

### Core Mission
- **Collect**: Automatically gather threat intelligence articles from RSS feeds and web scraping
- **Process**: Clean, normalize, deduplicate, and quality-score content
- **Analyze**: Extract threat techniques, tactics, and procedures (TTPs)
- **Present**: Provide web interface and APIs for threat intelligence consumption

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │  Web Interface  │    │   Background    │
│                 │    │                 │    │     Tasks       │
│ • RSS Feeds     │───▶│ • FastAPI App   │    │ • Celery Worker │
│ • Web Scraping  │    │ • Dashboard     │    │ • Scheduler     │
│ • 24+ Sources   │    │ • Search/Filter │    │ • Collection    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PostgreSQL Database                      │
│                                                                 │
│ • Articles (content, metadata, quality scores)                 │
│ • Sources (RSS feeds, scraping config, tier classification)    │
│ • Processing results (TTPs, deduplication, analytics)          │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
CTIScraper/
├── 📁 src/                          # Main application code
│   ├── 📁 web/                      # FastAPI web application
│   │   ├── modern_main.py           # Main FastAPI app entry point
│   │   ├── 📁 templates/            # Jinja2 HTML templates
│   │   │   ├── base.html            # Base template layout
│   │   │   ├── articles.html        # Articles listing page
│   │   │   ├── article_detail.html  # Article detail view
│   │   │   ├── dashboard.html       # Main dashboard
│   │   │   ├── sources.html         # Source management
│   │   │   └── analysis.html        # Analytics page
│   │   └── 📁 static/               # CSS, JS, images
│   │
│   ├── 📁 core/                     # Core processing engine
│   │   ├── rss_parser.py            # RSS feed parsing
│   │   ├── modern_scraper.py        # Modern web scraping (JSON-LD, OpenGraph)
│   │   ├── fetcher.py               # Content fetching orchestration
│   │   ├── processor.py             # Content processing pipeline
│   │   └── source_manager.py        # Source configuration management
│   │
│   ├── 📁 database/                 # Database layer
│   │   ├── async_manager.py         # Async database operations
│   │   ├── sync_manager.py          # Sync database operations
│   │   └── models.py                # SQLAlchemy ORM models
│   │
│   ├── 📁 models/                   # Pydantic data models
│   │   ├── article.py               # Article data model
│   │   └── source.py                # Source data model
│   │
│   ├── 📁 worker/                   # Background task processing
│   │   ├── celery_app.py            # Celery application configuration
│   │   └── tasks.py                 # Background task definitions
│   │
│   ├── 📁 utils/                    # Utility functions
│   │   ├── http.py                  # HTTP client with rate limiting
│   │   ├── content.py               # Content processing utilities
│   │   └── search_parser.py         # Boolean search functionality
│   │
│   └── 📁 cli/                      # Command-line interface
│       └── main.py                  # Rich-based CLI commands
│
├── 📁 config/                       # Configuration files
│   ├── sources.yaml                 # Source definitions and scraping config
│   ├── models.yaml                  # LLM model configurations
│   └── recommended_models.yaml      # Recommended model settings
│
├── 📁 tests/                        # Test suite
│   ├── 📁 unit/                     # Unit tests
│   ├── 📁 integration/              # Integration tests
│   ├── 📁 api/                      # API tests
│   └── test_search_parser.py        # Boolean search tests
│
├── 📁 nginx/                        # Reverse proxy configuration
│   └── nginx.conf                   # Nginx configuration
│
├── 📁 backup_old_architecture/      # Legacy code (for reference)
│   ├── 📁 old_web_server/           # Previous web implementation
│   ├── 📁 old_database/             # Previous database setup
│   └── 📁 quality_assessment/       # Previous TTP extraction
│
├── 📄 docker-compose.yml            # Full stack orchestration
├── 📄 Dockerfile                    # Application containerization
├── 📄 requirements.txt              # Python dependencies
├── 📄 README.md                     # Main project documentation
├── 📄 DATABASE_QUERY_GUIDE.md       # Database access guide
├── 📄 BOOLEAN_SEARCH_IMPLEMENTATION.md # Search feature documentation
└── 📄 start_production.sh           # Production startup script
```

## Key Components Deep Dive

### 1. Web Application (`src/web/`)

**Technology Stack**: FastAPI + Jinja2 + PostgreSQL (async)

**Key Features**:
- **Dashboard**: Real-time statistics and recent articles
- **Articles Page**: Advanced search with boolean logic (AND/OR/NOT)
- **Article Detail**: Full content view with metadata
- **Source Management**: Configure and monitor data sources
- **Analytics**: Quality distribution and TTP analysis

**Notable Implementation**:
```python
# Boolean search implementation
from src.utils.search_parser import parse_boolean_search

# Supports queries like:
# "ransomware" AND "critical infrastructure" NOT basic
# malware OR virus OR trojan
# "advanced persistent threat" AND (malware OR virus)
```

### 2. Core Processing Engine (`src/core/`)

**Content Processing Pipeline**:
```
RSS Feed/Web URL → RSS Parser → Modern Scraper → Legacy Scraper → Processor → Database
```

**Key Components**:
- **RSS Parser**: Extracts article metadata from RSS feeds
- **Modern Scraper**: Uses JSON-LD, OpenGraph, and microdata for structured content
- **Legacy Scraper**: CSS selector fallback for sites without structured data
- **Processor**: Content cleaning, normalization, deduplication, quality scoring

**Quality Assessment**:
- Content length and readability scoring
- Source reputation weighting
- Technical depth analysis
- Threat intelligence relevance scoring

### 3. Database Layer (`src/database/`)

**Technology**: PostgreSQL with SQLAlchemy ORM

**Key Tables**:
```sql
-- Sources table
sources (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    url VARCHAR,
    rss_url VARCHAR,
    tier INTEGER,  -- 1=premium, 2=news
    weight FLOAT,
    active BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

-- Articles table
articles (
    id SERIAL PRIMARY KEY,
    title TEXT,
    content TEXT,
    source_id VARCHAR REFERENCES sources(id),
    canonical_url VARCHAR,
    published_at TIMESTAMP,
    created_at TIMESTAMP,
    metadata JSONB  -- Quality scores, TTPs, etc.
)
```

**Features**:
- Async operations for web application
- Sync operations for CLI and background tasks
- JSONB metadata for flexible data storage
- Full-text search capabilities

### 4. Background Processing (`src/worker/`)

**Technology**: Celery + Redis

**Tasks**:
- **Source Monitoring**: Periodic checks of all configured sources
- **Content Collection**: Automated RSS and web scraping
- **Quality Analysis**: Background content quality assessment
- **TTP Extraction**: Threat technique identification
- **Maintenance**: Database cleanup and optimization

**Scheduling**:
```python
# Example task scheduling
@celery_app.task
def check_source(source_id: str):
    """Check a specific source for new content"""
    # RSS parsing → web scraping → content processing
```

### 5. Configuration Management (`config/`)

**Source Configuration** (`sources.yaml`):
```yaml
sources:
  - id: "cisco_talos"
    name: "Cisco Talos Intelligence Blog"
    url: "https://blog.talosintelligence.com/"
    rss_url: "https://blog.talosintelligence.com/rss/"
    tier: 1  # Premium source
    weight: 2.0
    check_frequency: 1800  # 30 minutes
    active: true
    config:
      allow: ["blog.talosintelligence.com"]
      extract:
        prefer_jsonld: true
        title_selectors: ["h1", "meta[property='og:title']"]
        body_selectors: ["article", "main", ".content"]
```

**Features**:
- Tier-based source classification
- Configurable scraping rules
- Rate limiting and respect for robots.txt
- Flexible content extraction selectors

## Data Flow

### 1. Content Collection Flow
```
1. Scheduler triggers source check
2. RSS parser extracts article metadata
3. Modern scraper attempts structured data extraction
4. Legacy scraper falls back to CSS selectors
5. Content processor cleans and normalizes
6. Deduplication check against existing content
7. Quality scoring and metadata enrichment
8. Storage in PostgreSQL database
```

### 2. Web Interface Flow
```
1. User requests articles page
2. FastAPI queries database with filters
3. Boolean search parser processes query
4. Results filtered and paginated
5. Jinja2 templates render HTML
6. JavaScript enhances interactivity
```

### 3. Background Processing Flow
```
1. Celery beat scheduler triggers tasks
2. Worker processes pick up tasks
3. Source monitoring runs periodically
4. Content collection executes tiered strategy
5. Quality analysis runs in background
6. Results stored in database
```

## Key Features

### 1. Boolean Search System
- **Operators**: AND, OR, NOT
- **Quoted Phrases**: "advanced persistent threat"
- **Complex Queries**: `"critical infrastructure" AND ransomware NOT basic`
- **Real-time**: Debounced search with 500ms delay
- **Help System**: Collapsible syntax guide

### 2. Quality Assessment
- **Content Scoring**: Length, readability, technical depth
- **Source Weighting**: Tier-based reputation scoring
- **Threat Relevance**: Intelligence value assessment
- **Classification**: Chosen/Rejected/Unclassified articles

### 3. Scalable Architecture
- **Async Processing**: Non-blocking web operations
- **Background Tasks**: Celery for heavy processing
- **Database Optimization**: Indexed queries, connection pooling
- **Containerization**: Docker for consistent deployment

## Technology Stack

### Backend
- **Python 3.11+**: Core application language
- **FastAPI**: Modern async web framework
- **SQLAlchemy**: Database ORM (async + sync)
- **PostgreSQL**: Primary database
- **Celery**: Background task processing
- **Redis**: Message broker and caching

### Frontend
- **Jinja2**: Server-side templating
- **Tailwind CSS**: Utility-first styling
- **JavaScript**: Interactive features
- **HTMX**: Dynamic content updates

### Infrastructure
- **Docker**: Containerization
- **Docker Compose**: Multi-service orchestration
- **Nginx**: Reverse proxy and load balancing
- **PostgreSQL**: Database server
- **Redis**: Cache and message broker

## Development Workflow

### Local Development
```bash
# Start full stack
docker-compose up -d

# Web interface
http://localhost:8000

# Database access
docker exec -it cti_postgres psql -U cti_user -d cti_scraper

# Run tests
python3 -m pytest tests/ -v

# CLI operations
python -m src.cli.main collect --tier 1 --dry-run
```

### Adding New Sources
1. Add source configuration to `config/sources.yaml`
2. Define scraping rules and selectors
3. Test with CLI: `python -m src.cli.main collect --source new_source_id`
4. Monitor collection in web interface
5. Adjust configuration based on results

### Customizing Processing
1. Modify `src/core/processor.py` for content processing
2. Update `src/core/modern_scraper.py` for extraction rules
3. Add quality metrics in processing pipeline
4. Test with sample content
5. Deploy and monitor results

## Monitoring and Maintenance

### Health Checks
- **Web Application**: `http://localhost:8000/health`
- **Database**: Connection pool monitoring
- **Celery Workers**: Task queue monitoring
- **Source Status**: Collection success rates

### Logging
- **Application Logs**: Docker container logs
- **Database Logs**: PostgreSQL query performance
- **Collection Logs**: Source-specific collection status
- **Error Tracking**: Failed scraping attempts

### Performance Metrics
- **Collection Rate**: Articles per hour
- **Quality Distribution**: Chosen vs rejected ratios
- **Source Performance**: Success rates by source
- **Database Performance**: Query response times

## Security Considerations

### Data Protection
- **Source Credentials**: Environment variable storage
- **Database Access**: Local-only connections by default
- **Rate Limiting**: Respectful scraping practices
- **Content Validation**: Input sanitization

### Operational Security
- **Container Security**: Non-root user execution
- **Network Security**: Internal service communication
- **Access Control**: Database user permissions
- **Audit Logging**: Database access monitoring

## Future Enhancements

### Planned Features
- **Advanced Analytics**: Machine learning-based content analysis
- **API Enhancements**: GraphQL interface
- **Real-time Updates**: WebSocket notifications
- **Export Capabilities**: Multiple format support
- **Integration**: SIEM and threat intelligence platform connectors

### Scalability Improvements
- **Horizontal Scaling**: Multiple worker instances
- **Database Sharding**: Partitioned data storage
- **Caching Layer**: Redis-based content caching
- **CDN Integration**: Static content delivery

## Getting Started for Developers

### Prerequisites
- Docker and Docker Compose
- Python 3.11+
- PostgreSQL (for local development)
- Redis (for background tasks)

### Quick Start
```bash
# Clone repository
git clone <repository-url>
cd CTIScraper

# Start services
docker-compose up -d

# Access web interface
open http://localhost:8000

# Check database
docker exec -it cti_postgres psql -U cti_user -d cti_scraper -c "SELECT COUNT(*) FROM articles;"

# Run initial collection
python -m src.cli.main collect --tier 1
```

### Development Environment
```bash
# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure database
export DATABASE_URL="postgresql+asyncpg://cti_user:cti_password_2024@localhost:5432/cti_scraper"

# Run web application
uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8000 --reload
```

This technical readout provides a comprehensive overview of the CTI Scraper architecture, implementation details, and development workflow for engineers and developers joining the project.
