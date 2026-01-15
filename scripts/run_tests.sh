#!/bin/bash
# Test runner that auto-configures environment variables
# Usage: ./scripts/run_tests.sh [pytest args...]

set -e

# Auto-set APP_ENV=test
export APP_ENV=test

# Auto-construct TEST_DATABASE_URL from defaults if not set
if [ -z "$TEST_DATABASE_URL" ]; then
    POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-cti_password}
    export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@localhost:5433/cti_scraper_test"
    echo "Auto-set TEST_DATABASE_URL=${TEST_DATABASE_URL}"
fi

# Ensure test environment guard will pass
if [ "$APP_ENV" != "test" ]; then
    echo "Error: APP_ENV must be 'test'"
    exit 1
fi

# Run pytest with provided arguments
exec python3 -m pytest "$@"
