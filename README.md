# CTI Scraper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docker.com)
[![CI/CD](https://github.com/starlord/CTIScraper/workflows/CI/badge.svg)](https://github.com/starlord/CTIScraper/actions)
[![Security](https://img.shields.io/badge/security-audited-green.svg)](.github/SECURITY.md)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

A comprehensive threat intelligence aggregation and analysis platform designed for security researchers and threat hunters. CTI Scraper automates the collection, processing, and analysis of threat intelligence from multiple sources, providing actionable insights for cybersecurity professionals.

## 🎯 Key Features

### 🔍 Intelligent Threat Intelligence Collection
- **Multi-Source Aggregation**: Automated collection from 40+ RSS feeds, security blogs, and vendor sites
- **Smart Content Processing**: RSS-first collection with basic web scraping fallback and HTML cleaning
- **Duplicate Detection**: Intelligent deduplication using content hashing and similarity analysis
- **Source Health Monitoring**: Real-time monitoring with automatic failure detection and recovery

### 🤖 AI-Powered Analysis
- **Threat Hunting Scoring**: Rule-based relevance scoring using keyword density and logarithmic formulas
- **LLM Integration**: Support for Ollama (local), OpenAI GPT models, and LM Studio
- **Intelligent Classification**: GPT-4 powered article relevance assessment and categorization
- **IOC Extraction**: Hybrid IOC extraction combining iocextract with optional LLM validation
- **SIGMA Rule Generation**: AI-powered generation of detection rules with pySIGMA validation

### 📊 Advanced Analytics
- **Text Annotation System**: Web-based interface for marking huntable vs non-huntable content
- **Keyword Classification**: Multi-tier keyword matching (perfect, good, LOLBAS, intelligence indicators)
- **Content Filtering**: Automated junk detection and quality assessment
- **Interactive Dashboards**: Real-time analytics for source health and content metrics

### 🌐 Modern Web Interface
- **Responsive Design**: Modern UI built with FastAPI and contemporary JavaScript
- **Real-time Updates**: Live monitoring of collection and processing status
- **Export Capabilities**: CSV export for annotations and classified content
- **RESTful API**: Comprehensive API for integration with other security tools
- **Database Management**: Command-line backup and restore tools for data protection

## 🏗️ Architecture

### Core Components
- **FastAPI Backend**: High-performance async web framework with automatic API documentation
- **PostgreSQL Database**: Robust data storage with advanced indexing and query optimization
- **Redis Cache**: High-speed caching and task queue management
- **Celery Workers**: Distributed task processing for scalable content collection
- **Docker Containers**: Containerized deployment for consistent environments

### Data Flow
1. **Collection**: RSS feed parsing (primary) with basic web scraping fallback
2. **Processing**: Content extraction, cleaning, and deduplication
3. **Analysis**: Rule-based scoring and AI-powered classification
4. **Storage**: Structured data storage with full-text search capabilities
5. **Presentation**: Real-time web interface and API endpoints

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for development)
- PostgreSQL and Redis (handled by Docker)

### ⚡ One-Command Setup (Recommended)
```bash
git clone https://github.com/starlord/CTIScraper.git
cd CTIScraper
chmod +x setup.sh
./setup.sh
```

This automated script will:
- ✅ Check prerequisites (Docker, Docker Compose)
- ✅ Create `.env` file from `env.example`
- ✅ Create necessary directories
- ✅ Start all services with proper configuration
- ✅ Wait for services to be ready
- ✅ Verify installation
- ✅ Show access URLs and management commands

### Manual Installation (Alternative)

If you prefer manual setup or the automated script fails:

1. **Clone the repository**
   ```bash
   git clone https://github.com/starlord/CTIScraper.git
   cd CTIScraper
   ```

2. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your configuration (API keys, database credentials, etc.)
   ```

   **⚠️ IMPORTANT**: The `.env` file is required for Redis and PostgreSQL to start properly. Without it, containers will fail with configuration errors.

3. **Start the application**
   ```bash
   docker-compose up -d
   ```

4. **Verify installation**
   ```bash
   # Check container status
   docker-compose ps
   
   # View logs
   docker-compose logs -f
   ```

5. **Access the application**
   - **Web Interface**: http://localhost:8001
   - **API Documentation**: http://localhost:8001/docs
   - **Health Check**: http://localhost:8001/health

## 📋 Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
POSTGRES_USER=cti_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=cti_scraper

# Redis
REDIS_PASSWORD=your_redis_password

# LLM Configuration (Optional)
CHATGPT_API_KEY=your_openai_api_key_here
OLLAMA_HOST=http://ollama:11434

# Application
LOG_LEVEL=INFO
WORKERS=4
```

### Source Configuration

- **Primary workflow**: Use the `Source Config` tab in the web UI to create or edit sources. Changes apply directly to PostgreSQL and persist across restarts.
- **Bootstrap file**: `config/sources.yaml` seeds the database only when no sources exist (all-or-nothing). Keep it updated for fresh deployments, but it no longer overwrites live edits.
- **Manual sync**: Run `docker exec cti_worker python -m src.cli.main sync-sources --config config/sources.yaml` for partial updates (existing sources get updated, new ones get created, missing ones optionally removed).
- **Manual reset**: Run `docker exec cti_worker python -m src.cli.main sync-sources --config config/sources.yaml` if you intentionally want to replace database rows with the YAML contents.

## 🏗️ Architecture

### Components
- **Web Server**: FastAPI application with modern web interface
- **Worker Processes**: Celery workers for background scraping and processing
- **Scheduler**: Automated source checking and maintenance tasks
- **Database**: PostgreSQL for structured data storage
- **Cache**: Redis for session management and task queuing
- **Reverse Proxy**: Nginx for production deployments with SSL termination and rate limiting

### Classification System

**Article Classification** (Whole Article Level):
- `chosen`: Relevant threat intelligence
- `rejected`: Not relevant
- `unclassified`: Needs review

**Annotation Classification** (Text Chunk Level):
- `huntable`: Actionable threat intelligence
- `not_huntable`: Informational content

### Data Model

**Article Metadata Structure:**
- **Database Field**: `article_metadata` (JSON column in PostgreSQL)
- **Pydantic Model**: `article_metadata` field in `Article` and `ArticleCreate` models
- **Key Fields**:
  - `threat_hunting_score`: Relevance score (0-100)
  - `perfect_keyword_matches`: Exact keyword matches
  - `good_keyword_matches`: Partial keyword matches
  - `lolbas_matches`: Living off the land binaries and scripts
  - `technical_depth_score`: Technical complexity assessment

## 🔧 Development

### Local Development Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start development server**
   ```bash
   uvicorn src.web.modern_main:app --reload --host 0.0.0.0 --port 8001
   ```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Test specific components
pytest tests/test_scraping.py

# Run IOC extractor tests
pytest tests/test_ioc_extractor.py -v

# Run security audit
pip-audit --desc
```

### Test Coverage
- **Unit Tests**: Core functionality and business logic
- **Integration Tests**: Database and API interactions  
- **IOC Extractor Tests**: Comprehensive testing of IOC extraction functionality
- **Security Tests**: Vulnerability scanning and dependency auditing

## 📊 Usage Examples

### Adding Sources
1. Navigate to Sources page in web interface
2. Click "Add Source"
3. Configure RSS URL, check frequency, and tier
4. Save and monitor collection status




### SIGMA Rule Generation
Generate detection rules from threat intelligence articles:
1. Navigate to any article with threat hunting score > 70
2. Click "Generate SIGMA Rules" button
3. AI analyzes content and generates detection rules
4. Rules are validated using pySIGMA for compliance
5. Failed rules are automatically retried with error feedback (up to 3 attempts)
6. Valid rules are stored with metadata and validation results

### Database Backup & Restore
Protect your data with command-line backup and restore tools:

**Create Backup:**
```bash
# Using helper script (recommended)
./backup_restore.sh create

# Using CLI command (in Docker container)
docker exec cti_worker python -m src.cli.main backup create

# Using direct script (in Docker container)
docker exec cti_worker python scripts/backup_database.py
```

**List Backups:**
```bash
# Using helper script
./backup_restore.sh list

# Using CLI command (in Docker container)
docker exec cti_worker python -m src.cli.main backup list

# Using direct script (in Docker container)
docker exec cti_worker python scripts/backup_database.py --list
```

**Restore Database:**
```bash
# Using helper script
./backup_restore.sh restore cti_scraper_backup_20250907_134653.sql.gz

# Using CLI command (in Docker container)
docker exec cti_worker python -m src.cli.main backup restore cti_scraper_backup_20250907_134653.sql.gz

# Using direct script (in Docker container)
docker exec cti_worker python scripts/restore_database.py cti_scraper_backup_20250907_134653.sql.gz
```

### Threat Hunting Score Management
Regenerate threat hunting scores after keyword updates:

**Rescore All Articles:**
```bash
# Using CLI command (recommended)
./run_cli.sh rescore --force

# Using direct script (in Docker container)
docker exec cti_worker python regenerate_all_scores.py
```

**Rescore Specific Article:**
```bash
# Using CLI command
./run_cli.sh rescore --article-id 965

# Dry run to preview changes
./run_cli.sh rescore --force --dry-run
```

**Features:**
- Automatic compression (70-80% size reduction)
- Metadata tracking with database statistics
- Safety checks and pre-restore snapshots
- Docker container integration
- Timestamped filenames for easy management

For detailed backup procedures, see [Database Backup & Restore Guide](docs/DATABASE_BACKUP_RESTORE.md).

## 🚀 Production Deployment

### Nginx Reverse Proxy
The Nginx container provides production-ready features:

**Security Features:**
- **SSL/TLS Termination**: HTTPS encryption with TLS 1.2/1.3
- **HTTP→HTTPS Redirect**: Forces secure connections
- **Rate Limiting**: API protection (10 req/s) and web traffic (30 req/s)
- **Request Size Limits**: 100MB max upload protection

**Performance Optimizations:**
- **Gzip Compression**: Reduces bandwidth for text content
- **Connection Keepalive**: Maintains persistent connections
- **Static File Caching**: 1-year cache headers for assets
- **WebSocket Support**: Real-time communication capability

**Configuration:**
- **Ports**: 80 (HTTP) → 443 (HTTPS) → 8001 (FastAPI)
- **SSL Certificates**: Located in `nginx/ssl/` directory
- **Health Check**: `/health` endpoint for monitoring
- **Load Balancing**: Upstream configuration for FastAPI backend

### SSL Setup
1. **Generate SSL certificates**:
   ```bash
   mkdir -p nginx/ssl
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout nginx/ssl/key.pem \
     -out nginx/ssl/cert.pem
   ```

2. **Update domain** in `nginx/nginx.conf`:
   ```nginx
   server_name your-domain.com;
   ```

3. **Deploy with SSL**:
   ```bash
   docker-compose up -d
   ```

## 📈 Monitoring

### Health Checks
- **Application Health**: `/health` and `/api/health`
- **Database Connectivity**: `/api/health/database` with detailed stats
- **Source Status**: Real-time failure tracking
- **Worker Health**: `/api/health/celery` for Celery task monitoring
- **Services Health**: `/api/health/services` for Redis, Ollama status

### Metrics
- Article collection rates
- Processing success/failure rates
- Classification accuracy
- Source availability

## 🔒 Security

### Best Practices
- All secrets managed via environment variables
- Database connections use encrypted connections
- Rate limiting on API endpoints
- Input validation and sanitization
- Regular dependency updates

### Data Privacy
- No external data transmission without explicit configuration
- Local LLM support via Ollama
- Configurable data retention policies

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add tests for new features
- Update documentation
- Use type hints where possible

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with FastAPI, SQLAlchemy, BeautifulSoup, and RSS-first collection strategy
- Inspired by the threat intelligence community's need for better aggregation tools
- Special thanks to the open-source security tool ecosystem

## 📚 Documentation

- [Contributing Guidelines](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [SIGMA Rule Generation](SIGMA_RULE_GENERATION.md)
- [Web App Testing Guide](WebAppDevtestingGuide.md)
- [Agent Guidelines](AGENTS.md)
- [Security Policy](.github/SECURITY.md)
- [IOC Extractor Tests](tests/test_ioc_extractor.py)

## 🔧 Troubleshooting

### Common Issues

**Redis container keeps restarting:**
```bash
# Check if .env file exists and has REDIS_PASSWORD
ls -la .env
cat .env | grep REDIS_PASSWORD

# If missing, create it:
cp env.example .env
# Edit .env and set REDIS_PASSWORD=your_secure_password
```

**PostgreSQL connection failed:**
```bash
# Check if .env file has database credentials
cat .env | grep POSTGRES

# If missing, create it:
cp env.example .env
# Edit .env and set POSTGRES_PASSWORD=your_secure_password
```

**Containers fail to start:**
```bash
# Check Docker is running
docker info

# Check for port conflicts
docker ps | grep -E "(5432|6379|8001)"

# Clean restart
docker-compose down
docker-compose up -d
```

**Environment variables not loading:**
```bash
# Verify .env file exists and is readable
ls -la .env
cat .env | head -5

# Check Docker Compose can read it
docker-compose config
```

### Health Checks

```bash
# Check all services
docker-compose ps

# Check specific service logs
docker-compose logs redis
docker-compose logs postgres
docker-compose logs web

# Test connectivity
curl http://localhost:8001/health
```

## 💬 Support

- Create an issue for bug reports or feature requests
- Check existing documentation for common questions
- Review health checks for system status
- See troubleshooting section above for common issues

---

**Note**: This tool is designed for legitimate security research and threat intelligence purposes. Users are responsible for compliance with applicable laws and regulations.
