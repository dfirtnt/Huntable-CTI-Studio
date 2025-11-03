#!/bin/bash
# Migration script: Add junk_filter_threshold to agentic_workflow_config
# Run this script to add the missing column to your database

set -e

echo "🔧 Running migration: Add junk_filter_threshold column..."

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER}" ]; then
    # Running inside Docker container
    psql -U cti_user -d cti_scraper -f /app/scripts/add_junk_filter_threshold.sql
else
    # Running on host, connect to Docker container
    docker exec -i cti_postgres psql -U cti_user -d cti_scraper < scripts/add_junk_filter_threshold.sql
fi

echo "✅ Migration completed successfully!"

