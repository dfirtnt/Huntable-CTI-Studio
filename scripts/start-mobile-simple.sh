#!/bin/bash

# Start CTI Scraper Mobile Instance (Simple HTTP-only version)
# This bypasses nginx and runs the web app directly on port 80

set -e

echo "🚀 Starting CTI Scraper Mobile Instance (Simple Mode)..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please create one from env.example"
    exit 1
fi

# Get local IP address for mobile access
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="localhost"
fi

echo "📱 Mobile access will be available at:"
echo "   HTTP:  http://$LOCAL_IP:8001"
echo ""

# Start just the core services without nginx
echo "🐳 Starting Docker containers..."
docker-compose -f docker-compose.mobile.yml up -d postgres redis web worker scheduler

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 15

# Check service health
echo "🔍 Checking service health..."

# Check web app directly
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "✅ Web App (Direct): OK"
else
    echo "⚠️  Web App (Direct): Starting up..."
fi

# Check database
if docker exec cti_postgres_mobile pg_isready -U cti_user > /dev/null 2>&1; then
    echo "✅ Database: OK"
else
    echo "⚠️  Database: Starting up..."
fi

echo ""
echo "🎉 Mobile deployment started successfully!"
echo ""
echo "📱 iPhone Access Instructions:"
echo "1. Make sure your iPhone is on the same WiFi network"
echo "2. Open Safari on your iPhone"
echo "3. Go to: http://$LOCAL_IP:8001"
echo "4. The app should load directly without nginx"
echo ""
echo "🔧 Management Commands:"
echo "   Stop:    docker-compose -f docker-compose.mobile.yml down"
echo "   Logs:    docker-compose -f docker-compose.mobile.yml logs -f web"
echo "   Status:  docker-compose -f docker-compose.mobile.yml ps"
echo ""
echo "📊 Service URLs:"
echo "   Web App:     http://localhost:8001"
echo "   Mobile:      http://$LOCAL_IP:8001"
echo "   Database:    localhost:5433"
echo "   Redis:       localhost:6380"
