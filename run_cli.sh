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
    echo "  sync-sources [--config <file>] [--validate-feeds] - Sync sources from YAML"
    echo "  export [--format <format>] [--days <days>]   - Export articles"
    echo "  stats                                         - Show statistics"
    echo "  backup create [--backup-dir <dir>] [--no-compress] - Create database backup"
    echo "  backup list [--backup-dir <dir>]              - List available backups"
    echo "  backup restore <file> [--backup-dir <dir>] [--force] - Restore database"
    echo "  rescore [--article-id <id>] [--force] [--dry-run] - Rescore threat hunting scores"
    echo "  embed [--batch-size <size>] [--annotation-type <type>] [--dry-run] - Generate embeddings for annotations"
    echo "  embed search [--limit <n>] [--threshold <score>] [--annotation-type <type>] - Semantic search"
    echo "  embed stats                                    - Show embedding statistics"
    echo ""
    echo "Examples:"
    echo "  $0 init"
    echo "  $0 collect --source threatpost"
    echo "  $0 sync-sources"
    echo "  $0 export --format json --days 7"
    echo "  $0 backup create"
    echo "  $0 backup list"
    echo "  $0 backup restore cti_scraper_backup_20250907_134653.sql.gz"
    echo "  $0 rescore --force"
    echo "  $0 rescore --article-id 965"
    echo "  $0 embed --batch-size 1000"
    echo "  $0 embed search --limit 10 --threshold 0.7"
    echo "  $0 embed stats"
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
        echo "Note: Sources management is now handled via the web interface at http://localhost:8001/sources"
        echo "Available CLI commands:"
        echo "  sync-sources  - Synchronize database sources from YAML configuration"
        echo "  stats         - Show database statistics including sources"
        exit 0
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
    "backup")
        CLI_CMD="$CLI_CMD backup"
        shift
        case "$1" in
            "create")
                CLI_CMD="$CLI_CMD create"
                shift
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --backup-dir)
                            CLI_CMD="$CLI_CMD --backup-dir $2"
                            shift 2
                            ;;
                        --no-compress)
                            CLI_CMD="$CLI_CMD --no-compress"
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
            "list")
                CLI_CMD="$CLI_CMD list"
                shift
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --backup-dir)
                            CLI_CMD="$CLI_CMD --backup-dir $2"
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
            "restore")
                if [ $# -lt 2 ]; then
                    echo "Error: backup restore requires <file>"
                    show_usage
                    exit 1
                fi
                CLI_CMD="$CLI_CMD restore $2"
                shift 2
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --backup-dir)
                            CLI_CMD="$CLI_CMD --backup-dir $2"
                            shift 2
                            ;;
                        --force)
                            CLI_CMD="$CLI_CMD --force"
                            shift
                            ;;
                        --no-snapshot)
                            CLI_CMD="$CLI_CMD --no-snapshot"
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
            *)
                echo "Unknown backup command: $1"
                show_usage
                exit 1
                ;;
        esac
        ;;
    "rescore")
        CLI_CMD="$CLI_CMD rescore"
        shift
        while [[ $# -gt 0 ]]; do
            case $1 in
                --article-id)
                    CLI_CMD="$CLI_CMD --article-id $2"
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
    "embed")
        CLI_CMD="$CLI_CMD embed"
        shift
        case "$1" in
            "search")
                CLI_CMD="$CLI_CMD search"
                shift
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --limit)
                            CLI_CMD="$CLI_CMD --limit $2"
                            shift 2
                            ;;
                        --threshold)
                            CLI_CMD="$CLI_CMD --threshold $2"
                            shift 2
                            ;;
                        --annotation-type)
                            CLI_CMD="$CLI_CMD --annotation-type $2"
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
                # Default embed command (generate embeddings)
                while [[ $# -gt 0 ]]; do
                    case $1 in
                        --batch-size)
                            CLI_CMD="$CLI_CMD --batch-size $2"
                            shift 2
                            ;;
                        --annotation-type)
                            CLI_CMD="$CLI_CMD --annotation-type $2"
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
        esac
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
