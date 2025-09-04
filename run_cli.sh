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
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Available commands:"
    echo "  init [--config <file>] [--validate-feeds]     - Initialize sources"
    echo "  collect [--source <id>] [--force] [--dry-run] - Collect articles"
    echo "  monitor [--interval <seconds>]               - Monitor sources"
    echo "  test [--source <id>] [--dry-run]              - Test sources"
    echo "  sources list [--active] [--format <format>]   - List sources"
    echo "  sources add <id> <name> <url> [--rss-url]    - Add source"
    echo "  sources disable <id>                         - Disable source"
    echo "  export [--format <format>] [--days <days>]   - Export articles"
    echo "  stats                                         - Show statistics"
    echo ""
    echo "Examples:"
    echo "  $0 init"
    echo "  $0 collect --source threatpost"
    echo "  $0 sources list --active"
    echo "  $0 export --format json --days 7"
}

# Check if command is provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

# Build the CLI command
CLI_CMD="python -m src.cli.main"

# Convert arguments to CLI format
case "$1" in
    "init")
        CLI_CMD="$CLI_CMD init"
        shift
        while [[ $# -gt 0 ]]; do
            case $1 in
                --config)
                    CLI_CMD="$CLI_CMD --config $2"
                    shift 2
                    ;;
                --validate-feeds)
                    CLI_CMD="$CLI_CMD --validate-feeds"
                    shift
                    ;;
                *)
                    echo "Unknown option: $1"
                    show_usage
                    exit 1
                    ;;
            esac
        done
        ;;
    "collect")
        CLI_CMD="$CLI_CMD collect"
        shift
        while [[ $# -gt 0 ]]; do
            case $1 in
                --source)
                    CLI_CMD="$CLI_CMD --source $2"
                    shift 2
                    ;;
                --force)
                    CLI_CMD="$CLI_CMD --force"
                    shift
                    ;;
                --dry-run)
                    CLI_CMD="$CLI_CMD --dry-run"
                    shift
                    ;;
                *)
                    echo "Unknown option: $1"
                    show_usage
                    exit 1
                    ;;
            esac
        done
        ;;
    "monitor")
        CLI_CMD="$CLI_CMD monitor"
        shift
        while [[ $# -gt 0 ]]; do
            case $1 in
                --interval)
                    CLI_CMD="$CLI_CMD --interval $2"
                    shift 2
                    ;;
                *)
                    echo "Unknown option: $1"
                    show_usage
                    exit 1
                    ;;
            esac
        done
        ;;
    "test")
        CLI_CMD="$CLI_CMD test"
        shift
        while [[ $# -gt 0 ]]; do
            case $1 in
                --source)
                    CLI_CMD="$CLI_CMD --source $2"
                    shift 2
                    ;;
                --dry-run)
                    CLI_CMD="$CLI_CMD --dry-run"
                    shift
                    ;;
                *)
                    echo "Unknown option: $1"
                    show_usage
                    exit 1
                    ;;
            esac
        done
        ;;
    "sources")
        CLI_CMD="$CLI_CMD sources"
        shift
        case "$1" in
            "list")
                CLI_CMD="$CLI_CMD list"
                shift
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --active)
                            CLI_CMD="$CLI_CMD --active"
                            shift
                            ;;
                        --format)
                            CLI_CMD="$CLI_CMD --format $2"
                            shift 2
                            ;;
                        *)
                            echo "Unknown option: $1"
                            show_usage
                            exit 1
                            ;;
                    esac
                done
                ;;
            "add")
                if [ $# -lt 4 ]; then
                    echo "Error: sources add requires <id> <name> <url>"
                    show_usage
                    exit 1
                fi
                CLI_CMD="$CLI_CMD add $2 $3 $4"
                shift 4
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --rss-url)
                            CLI_CMD="$CLI_CMD --rss-url $2"
                            shift 2
                            ;;
                        *)
                            echo "Unknown option: $1"
                            show_usage
                            exit 1
                            ;;
                    esac
                done
                ;;
            "disable")
                if [ $# -lt 2 ]; then
                    echo "Error: sources disable requires <id>"
                    show_usage
                    exit 1
                fi
                CLI_CMD="$CLI_CMD disable $2"
                ;;
            *)
                echo "Unknown sources command: $1"
                show_usage
                exit 1
                ;;
        esac
        ;;
    "export")
        CLI_CMD="$CLI_CMD export"
        shift
        while [[ $# -gt 0 ]]; do
            case $1 in
                --format)
                    CLI_CMD="$CLI_CMD --format $2"
                    shift 2
                    ;;
                --days)
                    CLI_CMD="$CLI_CMD --days $2"
                    shift 2
                    ;;
                --output)
                    CLI_CMD="$CLI_CMD --output $2"
                    shift 2
                    ;;
                --source)
                    CLI_CMD="$CLI_CMD --source $2"
                    shift 2
                    ;;
                *)
                    echo "Unknown option: $1"
                    show_usage
                    exit 1
                    ;;
            esac
        done
        ;;
    "stats")
        CLI_CMD="$CLI_CMD stats"
        ;;
    *)
        echo "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac

echo "🚀 Running CLI command in Docker: $CLI_CMD"
echo ""

# Run the command in the CLI container
docker-compose run --rm cli $CLI_CMD
