#!/bin/sh
# Create test DB so tests can use same Postgres (TEST_DATABASE_URL with port 5432).
# Runs before init.sql (alphabetical order in docker-entrypoint-initdb.d).
set -e
psql -v ON_ERROR_STOP=0 -d postgres -c "CREATE DATABASE cti_scraper_test OWNER cti_user" || true
psql -v ON_ERROR_STOP=0 -d cti_scraper_test -c "CREATE EXTENSION IF NOT EXISTS vector" || true
