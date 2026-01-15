#!/bin/bash
# Tear down test containers
# Usage: ./scripts/test_teardown.sh

set -e

echo "Stopping test containers..."
docker compose -f docker-compose.test.yml down

echo "Test containers stopped and removed (data destroyed)"
