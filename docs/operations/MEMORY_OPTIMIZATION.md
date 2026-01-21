# Memory Optimization Guide

## Overview

Memory limits and worker concurrency have been configured to prevent Docker from consuming excessive RAM and causing system hangs. These settings are **conservative by default** but can be adjusted for systems with more available RAM.

## Impact Analysis

### What Will Slow Things Down

1. **Worker Concurrency Reduction** ⚠️ **PERFORMANCE IMPACT**
   - **Main worker**: Reduced from CPU count (typically 4-8+) to **2** by default
   - **Workflow worker**: Reduced from 4 to **2** by default
   - **Impact**: Reduces parallel task processing, directly affecting throughput
   - **Solution**: Increase via environment variables (see below)

2. **Memory Limits** ⚠️ **ONLY IF HIT**
   - Limits are **caps** - they only slow things down if containers need more memory
   - If a container hits its limit, it may be OOM-killed or swap (very slow)
   - **Impact**: Only affects performance if you're actually using that much memory
   - **Solution**: Increase limits via environment variables if needed

3. **Worker Recycling** ✅ **MINIMAL IMPACT**
   - `worker_max_tasks_per_child`: Reduced from 1000 to 50
   - Causes more frequent worker process recycling
   - **Impact**: Small overhead from process restarts, but prevents memory leaks
   - **Solution**: Increase if you have sufficient RAM and want less recycling

### What Won't Slow Things Down

- **Memory limits** (if not hit) - These are just caps
- **Redis eviction policy** - Only activates when Redis is full
- **Result expiration** - Only affects Redis cleanup timing

## Configuration

All settings are configurable via environment variables with safe defaults.

### Environment Variables

Add these to your `.env` file or export before running `docker compose`:

#### Worker Concurrency (Most Important for Performance)

```bash
# Main worker concurrency (default: 2)
WORKER_CONCURRENCY=4

# Workflow worker concurrency (default: 2)
WORKFLOW_WORKER_CONCURRENCY=4
```

**Recommended values:**
- **Low RAM (< 8GB)**: 2 (default)
- **Medium RAM (8-16GB)**: 4
- **High RAM (16GB+)**: 6-8

#### Memory Limits

```bash
# PostgreSQL (default: 2G limit, 512M reservation)
POSTGRES_MEMORY_LIMIT=4G
POSTGRES_MEMORY_RESERVATION=1G

# Main worker (default: 2G limit, 512M reservation)
WORKER_MEMORY_LIMIT=4G
WORKER_MEMORY_RESERVATION=1G

# Workflow worker (default: 2G limit, 512M reservation)
WORKFLOW_WORKER_MEMORY_LIMIT=4G
WORKFLOW_WORKER_MEMORY_RESERVATION=1G

# Web server (default: 1G limit, 256M reservation)
WEB_MEMORY_LIMIT=2G
WEB_MEMORY_RESERVATION=512M

# Redis (default: 512M limit, 128M reservation)
REDIS_MEMORY_LIMIT=1G
REDIS_MEMORY_RESERVATION=256M
REDIS_MAXMEMORY=1gb  # Redis internal limit
```

#### Celery Worker Settings

```bash
# Max tasks per child before recycling (default: 50)
# Higher = less recycling overhead, but more memory leak risk
CELERY_MAX_TASKS_PER_CHILD=200
```

### Example: High-RAM System Configuration

For a system with 32GB+ RAM:

```bash
# .env file
WORKER_CONCURRENCY=8
WORKFLOW_WORKER_CONCURRENCY=6
WORKER_MEMORY_LIMIT=8G
WORKFLOW_WORKER_MEMORY_LIMIT=8G
POSTGRES_MEMORY_LIMIT=4G
WEB_MEMORY_LIMIT=2G
REDIS_MEMORY_LIMIT=2G
REDIS_MAXMEMORY=2gb
CELERY_MAX_TASKS_PER_CHILD=200
```

## Monitoring

Check actual memory usage:

```bash
docker stats --no-stream
```

If containers are consistently near their limits, increase them. If they're well below, you can reduce them to free up RAM.

## Default Configuration Summary

**Current defaults (conservative for low-RAM systems):**

| Service | Memory Limit | Concurrency |
|---------|-------------|-------------|
| PostgreSQL | 2G | N/A |
| Redis | 512M | N/A |
| Web | 1G | N/A |
| Main Worker | 2G | 2 |
| Workflow Worker | 2G | 2 |
| Scheduler | 256M | N/A |

**Total cap**: ~6.5GB (prevents system hangs)

## Recommendations

1. **Start with defaults** - They're safe and prevent hangs
2. **Monitor usage** - Use `docker stats` to see actual consumption
3. **Increase gradually** - If you have more RAM and need more throughput:
   - First increase `WORKER_CONCURRENCY` (biggest performance impact)
   - Then increase memory limits if containers are hitting them
   - Finally increase `CELERY_MAX_TASKS_PER_CHILD` if you want less recycling

## Troubleshooting

**Containers being OOM-killed:**
- Increase memory limits for that specific container
- Check logs: `docker logs <container_name>`

**Tasks processing slowly:**
- Increase `WORKER_CONCURRENCY` and `WORKFLOW_WORKER_CONCURRENCY`
- Monitor CPU usage - if not maxed, you can increase concurrency

**System still hanging:**
- Check total memory usage: `docker stats`
- Ensure total limits don't exceed available RAM
- Consider reducing limits further if system has < 8GB RAM
