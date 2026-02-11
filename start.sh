#!/bin/bash

# CTI Scraper Startup Script
# Single script for development use

set -e

# Prefer docker compose (plugin) if docker-compose not found
if command -v docker-compose > /dev/null 2>&1; then
    DC="docker-compose"
else
    DC="docker compose"
fi

echo "🚀 Starting CTI Scraper..."

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

# Skip embedding-dependent steps when we warned about limited/untested environment
SKIP_SIGMA_INDEX=""

# Check OS and CPU: warn if not macOS or not Apple Silicon
if [ "$(uname -s)" != "Darwin" ]; then
    echo ""
    echo "⚠️  WARNING: Not running on macOS + Apple Silicon + LMStudio (detected: $(uname -s))."
    echo ""
    echo "   This project has not been tested on Windows or Linux."
    echo "   You may encounter compatibility or performance issues."
    echo ""
    printf "   Do you want to continue the install? [y/N] "
    read -r cont
    case "${cont:-n}" in
        [yY]|[yY][eE][sS]) SKIP_SIGMA_INDEX=1 ;;
        *) echo "   Install cancelled."; exit 0 ;;
    esac
    echo ""
elif [ "$(uname -m)" != "arm64" ]; then
    echo ""
    echo "⚠️  WARNING: Not running on Apple Silicon (detected: $(uname -m))."
    echo ""
    echo "   The app will not be fully functional on this architecture."
    echo "   Working: CTI Article ingestion, regex scoring/annotation systems."
    echo "   Limited: Many features that require embeddings will not work correctly."
    echo ""
    echo "   If LMStudio isn't running:"
    echo "   • Local models — You can't list, load, or test local models in the app;"
    echo "     that only works when LMStudio is available."
    echo "   • Sigma rules in search — Sigma rules won't be indexed, so search/RAG"
    echo "     won't use SigmaHQ rules."
    echo ""
    printf "   Do you want to continue the install? [y/N] "
    read -r cont
    case "${cont:-n}" in
        [yY]|[yY][eE][sS]) SKIP_SIGMA_INDEX=1 ;;
        *) echo "   Install cancelled."; exit 0 ;;
    esac
    echo ""
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs data

# Stop any existing containers
echo "🛑 Stopping existing containers..."
$DC down --remove-orphans

# Build and start the stack
echo "🔨 Building and starting stack..."
$DC up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 15

# Check service health
echo "🏥 Checking service health..."

# Check PostgreSQL
if $DC exec -T postgres pg_isready -U cti_user -d cti_scraper > /dev/null 2>&1; then
    echo "✅ PostgreSQL is ready"
else
    echo "❌ PostgreSQL is not ready"
    $DC logs postgres
    exit 1
fi

# Check Redis
if $DC exec -T redis redis-cli --raw incr ping > /dev/null 2>&1; then
    echo "✅ Redis is ready"
else
    echo "❌ Redis is not ready"
    $DC logs redis
    exit 1
fi

# Check web service
if curl -f http://localhost:8001/health > /dev/null 2>&1; then
    echo "✅ Web service is ready"
else
    echo "❌ Web service is not ready"
    $DC logs web
    exit 1
fi

# Sigma: sync SigmaHQ repo; index rules (embeddings) only when not in limited-env mode
echo ""
echo "📋 Sigma: syncing SigmaHQ repo..."
if $DC run --rm cli python -m src.cli.main sigma sync 2>/dev/null; then
    if [ -n "$SKIP_SIGMA_INDEX" ]; then
        echo "⏭️  Skipping Sigma index (embeddings/LM Studio not assumed). Run ./run_cli.sh sigma index when LM Studio is available."
    elif $DC run --rm cli python -m src.cli.main sigma index 2>/dev/null; then
        echo "✅ Sigma rules synced and indexed"
    else
        echo "⚠️ Sigma index failed (run manually: ./run_cli.sh sigma index)"
    fi
else
    echo "⚠️ Sigma sync failed (run manually: ./run_cli.sh sigma sync)"
fi

echo ""
echo "🎉 CTI Scraper is running!"
echo ""
echo "📊 Services:"
echo "   • Web Interface: http://localhost:8001"
echo "   • PostgreSQL:    postgres:5432 (Docker container)"
echo "   • Redis:         redis:6379 (Docker container)"
echo ""
echo "🔧 Management:"
echo "   • CLI Commands:  ./run_cli.sh <command>"
echo "   • View logs:     $DC logs -f [service]"
echo "   • Stop stack:    $DC down"
echo "   • Restart:       $DC restart [service]"
echo ""
echo "📈 Monitoring:"
echo "   • Health check:  http://localhost:8001/health"
echo "   • Database stats: http://localhost:8001/api/sources"
echo ""

# Show running containers
echo "🐳 Running containers:"
$DC ps

echo ""
echo "✨ Startup complete!"
echo ""
echo "💡 Quick start:"
echo "   Sources are auto-seeded from config/sources.yaml on first run (if the DB has fewer than 5 sources)."
echo "   SigmaHQ repo is synced and indexed at startup (similarity search). Re-run: ./run_cli.sh sigma sync && ./run_cli.sh sigma index"
echo "   RSS/scraping runs automatically every 30 minutes via Celery Beat; no extra step required."
echo ""
echo "   • Reload sources from YAML:  ./run_cli.sh init"
echo "   • DB stats (sources):       ./run_cli.sh stats"
echo "   • Collect articles now:     ./run_cli.sh collect  (otherwise wait for the next 30-min run)"
echo ""
