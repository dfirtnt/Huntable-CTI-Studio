#!/bin/bash
# LMStudio MCP Server Setup Script

set -e

echo "🚀 Setting up LMStudio MCP Server for Cursor IDE..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is required but not installed."
    exit 1
fi

# Install required dependencies
echo "📦 Installing Python dependencies..."
pip3 install requests mcp

# Make the MCP server executable
chmod +x lmstudio-mcp-server.py

# Create environment file
echo "⚙️ Creating environment configuration..."
cat > .env.lmstudio << EOF
# LMStudio Configuration
LMSTUDIO_BASE_URL=http://localhost:1234
LMSTUDIO_API_KEY=
LOG_LEVEL=INFO
EOF

# Create Cursor settings template
echo "📝 Creating Cursor settings template..."
cat > cursor-settings-lmstudio.json << EOF
{
  "mcp.servers": {
    "lmstudio": {
      "command": "python",
      "args": ["$(pwd)/lmstudio-mcp-server.py"],
      "env": {
        "PYTHONPATH": "$(pwd)",
        "LMSTUDIO_BASE_URL": "http://localhost:1234",
        "LMSTUDIO_API_KEY": ""
      }
    }
  }
}
EOF

echo "✅ LMStudio MCP Server setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Install LMStudio from: https://lmstudio.ai/download"
echo "2. Load a model in LMStudio"
echo "3. Start the LMStudio server (Local Server tab → Start Server)"
echo "4. Add the configuration from cursor-settings-lmstudio.json to your Cursor settings"
echo "5. Restart Cursor IDE"
echo "6. Test with: lmstudio_check_models()"
echo ""
echo "📚 Documentation: LMSTUDIO_MCP_CONFIG.md"
echo "🔧 Configuration: cursor-settings-lmstudio.json"
echo "🌍 Environment: .env.lmstudio"
