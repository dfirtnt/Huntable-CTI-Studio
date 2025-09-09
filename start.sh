#!/bin/bash

# CTI Scraper Startup Script
# Single script for development use

set -e

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

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs data nginx/ssl

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down --remove-orphans

# Build and start the stack
echo "🔨 Building and starting stack..."
docker-compose up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 15

# Check service health
echo "🏥 Checking service health..."

# Check PostgreSQL
if docker-compose exec -T postgres pg_isready -U cti_user -d cti_scraper > /dev/null 2>&1; then
    echo "✅ PostgreSQL is ready"
else
    echo "❌ PostgreSQL is not ready"
    docker-compose logs postgres
    exit 1
fi

# Check Redis
if docker-compose exec -T redis redis-cli --raw incr ping > /dev/null 2>&1; then
    echo "✅ Redis is ready"
else
    echo "❌ Redis is not ready"
    docker-compose logs redis
    exit 1
fi

# Check web service
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Web service is ready"
else
    echo "❌ Web service is not ready"
    docker-compose logs web
    exit 1
fi

echo ""
echo "🎉 CTI Scraper is running!"
echo ""
echo "📊 Services:"
echo "   • Web Interface: http://localhost:8000"
echo "   • PostgreSQL:    postgres:5432 (Docker container)"
echo "   • Redis:         redis:6379 (Docker container)"
echo "   • Ollama:        ollama:11434 (Docker container)"
echo ""
echo "🔧 Management:"
echo "   • CLI Commands:  ./run_cli.sh <command>"
echo "   • View logs:     docker-compose logs -f [service]"
echo "   • Stop stack:    docker-compose down"
echo "   • Restart:       docker-compose restart [service]"
echo ""
echo "📈 Monitoring:"
echo "   • Health check:  http://localhost:8000/health"
echo "   • Database stats: http://localhost:8000/api/sources"
echo ""

# Show running containers
echo "🐳 Running containers:"
docker-compose ps

echo ""
echo "✨ Startup complete!"
echo ""
echo "💡 Quick start:"
echo "   • Initialize sources: ./run_cli.sh init"
echo "   • List sources:       ./run_cli.sh sources list"
echo "   • Collect articles:   ./run_cli.sh collect"
echo ""
