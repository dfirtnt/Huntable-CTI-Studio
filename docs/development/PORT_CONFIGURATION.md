# Port Configuration

Current port mappings and testing helpers.

## Defaults
- Web app / API: 8001 (host → container 8001)
- Aux/debug port: 8888 (exposed by web container)
- PostgreSQL: 5432 (container)
- Redis: 6379 (container)
- LM Studio (optional external): 1234 (default `LMSTUDIO_API_URL=http://host.docker.internal:1234/v1`)

`docker-compose.yml` snippet:
```yaml
web:
  ports:
    - "8001:8001"
    - "8888:8888"
  command: uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --reload
```

## Custom host port
```yaml
# change host port for web
web:
  ports:
    - "8002:8001"
```
Set matching base URL for tests:
```bash
export CTI_SCRAPER_URL=http://localhost:8002
```

## Testing helpers
```bash
# health
curl http://localhost:8001/health
# DB
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U cti_user -d cti_scraper -c "select 1"
# Redis
redis-cli -h localhost -p 6379 ping
```

## Port conflicts
```bash
lsof -i :8001
# adjust compose ports if needed, then
docker-compose down
docker-compose up -d
```

_Last verified: Feb 2025_
