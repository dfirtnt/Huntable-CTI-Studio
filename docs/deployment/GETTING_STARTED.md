# Getting Started with CTIScraper Deployment

Quick deployment guide for getting CTIScraper up and running in different environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Environment Setup](#environment-setup)
4. [Docker Architecture](#docker-architecture)
5. [Configuration](#configuration)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)
8. [Next Steps](#next-steps)

## Prerequisites

### System Requirements

- **Docker**: Version 20.10+ with Docker Compose
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Storage**: Minimum 10GB free space
- **Network**: Internet access for downloading feeds and AI services

### Platform Support

- **Linux**: Ubuntu 20.04+, CentOS 8+, Debian 11+
- **macOS**: macOS 10.15+ (Intel/Apple Silicon)
- **Windows**: Windows 10+ with WSL2 or Docker Desktop

### Required Software

```bash
# Install Docker and Docker Compose
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose-plugin

# macOS (with Homebrew)
brew install docker docker-compose

# Windows
# Download Docker Desktop from https://docker.com
```

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd CTIScraper

# Copy environment template
cp env.example .env

# Start the application
./start.sh
```

### 2. Verify Installation

```bash
# Check container status
docker-compose ps

# Check application health
curl http://localhost:8001/health

# Access web interface
open http://localhost:8001
```

### 3. First Steps

1. **Access the web interface** at `http://localhost:8001`
2. **Add your first source** via the Sources page
3. **Trigger content collection** to test the system
4. **View collected articles** on the Articles page

## Environment Setup

### Development Environment

**Purpose**: Local development and testing

**Features**:
- Hot reload for code changes
- Debug logging enabled
- CLI tools included
- Exposed ports for external access
- Persistent data volumes

**Usage**:
```bash
# Start development environment
./start.sh

# Use CLI tools
./run_cli.sh <command>

# View logs
docker-compose logs -f web
```

### Production Environment

**Purpose**: Production deployment

**Features**:
- Optimized for performance
- Health checks and monitoring
- Persistent data volumes
- CLI tools available via profiles

**Usage**:
```bash
# Start production environment
./start.sh

# Use CLI tools
docker-compose run --rm cli <command>

# Monitor services
docker-compose ps
```

### Test Environment

**Purpose**: Automated testing

**Features**:
- Isolated test database
- Test-specific configurations
- Automated test execution
- Clean environment for each test run

**Usage**:
```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run tests
python run_tests.py --docker --all

# Clean up
docker-compose -f docker-compose.test.yml down
```

## Docker Architecture

### Core Services

#### 1. PostgreSQL Database (`postgres`)
- **Purpose**: Stores all application data (sources, articles, metadata)
- **Port**: 5432 (internal)
- **Features**: Async operations, persistent volumes
- **Data**: Sources, articles, annotations, metadata

#### 2. Redis Cache (`redis`)
- **Purpose**: Message broker and caching layer
- **Port**: 6379 (internal)
- **Features**: Celery task queue, result backend, caching
- **Data**: Task queues, cached responses, session data

#### 3. FastAPI Web Application (`web`)
- **Purpose**: Main web interface and API endpoints
- **Port**: 8001 (external)
- **Features**: Web UI, REST API, user interactions
- **Endpoints**: Articles, sources, analysis, health

#### 4. Celery Worker (`worker`)
- **Purpose**: Background task processing
- **Features**: Source checking, article collection, scheduled operations
- **Tasks**: Content collection, processing, analysis

#### 5. Celery Beat Scheduler (`scheduler`)
- **Purpose**: Periodic task scheduling
- **Features**: Automated source checks, maintenance tasks
- **Schedule**: Daily source checks, weekly maintenance

#### 6. Multi-Provider LLM Service (`cti_ollama`)
- **Purpose**: AI-powered content analysis
- **Features**: Local Ollama, OpenAI GPT-4o, Anthropic Claude
- **Capabilities**: Summaries, SIGMA rules, rankings, RAG chat
- **Models**: Llama 3.2 1B (local), GPT-4o, Claude

#### 7. Automated Backup System
- **Purpose**: Data protection and recovery
- **Features**: Daily backups, retention policies, web management
- **Schedule**: 2:00 AM daily, 3:00 AM weekly cleanup
- **Retention**: 7 daily + 4 weekly + 3 monthly backups

### Service Communication

```mermaid
graph TB
    User[User] --> Web[Web App :8001]
    Web --> DB[(PostgreSQL :5432)]
    Web --> Redis[(Redis :6379)]
    Web --> Worker[Celery Worker]
    Worker --> DB
    Worker --> Redis
    Worker --> LLM[LLM Service]
    Scheduler[Beat Scheduler] --> Worker
    Backup[Backup System] --> DB
    CLI[CLI Tools] --> DB
```

### Data Flow

1. **User adds source** → Web app → Database
2. **Scheduler triggers collection** → Worker → Source checking
3. **Worker collects content** → Processing → Database
4. **AI analysis** → LLM service → Threat scoring
5. **User views results** → Web app → Database

## Configuration

### Environment Variables

#### Core Configuration
```bash
# .env file
# Database
DATABASE_URL=postgresql://cti_user:cti_password@postgres:5432/cti_scraper
POSTGRES_DB=cti_scraper
POSTGRES_USER=cti_user
POSTGRES_PASSWORD=cti_password

# Redis
REDIS_URL=redis://redis:6379

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO
CTI_SCRAPER_URL=http://localhost:8001

# AI Services (optional)
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
```

#### AI Configuration
```bash
# Ollama (local AI)
OLLAMA_BASE_URL=http://cti_ollama:11434
OLLAMA_MODEL=llama3.2:1b

# OpenAI (optional)
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o

# Anthropic (optional)
ANTHROPIC_API_KEY=sk-ant-your-key
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

#### Backup Configuration
```bash
# Backup settings
BACKUP_RETENTION_DAYS=7
BACKUP_RETENTION_WEEKS=4
BACKUP_RETENTION_MONTHS=3
BACKUP_MAX_SIZE_GB=50
```

### Docker Compose Configuration

#### Development (`docker-compose.yml`)
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: cti_scraper
      POSTGRES_USER: cti_user
      POSTGRES_PASSWORD: cti_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"

  web:
    build: .
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://cti_user:cti_password@postgres:5432/cti_scraper
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
    volumes:
      - .:/app
```

#### Production (`docker-compose.yml`)
**Note**: Production uses the same `docker-compose.yml` file with production environment variables set in `.env`.

For production deployment:
- Set `ENVIRONMENT=production` in `.env`
- Use strong passwords for `POSTGRES_PASSWORD`
- Configure proper `CORS_ORIGINS` for your domain
- Set `DEBUG=false` and `LOG_LEVEL=INFO`
- Ensure `SECRET_KEY` is a secure random string
- Configure SSL/TLS certificates
- Set up proper backup strategies

## Verification

### Health Checks

#### Application Health
```bash
# Check web application
curl http://localhost:8001/health

# Expected response
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "services": {
    "database": "healthy",
    "redis": "healthy",
    "worker": "healthy"
  }
}
```

#### Service Status
```bash
# Check all containers
docker-compose ps

# Expected output
NAME                IMAGE               STATUS
cti_postgres        postgres:15         Up
cti_redis           redis:7-alpine      Up
cti_web             cti_scraper         Up
cti_worker          cti_scraper         Up
cti_scheduler       cti_scraper         Up
cti_ollama          ollama/ollama       Up
```

#### Database Connectivity
```bash
# Test database connection
docker-compose exec postgres psql -U cti_user -d cti_scraper -c "SELECT 1;"

# Expected output
 ?column?
----------
        1
```

#### Redis Connectivity
```bash
# Test Redis connection
docker-compose exec redis redis-cli ping

# Expected output
PONG
```

### Functional Tests

#### Web Interface
```bash
# Test homepage
curl http://localhost:8001/

# Test API endpoints
curl http://localhost:8001/api/articles
curl http://localhost:8001/api/sources
```

#### CLI Tools
```bash
# Test CLI functionality
./run_cli.sh --help
./run_cli.sh sources list
./run_cli.sh articles list
```

#### AI Services
```bash
# Test local AI
curl http://localhost:8001/api/ai/summary -X POST -H "Content-Type: application/json" -d '{"text": "Test content"}'

# Test AI health
curl http://localhost:8001/api/ai/health
```

## Troubleshooting

### Common Issues

#### Container Startup Issues
```bash
# Check container logs
docker-compose logs web
docker-compose logs postgres
docker-compose logs redis

# Restart specific service
docker-compose restart web

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d
```

#### Database Connection Issues
```bash
# Check database status
docker-compose exec postgres pg_isready -U cti_user

# Reset database
docker-compose down
docker volume rm cti_postgres_data
docker-compose up -d
```

#### Port Conflicts
```bash
# Check port usage
netstat -tulpn | grep :8001
netstat -tulpn | grep :5432
netstat -tulpn | grep :6379

# Change ports in docker-compose.yml
ports:
  - "8002:8001"  # Change external port
```

#### Memory Issues
```bash
# Check memory usage
docker stats

# Increase Docker memory limit
# Docker Desktop: Settings → Resources → Memory
# Linux: Edit /etc/docker/daemon.json
```

#### AI Service Issues
```bash
# Check Ollama status
docker-compose exec cti_ollama ollama list

# Restart AI service
docker-compose restart cti_ollama

# Check AI logs
docker-compose logs cti_ollama
```

### Debug Commands

#### Application Debugging
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
docker-compose restart web

# View detailed logs
docker-compose logs -f web

# Access container shell
docker-compose exec web bash
```

#### Database Debugging
```bash
# Access database shell
docker-compose exec postgres psql -U cti_user -d cti_scraper

# Check database size
docker-compose exec postgres psql -U cti_user -d cti_scraper -c "SELECT pg_size_pretty(pg_database_size('cti_scraper'));"

# Check table sizes
docker-compose exec postgres psql -U cti_user -d cti_scraper -c "SELECT schemaname,tablename,pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
```

#### Performance Debugging
```bash
# Check resource usage
docker stats

# Monitor logs in real-time
docker-compose logs -f

# Check service health
curl http://localhost:8001/health
```

### Recovery Procedures

#### Data Recovery
```bash
# Restore from backup
./run_cli.sh backup restore <backup-file>

# Check backup status
./run_cli.sh backup list
```

#### Service Recovery
```bash
# Full restart
docker-compose down
docker-compose up -d

# Clean restart (removes volumes)
docker-compose down -v
docker-compose up -d
```

#### Configuration Recovery
```bash
# Reset to defaults
cp env.example .env
docker-compose restart
```

## Next Steps

### Basic Usage

1. **Add Sources**: Configure RSS feeds and web sources
2. **Collect Content**: Trigger content collection and processing
3. **Analyze Articles**: Review threat scores and AI analysis
4. **Manage Data**: Use annotations and classifications

### Advanced Configuration

1. **AI Integration**: Configure OpenAI and Anthropic APIs
2. **Custom Scoring**: Adjust threat hunting parameters
3. **Backup Strategy**: Configure automated backups
4. **Monitoring**: Set up health monitoring and alerts

### Production Deployment

1. **Security**: Configure authentication and authorization
2. **Scaling**: Set up load balancing and horizontal scaling
3. **Monitoring**: Implement comprehensive monitoring
4. **Backup**: Configure production backup strategies

### Documentation

- **Architecture**: [Docker Architecture Guide](DOCKER_ARCHITECTURE.md)
- **API Reference**: [API Endpoints](API_ENDPOINTS.md)
- **Testing**: [Testing Guide](../tests/TESTING.md)
- **Backup**: [Database Backup](DATABASE_BACKUP_RESTORE.md)

### Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: Project documentation
- **Community**: Project community channels

---

*Last updated: January 2025*
