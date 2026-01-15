#!/bin/bash
# Start test containers for running tests
# Usage: ./scripts/test_setup.sh

set -e

echo "Starting test containers..."
docker compose -f docker-compose.test.yml up -d

echo "Waiting for containers to be healthy..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker compose -f docker-compose.test.yml ps | grep -q "healthy"; then
        echo "Test containers are ready!"
        exit 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

echo "Warning: Containers may not be fully healthy yet"
docker compose -f docker-compose.test.yml ps
