#!/bin/bash

# CTI Scraper Development Startup Script
# This script starts the development stack with CLI tools

set -e

echo "🚀 Starting CTI Scraper Development Stack..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "docker-compose.dev.yml" ]; then
    echo "❌ Please run this script from the CTI Scraper root directory."
    exit 1
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs data nginx/ssl

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.dev.yml down --remove-orphans

# Build and start the development stack
echo "🔨 Building and starting development stack..."
docker-compose -f docker-compose.dev.yml up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 15

# Check service health
echo "🏥 Checking service health..."

# Check PostgreSQL
if docker-compose -f docker-compose.dev.yml exec -T postgres pg_isready -U cti_user -d cti_scraper > /dev/null 2>&1; then
    echo "✅ PostgreSQL is ready"
else
    echo "❌ PostgreSQL is not ready"
    docker-compose -f docker-compose.dev.yml logs postgres
    exit 1
fi

# Check Redis
if docker-compose -f docker-compose.dev.yml exec -T redis redis-cli --raw incr ping > /dev/null 2>&1; then
    echo "✅ Redis is ready"
else
    echo "❌ Redis is not ready"
    docker-compose -f docker-compose.dev.yml logs redis
    exit 1
fi

# Check web service
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Web service is ready"
else
    echo "❌ Web service is not ready"
    docker-compose -f docker-compose.dev.yml logs web
    exit 1
fi

echo ""
echo "🎉 CTI Scraper Development Stack is running!"
echo ""
echo "📊 Services:"
echo "   • Web Interface: http://localhost:8000"
echo "   • PostgreSQL:    localhost:5432"
echo "   • Redis:         localhost:6379"
echo "   • Ollama:        localhost:11434"
echo ""
echo "🔧 Management:"
echo "   • CLI Commands:  ./run_cli.sh <command>"
echo "   • View logs:     docker-compose -f docker-compose.dev.yml logs -f [service]"
echo "   • Stop stack:    docker-compose -f docker-compose.dev.yml down"
echo "   • Restart:       docker-compose -f docker-compose.dev.yml restart [service]"
echo ""
echo "📈 Monitoring:"
echo "   • Health check:  http://localhost:8000/health"
echo "   • Database stats: http://localhost:8000/api/sources"
echo ""

# Show running containers
echo "🐳 Running containers:"
docker-compose -f docker-compose.dev.yml ps

echo ""
echo "✨ Development stack startup complete!"
echo ""
echo "💡 Quick start:"
echo "   • Initialize sources: ./run_cli.sh init"
echo "   • List sources:       ./run_cli.sh sources list"
echo "   • Collect articles:   ./run_cli.sh collect"
echo ""
