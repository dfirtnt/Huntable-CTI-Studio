#!/bin/bash

# CTIScraper Browser Extension Installation Script

echo "🛡️ CTIScraper Browser Extension Setup"
echo "====================================="

# Create simple placeholder icons
echo "Creating placeholder icons..."

# Create a simple 16x16 icon (base64 encoded 1x1 blue pixel)
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" | base64 -d > icons/icon16.png
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" | base64 -d > icons/icon32.png
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" | base64 -d > icons/icon48.png
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" | base64 -d > icons/icon128.png

echo "✅ Extension files created!"
echo ""
echo "📋 Installation Instructions:"
echo "1. Open Chrome/Edge and go to chrome://extensions/"
echo "2. Enable 'Developer mode' (toggle in top right)"
echo "3. Click 'Load unpacked' and select this browser-extension folder"
echo "4. Click the CTIScraper icon in your browser toolbar to use"
echo ""
echo "🧪 Testing Instructions:"
echo "1. Open the test-article.html file in your browser"
echo "2. Click the CTIScraper extension icon"
echo "3. Verify it extracts the article title and content"
echo "4. Click 'Send to CTIScraper' to test the API integration"
echo ""
echo "🔧 Configuration:"
echo "- Default API URL: http://127.0.0.1:8000"
echo "- Modify in extension popup if needed"
echo ""
echo "🚀 Ready to use! Navigate to any article and click the extension icon."
