#!/bin/bash
# Migration script: Add proc_tree_attention_preprocessor_enabled to agentic_workflow_config
# Run this script to add the column to your database
#
# REVIEW THIS SCRIPT BEFORE RUNNING. Inspect the ALTER TABLE statement below.

set -e

echo "Running migration: Add proc_tree_attention_preprocessor_enabled column..."

SQL="ALTER TABLE agentic_workflow_config ADD COLUMN IF NOT EXISTS proc_tree_attention_preprocessor_enabled BOOLEAN NOT NULL DEFAULT TRUE;"

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "${DOCKER_CONTAINER}" ]; then
    # Running inside Docker container
    echo "$SQL" | psql -U cti_user -d cti_scraper
else
    # Running on host, connect to Docker container
    echo "$SQL" | docker exec -i cti_postgres psql -U cti_user -d cti_scraper
fi

echo "Migration completed successfully!"
