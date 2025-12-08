#!/bin/bash
# Migration script: Add qa_enabled to agentic_workflow_config
# Run this script to add the missing column to your database

set -e

echo "🔧 Running migration: Add qa_enabled column..."

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER}" ]; then
    # Running inside Docker container
    psql -U cti_user -d cti_scraper -f /app/scripts/add_qa_enabled.sql
else
    # Running on host, connect to Docker container
    docker exec -i cti_postgres psql -U cti_user -d cti_scraper < scripts/add_qa_enabled.sql
fi

echo "✅ Migration completed successfully!"

