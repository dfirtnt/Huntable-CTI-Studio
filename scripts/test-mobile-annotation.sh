#!/bin/bash

# Mobile Annotation Testing Script
# Tests the mobile-optimized annotation system using Playwright

set -e

echo "🧪 Testing Mobile Annotation System..."

# Check if mobile web server is running
echo "🔍 Checking mobile web server..."
if ! curl -s http://192.168.1.194:8002/health > /dev/null 2>&1; then
    echo "❌ Mobile web server not running. Starting it..."
    ./scripts/start-mobile-minimal.sh
    sleep 10
fi

# Check if mobile web server is healthy
if curl -s http://192.168.1.194:8002/health | grep -q "healthy"; then
    echo "✅ Mobile web server is healthy"
else
    echo "❌ Mobile web server is not healthy"
    exit 1
fi

# Create test results directory
mkdir -p test-results/videos/mobile

# Run mobile annotation tests
echo "📱 Running mobile annotation tests..."
python3 -m pytest tests/ui/test_mobile_annotation.py -v \
    --tb=short \
    --html=test-results/mobile-annotation-report.html \
    --self-contained-html \
    --capture=no

# Check test results
if [ $? -eq 0 ]; then
    echo "✅ Mobile annotation tests passed!"
    echo "📊 Test report: test-results/mobile-annotation-report.html"
    echo "🎥 Test videos: test-results/videos/mobile/"
else
    echo "❌ Mobile annotation tests failed!"
    exit 1
fi

echo "🎉 Mobile annotation testing complete!"
