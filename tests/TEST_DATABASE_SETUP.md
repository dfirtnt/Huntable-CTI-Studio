# Test Database Setup

## Overview
The test suite uses containerized PostgreSQL and Redis instances to avoid conflicts with production data.

**Containers:**
- **PostgreSQL:** `cti_postgres_test` (port 5433)
- **Redis:** `cti_redis_test` (port 6380)

These containers are managed by `docker-compose.test.yml` and auto-started by `run_tests.py` if either one is missing.

---

## Quick Start

### Run Tests with Test Database
```bash
# Tests will auto-start both required containers if needed
python run_tests.py api

# Or set environment variables manually
export APP_ENV=test
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"
pytest tests/api/ -v
```

### Check Container Status
```bash
docker ps --filter name=cti_postgres_test
docker ps --filter name=cti_redis_test
```

Expected output:
```
cti_postgres_test - Up X hours (healthy) - 0.0.0.0:5433->5432/tcp
cti_redis_test    - Up X hours (healthy) - 0.0.0.0:6380->6379/tcp
```

---

## Password Management

### How It Works

The test database password is **automatically managed** via `.env`:

```
.env file → docker-compose.test.yml → Container → run_tests.py → Tests
```

1. **`.env`** contains `POSTGRES_PASSWORD=<generated_password>`
2. **`docker-compose.test.yml`** reads `${POSTGRES_PASSWORD:-cti_password}`
3. **Container** starts with that password
4. **`run_tests.py`** reads `POSTGRES_PASSWORD` from `.env` and builds `TEST_DATABASE_URL`
5. **Tests** use `TEST_DATABASE_URL` from environment

### No Hardcoded Passwords! ✅

- Tests read from environment variable
- `run_tests.py` reads from `.env`
- Password only in **one place**: `.env` file
- When password changes, restart containers

### Changing the Password

```bash
# 1. Update .env
echo "POSTGRES_PASSWORD=new_password_here" >> .env

# 2. Restart test containers
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose.test.yml up -d

# 3. Tests will automatically use new password
python run_tests.py api
```

---

## Container Details

### PostgreSQL Test Database
- **Container Name:** `cti_postgres_test`
- **Image:** `pgvector/pgvector:pg15`
- **Host Port:** 5433 (production uses 5432)
- **Database:** `cti_scraper_test`
- **User:** `cti_user`
- **Password:** Read from `POSTGRES_PASSWORD` in `.env` (default: `cti_password`)
- **Network:** `cti_test_network`
- **Data:** Ephemeral (no volumes, destroyed on container removal)

### Redis Test Instance
- **Container Name:** `cti_redis_test`
- **Image:** `redis:7-alpine`
- **Host Port:** 6380 (production uses 6379)
- **Network:** `cti_test_network`
- **Data:** Ephemeral (no volumes, destroyed on container removal)

---

## Connection Strings

**The password is read from `.env` file automatically by `run_tests.py`.**

### PostgreSQL (asyncpg for async tests)
```bash
# run_tests.py automatically constructs this from POSTGRES_PASSWORD in .env
TEST_DATABASE_URL="postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@localhost:5433/cti_scraper_test"

# Current password (check your .env):
TEST_DATABASE_URL="postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"
```

### PostgreSQL (psycopg2 for sync operations)
```bash
TEST_DATABASE_URL="postgresql://cti_user:${POSTGRES_PASSWORD}@localhost:5433/cti_scraper_test"
```

### Redis
```bash
TEST_REDIS_URL="redis://localhost:6380/0"
```

---

## Manual Container Management

### Start Containers
```bash
docker-compose -f docker-compose.test.yml up -d
```

### Stop Containers
```bash
docker-compose -f docker-compose.test.yml down
```

### Restart Containers (Fresh DB)
```bash
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose.test.yml up -d
```

### View Logs
```bash
docker logs cti_postgres_test
docker logs cti_redis_test
```

### Connect to PostgreSQL
```bash
PGPASSWORD=K1LZXPsrF2uft4fNL6UB2C0u psql -h localhost -p 5433 -U cti_user -d cti_scraper_test
```

### Connect to Redis
```bash
redis-cli -p 6380
```

---

## Running API Tests

### Option 1: Using run_tests.py (Recommended)
```bash
# Auto-starts containers, sets environment
python run_tests.py api

# Specific test file
python run_tests.py tests/api/test_workflow_config_api.py
```

### Option 2: Direct pytest
```bash
# Set environment first
export APP_ENV=test
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"

# Run tests
pytest tests/api/test_workflow_config_api.py -v
```

### Option 3: Using ASGI Client (In-Process)
```bash
export APP_ENV=test
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"
export USE_ASGI_CLIENT=1

pytest tests/api/test_workflow_preset_lifecycle.py -v
```

---

## Test Database Schema

The test database schema is managed by:
1. **Alembic migrations** (same as production)
2. **Test fixtures** in `tests/conftest.py`
3. **Schema validation** via `ensure_workflow_config_schema()`

### Initialize Schema
```bash
# Connect to test DB
PGPASSWORD=K1LZXPsrF2uft4fNL6UB2C0u psql -h localhost -p 5433 -U cti_user -d cti_scraper_test

# Run schema initialization
\i scripts/init_test_schema.sql
```

Or via Python:
```bash
python scripts/init_test_schema.py
```

---

## Common Issues

### Issue 1: Password Authentication Failed
**Error:** `FATAL: password authentication failed for user "cti_user"`

**Cause:** Password mismatch between `.env` and running container

**Fix:**
```bash
# Step 1: Check password in .env
grep POSTGRES_PASSWORD .env

# Step 2: Restart containers to pick up new password
docker-compose -f docker-compose.test.yml down
docker-compose -f docker-compose.test.yml up -d

# Step 3: run_tests.py will auto-configure TEST_DATABASE_URL from .env
python run_tests.py api
```

### Issue 2: Connection Refused
**Error:** `Connection refused` on port 5433

**Cause:** Test containers not running

**Fix:**
```bash
# Start containers
docker-compose -f docker-compose.test.yml up -d

# Verify they're running
docker ps --filter name=cti_postgres_test
```

### Issue 3: Database Does Not Exist
**Error:** `database "cti_scraper_test" does not exist`

**Cause:** Fresh container hasn't initialized database

**Fix:**
```bash
# Wait for healthcheck
docker-compose -f docker-compose.test.yml ps

# Should show "(healthy)" status
# If not, wait and check logs
docker logs cti_postgres_test
```

### Issue 4: Wrong Password in Tests
**Problem:** Tests hardcode old password `cti_password`

**Files to check:**
- `tests/integration/test_workflow_execution_integration.py`
- `tests/integration/test_celery_state_transitions.py`
- `tests/integration/conftest.py`

**Fix:** Update hardcoded connection strings to use `K1LZXPsrF2uft4fNL6UB2C0u`

---

## Environment Variables Summary

| Variable | Value | Purpose |
|----------|-------|---------|
| `APP_ENV` | `test` | Enable test mode |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test` | Test DB connection |
| `TEST_REDIS_URL` | `redis://localhost:6380/0` | Test Redis connection |
| `USE_ASGI_CLIENT` | `1` | Use in-process app (optional) |
| `POSTGRES_PORT` | `5433` | Test DB port override |

---

## Security Notes

### Ephemeral Data
- ✅ Test containers use **no persistent volumes**
- ✅ All data destroyed when container removed
- ✅ Fresh database on each `docker-compose up`

### Password Management
- ⚠️ Test password `K1LZXPsrF2uft4fNL6UB2C0u` is randomly generated
- ⚠️ Stored in container environment (visible via `docker inspect`)
- ✅ Only accessible on localhost (not exposed externally)
- ✅ Separate from production credentials

### Port Isolation
- Test PostgreSQL: **5433** (production: 5432)
- Test Redis: **6380** (production: 6379)
- Test Web: **8002** (production: 8001)

---

## Integration with run_tests.py

The test runner automatically:
1. Checks if both test containers are running
2. Starts `postgres_test` and `redis_test` if needed via `docker compose -f docker-compose.test.yml up -d postgres_test redis_test`
3. Sets `TEST_DATABASE_URL` environment variable
4. Waits for healthchecks to pass
5. Runs tests

**No manual setup required when using `run_tests.py`!**

---

## Verifying Test Database Connection

### Python
```python
import asyncpg

async def test_connection():
    conn = await asyncpg.connect(
        "postgresql://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"
    )
    result = await conn.fetchval("SELECT 1")
    print(f"Connection successful: {result}")
    await conn.close()

# Run with: python -m asyncio -c "import asyncio; asyncio.run(test_connection())"
```

### Command Line
```bash
PGPASSWORD=K1LZXPsrF2uft4fNL6UB2C0u psql \
  -h localhost \
  -p 5433 \
  -U cti_user \
  -d cti_scraper_test \
  -c "SELECT current_database(), current_user, version();"
```

Expected output:
```
 current_database |  current_user | version
------------------+---------------+---------
 cti_scraper_test | cti_user      | PostgreSQL 15.14...
```

---

## References

- **Docker Compose:** `docker-compose.test.yml`
- **Test Runner:** `run_tests.py`
- **Fixtures:** `tests/conftest.py`
- **Schema Init:** `scripts/init_test_schema.py`
