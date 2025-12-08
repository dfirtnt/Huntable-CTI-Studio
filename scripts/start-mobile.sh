#!/bin/bash

# Start CTI Scraper Mobile Instance
# This script starts the mobile-friendly nginx-based deployment

set -e

echo "🚀 Starting CTI Scraper Mobile Instance..."

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
echo "   HTTP:  http://$LOCAL_IP"
echo "   HTTPS: https://$LOCAL_IP"
echo ""

# Start the mobile deployment
echo "🐳 Starting Docker containers..."
docker-compose -f docker-compose.mobile.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check service health
echo "🔍 Checking service health..."

# Check nginx
if curl -s -k https://localhost/health > /dev/null 2>&1; then
    echo "✅ Nginx (HTTPS): OK"
else
    echo "⚠️  Nginx (HTTPS): Starting up..."
fi

# Check web app
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "✅ Web App: OK"
else
    echo "⚠️  Web App: Starting up..."
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
echo "3. Go to: https://$LOCAL_IP"
echo "4. Accept the security warning (self-signed certificate)"
echo "5. If needed, trust the certificate in iPhone Settings > General > About > Certificate Trust Settings"
echo ""
echo "🔧 Management Commands:"
echo "   Stop:    docker-compose -f docker-compose.mobile.yml down"
echo "   Logs:    docker-compose -f docker-compose.mobile.yml logs -f"
echo "   Status:  docker-compose -f docker-compose.mobile.yml ps"
echo ""
echo "📊 Service URLs:"
echo "   Web App:     http://localhost:8001"
echo "   HTTPS:       https://localhost"
echo "   Database:    localhost:5433"
echo "   Redis:       localhost:6380"
