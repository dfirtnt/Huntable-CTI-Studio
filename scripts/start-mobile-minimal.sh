#!/bin/bash

# Start CTI Scraper Mobile Instance (Minimal - Web Only)
# This starts just a mobile web server that connects to existing services

set -e

echo "🚀 Starting CTI Scraper Mobile Instance (Minimal Mode)..."

# Check if main services are running
if ! docker ps | grep -q cti_postgres; then
    echo "❌ Main CTI services not running. Please start them first:"
    echo "   docker-compose up -d"
    exit 1
fi

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
echo "   HTTP:  http://$LOCAL_IP:8002"
echo ""

# Start just the mobile web server
echo "🐳 Starting mobile web server..."
docker-compose -f docker-compose.mobile-simple.yml up -d

# Wait for service to be ready
echo "⏳ Waiting for mobile web server to start..."
sleep 10

# Check service health
echo "🔍 Checking service health..."

# Check web app directly
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "✅ Mobile Web App: OK"
else
    echo "⚠️  Mobile Web App: Starting up..."
fi

echo ""
echo "🎉 Mobile deployment started successfully!"
echo ""
echo "📱 iPhone Access Instructions:"
echo "1. Make sure your iPhone is on the same WiFi network"
echo "2. Open Safari on your iPhone"
echo "3. Go to: http://$LOCAL_IP:8002"
echo "4. The app should load with full functionality"
echo ""
echo "🔧 Management Commands:"
echo "   Stop:    docker-compose -f docker-compose.mobile-simple.yml down"
echo "   Logs:    docker-compose -f docker-compose.mobile-simple.yml logs -f"
echo "   Status:  docker-compose -f docker-compose.mobile-simple.yml ps"
echo ""
echo "📊 Service URLs:"
echo "   Mobile Web:  http://$LOCAL_IP:8002"
echo "   Local Web:   http://localhost:8002"
echo ""
echo "💡 This mobile instance shares the same database and services as your main instance."
