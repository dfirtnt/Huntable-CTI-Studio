# CTI Scraper

A modern threat intelligence collection and analysis platform that automatically gathers, processes, and analyzes security content from RSS feeds and web sources. Built with FastAPI, PostgreSQL, and Celery for scalable threat intelligence operations.

## 🚀 Features

- **Multi-Source Collection**: RSS feeds + intelligent web scraping with structured data extraction
- **Content Processing**: Advanced cleaning, normalization, deduplication, and quality scoring
- **Modern Web Interface**: FastAPI-powered dashboard with search, filtering, and analytics
- **Scalable Architecture**: PostgreSQL storage with async operations and Celery background tasks
- **Robots.txt Compliance**: Respectful crawling with configurable rate limiting per source
- **Source Tiering**: Priority-based collection system (premium/standard/basic tiers)
- **Threat Intelligence Focus**: Specialized for cybersecurity content analysis

## 📋 Quick Start

### Prerequisites
- Docker Desktop
- Git

### Development Setup
```bash
# Clone the repository
git clone https://github.com/dfirtnt/CTIScraper.git
cd CTIScraper

# Start development environment
./start_development.sh

# Initialize sources
./run_cli.sh init

# Start collecting content
./run_cli.sh collect --dry-run
```

### Production Deployment
```bash
# Start production stack
./start_production.sh
```

**Access Points:**
- Web UI: http://localhost:8000
- API: http://localhost:8000/api/*
- Health Check: http://localhost:8000/health

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Interface │    │  Background     │    │   Data Storage  │
│   (FastAPI)     │◄──►│  Tasks (Celery) │◄──►│  (PostgreSQL)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Content       │    │   Source        │    │   Redis Cache  │
│   Collection    │    │   Management    │    │   & Queue       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 Project Structure

```
src/
├── web/                 # FastAPI application
│   ├── modern_main.py   # Main web application
│   └── templates/       # HTML templates
├── core/                # Content ingestion engine
│   ├── rss_parser.py    # RSS/Atom feed processing
│   ├── modern_scraper.py # Structured data extraction
│   ├── fetcher.py       # Multi-strategy content fetching
│   └── processor.py     # Content processing pipeline
├── database/            # Data layer
│   ├── models.py        # SQLAlchemy models
│   ├── async_manager.py # Async database operations
│   └── manager.py       # Sync database operations
├── worker/              # Background task processing
├── utils/               # Shared utilities
└── cli/                 # Command-line interface

config/
├── sources.yaml         # Source definitions and configuration
├── models.yaml          # Model configuration
└── recommended_models.yaml # Recommended settings
```

## 🔧 Configuration

### Source Configuration (`config/sources.yaml`)
```yaml
sources:
  - id: "thehackernews"
    name: "The Hacker News"
    url: "https://thehackernews.com/"
    rss_url: "https://feeds.feedburner.com/TheHackersNews"
    tier: 2  # Source priority (1=premium, 2=standard, 3=basic)
    check_frequency: 3600
    active: true
    robots:
      enabled: true
      user_agent: "CTIScraper/2.0"
      respect_delay: true
      max_requests_per_minute: 10
```

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://cti_user:password@postgres:5432/cti_scraper

# Redis
REDIS_URL=redis://:password@redis:6379/0

# OpenAI (optional)
CHATGPT_API_KEY=your_openai_api_key_here
CHATGPT_API_URL=https://api.openai.com/v1/chat/completions
```

## 🛠️ CLI Commands

```bash
# Initialize sources from configuration
./run_cli.sh init --config config/sources.yaml

# Collect content from all sources
./run_cli.sh collect --dry-run

# Monitor sources continuously
./run_cli.sh monitor --interval 300

# List active sources
./run_cli.sh sources list --active

# Export articles
./run_cli.sh export --format json --days 7

# Show system statistics
./run_cli.sh stats
```

## 🔍 API Endpoints

### Web Interface
- `GET /` - Dashboard with statistics and recent articles
- `GET /articles` - Article listing with search and filters
- `GET /articles/{id}` - Detailed article view
- `GET /sources` - Source management interface

### JSON API
- `GET /health` - Service health status
- `GET /api/articles` - List articles with pagination
- `GET /api/articles/{id}` - Article details
- `GET /api/sources` - Source information
- `POST /api/sources/{id}/toggle` - Toggle source status

## 🧪 Testing

```bash
# Run all tests
pytest -q

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/api/
```

## 📚 Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Documentation Overview](docs/README.md)** - Complete documentation index
- **[Docker Architecture](docs/deployment/DOCKER_ARCHITECTURE.md)** - Docker setup guide
- **[Testing Guide](docs/development/TESTING_GUIDE.md)** - Testing documentation
- **[Database Queries](docs/development/DATABASE_QUERY_GUIDE.md)** - Database operations

## 🔒 Security Features

- **Robots.txt Compliance**: Respectful crawling with configurable per-source settings
- **Rate Limiting**: Automatic request throttling based on source policies
- **Environment-based Configuration**: Sensitive data stored in environment variables
- **Input Validation**: Comprehensive input sanitization and validation
- **Secure Defaults**: Production-ready security configurations

## 🚀 Deployment

### Docker Compose (Recommended)
```bash
# Development
docker-compose -f docker-compose.dev.yml up --build -d

# Production
docker-compose up --build -d
```

### AWS Deployment
See [AWS Deployment Guide](AWS_DEPLOYMENT_README.md) for cloud deployment instructions.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Important Notes

- **Research Purpose**: This tool is designed for legitimate threat intelligence research
- **Respectful Crawling**: Always respect website terms of service and robots.txt policies
- **Rate Limiting**: Built-in rate limiting helps maintain respectful data collection
- **Source Tiering**: Prioritize premium sources while maintaining comprehensive coverage

## 🆘 Support

For issues, questions, or contributions:
- Create an issue on GitHub
- Check the documentation in `docs/`
- Review the troubleshooting guide in `GITHUB_TROUBLESHOOTING.md`
