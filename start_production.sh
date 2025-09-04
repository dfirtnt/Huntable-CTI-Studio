#!/bin/bash

# CTI Scraper Production Startup Script
# This script starts the complete production stack

set -e

echo "🚀 Starting CTI Scraper Production Stack..."

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

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD:-cti_password_2024}@postgres:5432/cti_scraper"
export REDIS_URL="redis://:cti_redis_2024@redis:6379/0"
export ENVIRONMENT="production"
export LOG_LEVEL="INFO"
export SOURCES_CONFIG="/app/config/sources.yaml"

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down --remove-orphans

# Build and start the stack
echo "🔨 Building and starting production stack..."
docker-compose up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

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

# Check Nginx
if curl -f http://localhost/health > /dev/null 2>&1; then
    echo "✅ Nginx is ready"
else
    echo "❌ Nginx is not ready"
    docker-compose logs nginx
    exit 1
fi

echo ""
echo "🎉 CTI Scraper Production Stack is running!"
echo ""
echo "📊 Services:"
echo "   • Web Interface: http://localhost:8000"
echo "   • Nginx Proxy:   http://localhost"
echo "   • PostgreSQL:    localhost:5432"
echo "   • Redis:         localhost:6379"
echo "   • Flower (Celery): http://localhost:5555"
echo ""
echo "🔧 Management:"
echo "   • View logs:     docker-compose logs -f [service]"
echo "   • Stop stack:    docker-compose down"
echo "   • Restart:       docker-compose restart [service]"
echo ""
echo "📈 Monitoring:"
echo "   • Health check:  http://localhost/health"
echo "   • Database stats: http://localhost:8000/api/sources"
echo ""

# Show running containers
echo "🐳 Running containers:"
docker-compose ps

echo ""
echo "✨ Production stack startup complete!"
