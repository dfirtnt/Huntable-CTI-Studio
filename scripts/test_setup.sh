#!/bin/bash
# Start test containers for running tests
# Usage: ./scripts/test_setup.sh

set -e

echo "Starting test containers..."
docker compose -f docker-compose.test.yml up -d postgres_test redis_test

echo "Waiting for containers to be healthy..."
timeout=60
elapsed=0
required_services=("postgres_test" "redis_test")
while [ $elapsed -lt $timeout ]; do
    all_healthy=true

    for service in "${required_services[@]}"; do
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
        echo "Test containers are ready!"
        exit 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

echo "Warning: Containers did not become healthy within ${timeout}s"
docker compose -f docker-compose.test.yml ps
