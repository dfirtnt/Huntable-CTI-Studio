# Docker Architecture Guide

This document explains the Docker architecture and how to work with the containerized CTI Scraper.

## Architecture Overview

The CTI Scraper uses a microservices architecture with the following components:

### Core Services (Production & Development)

1. **PostgreSQL Database** (`postgres`)
   - Stores all application data (sources, articles, metadata)
   - Uses asyncpg for high-performance async operations
   - Persistent data volumes for data retention

2. **Redis Cache** (`redis`)
   - Message broker for Celery tasks
   - Result backend for task results
   - Caching layer for frequently accessed data

3. **FastAPI Web Application** (`web`)
   - Main web interface and API endpoints
   - Serves HTML templates and JSON APIs
   - Handles user interactions and data display

4. **Celery Worker** (`worker`)
   - Processes background tasks
   - Handles source checking and article collection
   - Runs scheduled operations

5. **Celery Beat Scheduler** (`scheduler`)
   - Manages periodic task scheduling
   - Triggers source checks and maintenance tasks

6. **Ollama LLM Service** (`ollama`)
   - Local large language model for content analysis
   - Provides threat hunting and detection engineering analysis
   - Runs Mistral model for content processing

### Additional Services

7. **CLI Tool Service** (`cli`) - **NEW**
   - Containerized command-line interface
   - Uses same PostgreSQL database as web application
   - Eliminates data inconsistency between CLI and web operations

8. **Nginx Reverse Proxy** (`nginx`) - Production only
   - Load balancing and SSL termination
   - Static file serving
   - Security headers and rate limiting

## Environment Configurations

### Development Environment (`docker-compose.dev.yml`)

- **Purpose**: Local development and testing
- **Features**:
  - Hot reload for code changes
  - Debug logging enabled
  - CLI tools included
  - Exposed ports for external access
  - Separate data volumes (`*_dev`)

- **Usage**:
  ```bash
  ./start_development.sh
  ./run_cli.sh <command>
  ```

### Production Environment (`docker-compose.yml`)

- **Purpose**: Production deployment
- **Features**:
  - Optimized for performance
  - Nginx reverse proxy
  - Health checks and monitoring
  - Persistent data volumes
  - CLI tools available via profiles

- **Usage**:
  ```bash
  ./start_production.sh
  docker-compose run --rm cli <command>
  ```

## Database Connectivity

### Before (Issues Fixed)

- CLI tool used SQLite locally
- Web app used PostgreSQL in Docker
- Data inconsistency between CLI and web operations
- Different database managers for different components

### After (Fixed Architecture)

- All components use PostgreSQL in Docker
- Consistent database connectivity across all services
- Single source of truth for data
- Unified async database manager

## Service Communication

### Internal Communication (Docker Network)

Services communicate using Docker service names:
- Database: `postgres:5432`
- Redis: `redis:6379`
- Web API: `web:8000`
- Ollama: `cti_ollama:11434`

### External Access (Port Mapping)

For development and external access:
- Web UI: `localhost:8000`
- Database: `localhost:5432`
- Redis: `localhost:6379`
- Ollama: `localhost:11434`

## CLI Tool Integration

### Problem Solved

The CLI tool was previously running locally with SQLite, causing:
- Data inconsistency between CLI and web operations
- Different database schemas
- Confusion about which database to use

### Solution Implemented

1. **Containerized CLI**: CLI tool now runs in Docker container
2. **Unified Database**: Uses same PostgreSQL as web application
3. **Consistent Environment**: Same environment variables and configuration
4. **Easy Access**: Simple script (`run_cli.sh`) for running CLI commands

### Usage Examples

```bash
# Initialize sources
./run_cli.sh init

# List sources
./run_cli.sh sources list --active

# Collect articles
./run_cli.sh collect --dry-run

# Export data
./run_cli.sh export --format json --days 7

# Monitor sources
./run_cli.sh monitor --interval 300
```

## Data Persistence

### Volumes

- **PostgreSQL Data**: `postgres_data` (production) / `postgres_data_dev` (development)
- **Redis Data**: `redis_data` (production) / `redis_data_dev` (development)
- **Ollama Models**: `ollama_data` (production) / `ollama_data_dev` (development)

### Backup Strategy

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U cti_user cti_scraper > backup.sql

# Backup Redis
docker-compose exec redis redis-cli --rdb /data/dump.rdb

# Restore PostgreSQL
docker-compose exec -T postgres psql -U cti_user cti_scraper < backup.sql
```

## Health Monitoring

### Health Checks

All services include health checks:
- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`
- Web: `curl /health`
- Ollama: `curl /api/tags`

### Monitoring Commands

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f [service]

# Health check
curl http://localhost:8000/health

# Database stats
curl http://localhost:8000/api/sources
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Ensure PostgreSQL container is running: `docker-compose ps`
   - Check logs: `docker-compose logs postgres`
   - Verify network connectivity: `docker-compose exec web ping postgres`

2. **CLI Tool Issues**
   - Use `./run_cli.sh` instead of running CLI locally
   - Ensure development stack is running: `./start_development.sh`
   - Check CLI logs: `docker-compose logs cli`

3. **Port Conflicts**
   - Stop conflicting services: `docker-compose down`
   - Check port usage: `lsof -i :8000`
   - Use different ports in docker-compose files if needed

### Debug Mode

For debugging, use the development environment:
```bash
./start_development.sh
docker-compose -f docker-compose.dev.yml logs -f
```

## Migration from Local Development

If you were previously running components locally:

1. **Stop local services**: Stop any local PostgreSQL, Redis, or Python processes
2. **Backup data**: Export any important data from local databases
3. **Start Docker stack**: `./start_development.sh`
4. **Migrate data**: Import data into Docker PostgreSQL if needed
5. **Use CLI script**: Replace direct CLI calls with `./run_cli.sh`

## Best Practices

1. **Always use Docker**: Run all components in Docker for consistency
2. **Use CLI script**: Use `./run_cli.sh` instead of running CLI locally
3. **Development vs Production**: Use appropriate docker-compose file
4. **Data backup**: Regular backups of PostgreSQL and Redis data
5. **Monitoring**: Check health endpoints and logs regularly
6. **Environment variables**: Use consistent environment variables across services
7. **No virtual environments needed**: All Python dependencies are managed in Docker containers
