# Multi-Instance Docker Setup

## Overview
This guide explains how to run multiple instances of Huntable CTI Studio simultaneously without port conflicts.

## Port Allocation

| Service | Original Port | Dev2 Port | Container Name |
|---------|---------------|-----------|----------------|
| Web App | 8001 | 8002 | cti_web_dev2 |
| PostgreSQL | 5432 | 5433 | cti_postgres_dev2 |
| Redis | 6379 | 6380 | cti_redis_dev2 |

## Setup Instructions

### 1. Clone Repository
```bash
git clone /path/to/Huntable-CTI-Studio /path/to/Huntable-CTI-Studio-dev2
cd /path/to/Huntable-CTI-Studio-dev2
```

### 2. Provision Secrets and Config
```bash
./setup.sh --no-backups
# Edit .env as needed for this instance-specific compose file
```
See [Development Setup](setup.md#1-provision-local-secrets-and-config) for what `setup.sh` does.

### 3. Start Dev2 Instance
```bash
docker-compose -f docker-compose.dev2.yml up -d
```

!!! warning "Known gaps in `docker-compose.dev2.yml`"
    **Missing init file.** The dev2 stack bind-mounts `./init.sql`, which does not exist at
    the repo root -- the primary `docker-compose.yml` mounts the `./init-scripts/` directory
    instead. Docker creates an empty *directory* named `init.sql` rather than failing, so
    Postgres starts with no init script applied.

    **Missing services.** dev2 defines only `postgres`, `redis`, `web`, `worker`, `scheduler`,
    and `cli`. It has no `workflow_worker`, `maintenance`, `mcp_http`, or `codex_auth_init`,
    so agentic workflow execution, backup/restore, and MCP HTTP access are unavailable on the
    dev2 instance.

### 4. Verify Services
```bash
# Check web app
curl http://localhost:8002/health

# Check database
docker exec -it cti_postgres_dev2 psql -U cti_user -d cti_scraper -c "SELECT version();"

# Check Redis
docker exec -it cti_redis_dev2 redis-cli -a ${REDIS_PASSWORD} ping
```

## Database Management

### Access Dev2 Database
```bash
docker exec -it cti_postgres_dev2 psql -U cti_user -d cti_scraper
```

### Backup Dev2 Database
```bash
docker exec cti_postgres_dev2 pg_dump -U cti_user cti_scraper > backup_dev2.sql
```

### Restore to Dev2 Database
```bash
docker exec -i cti_postgres_dev2 psql -U cti_user -d cti_scraper < backup_dev2.sql
```

## CLI Commands

### Run CLI in Dev2 Instance
```bash
docker-compose -f docker-compose.dev2.yml run --rm cli python3 -m src.cli.main [command]
```

### Example: Rescore Articles
```bash
docker-compose -f docker-compose.dev2.yml run --rm cli python3 -m src.cli.main rescore
```

## Stopping Instances

### Stop Dev2 Instance
```bash
docker-compose -f docker-compose.dev2.yml down
```

### Stop All Instances
```bash
# Original instance
docker-compose down

# Dev2 instance
docker-compose -f docker-compose.dev2.yml down
```

## Volume Management

Each instance uses separate Docker volumes:
- `postgres_data_dev2`
- `redis_data_dev2`

This ensures complete data isolation between instances.

## Network Isolation

Each instance uses its own Docker network (`cti_network_dev2`) to prevent service conflicts.

## Troubleshooting

### Port Already in Use
If you encounter port conflicts, check what's using the ports:
```bash
lsof -i :8002
lsof -i :5433
lsof -i :6380
```

Local LLM endpoints are host-managed and are not part of the Dev2 Compose port map.

### Container Name Conflicts
All Dev2 containers use `_dev2` suffix to avoid naming conflicts with the original instance.

_Last updated: 2026-07-03_
_Last reviewed: 2026-09-01_
