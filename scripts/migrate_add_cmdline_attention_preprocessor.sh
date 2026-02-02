#!/bin/bash
# Migration script: Add cmdline_attention_preprocessor_enabled to agentic_workflow_config
# Run this script to add the column to your database

set -e

echo "🔧 Running migration: Add cmdline_attention_preprocessor_enabled column..."

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER}" ]; then
    # Running inside Docker container
    psql -U cti_user -d cti_scraper -f /app/scripts/add_cmdline_attention_preprocessor.sql
else
    # Running on host, connect to Docker container
    docker exec -i cti_postgres psql -U cti_user -d cti_scraper < scripts/add_cmdline_attention_preprocessor.sql
fi

echo "✅ Migration completed successfully!"
