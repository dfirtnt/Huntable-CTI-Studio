#!/bin/bash

# CTI Scraper CLI Runner Script
# This script runs CLI commands in the Docker container

set -e

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Please run this script from the CTI Scraper root directory."
    exit 1
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 <cli args>"
    echo ""
    echo "Examples:"
    echo "  $0 --help"
    echo "  $0 init --config config/sources.yaml"
    echo "  $0 collect --source threatpost --dry-run"
    echo "  $0 search --query ransomware --limit 25 --format json"
    echo "  $0 sync-sources --config config/sources.yaml --no-remove"
    echo "  $0 backup create --backup-dir backups/"
    echo "  $0 rescore --article-id 123 --dry-run"
    echo "  $0 embed stats"
    echo ""
    echo "Pass any args supported by 'python -m src.cli.main --help'."
}

# Check if command is provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

echo "🚀 Running CLI command in Docker: python -m src.cli.main $*"
echo ""

# Run the command in the CLI container (pass args directly to click CLI)
docker-compose run --rm cli python -m src.cli.main "$@"
