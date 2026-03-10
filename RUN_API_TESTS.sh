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

# Check if test containers are running
if ! docker ps | grep -q cti_postgres_test; then
    echo "⚠️  Test containers not running. Starting them..."
    docker-compose -f docker-compose.test.yml up -d
    echo "⏳ Waiting for containers to be healthy..."
    sleep 5
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
