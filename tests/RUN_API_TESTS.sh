#!/bin/bash
# Quick script to run API tests with correct test database
# Password is read from .env file automatically

set -e

echo "🧪 Running API Tests with Test Database"
echo "========================================"
echo ""

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep POSTGRES_PASSWORD | xargs)
fi

required_containers=("cti_postgres_test" "cti_redis_test")
missing_containers=()

for container in "${required_containers[@]}"; do
    if ! docker ps --filter "name=${container}" --format "{{.Names}}" | grep -q "${container}"; then
        missing_containers+=("${container}")
    fi
done

if [ ${#missing_containers[@]} -gt 0 ]; then
    echo "Test containers not running: ${missing_containers[*]}. Starting them..."
    docker compose -f docker-compose.test.yml up -d postgres_test redis_test
    echo "Waiting for containers to be healthy..."
    timeout=60
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        all_healthy=true
        for service in postgres_test redis_test; do
            container_id=$(docker compose -f docker-compose.test.yml ps -q "$service")
            if [ -z "$container_id" ]; then
                all_healthy=false
                break
            fi

            status=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || echo "unknown")
            if [ "$status" != "healthy" ]; then
                all_healthy=false
                break
            fi
        done

        if [ "$all_healthy" = true ]; then
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
fi

# Export environment variables (password from .env)
export APP_ENV=test
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-cti_password}
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@localhost:5433/cti_scraper_test"
export USE_ASGI_CLIENT=1

echo "✅ Environment configured"
echo "   APP_ENV=$APP_ENV"
echo "   TEST_DATABASE_URL=postgresql+asyncpg://cti_user:***@localhost:5433/cti_scraper_test"
echo "   USE_ASGI_CLIENT=$USE_ASGI_CLIENT"
echo ""

# Run tests
if [ -z "$1" ]; then
    echo "🚀 Running all API tests..."
    .venv/bin/pytest tests/api/ -v
else
    echo "🚀 Running: $1"
    .venv/bin/pytest "$1" -v
fi
