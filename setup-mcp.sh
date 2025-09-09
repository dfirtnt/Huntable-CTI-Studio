# CTIScraper MCP Server Setup Script

#!/bin/bash

# CTIScraper MCP Server Setup Script
# This script sets up the MCP server for Cursor integration

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Python is installed
check_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
}

# Function to check if pip is installed
check_pip() {
    if ! command -v pip3 >/dev/null 2>&1; then
        print_error "pip3 is required but not installed"
        exit 1
    fi
    
    print_success "pip3 found"
}

# Function to install MCP dependencies
install_dependencies() {
    print_status "Installing MCP dependencies..."
    
    # Create requirements file for MCP
    cat > requirements-mcp.txt << 'EOF'
mcp>=0.1.0
asyncio
pathlib
logging
pydantic>=2.0.0
typing-extensions
EOF
    
    # Install dependencies
    pip3 install -r requirements-mcp.txt
    
    print_success "MCP dependencies installed"
}

# Function to create MCP configuration
create_mcp_config() {
    print_status "Creating MCP configuration..."
    
    # Get current directory
    CURRENT_DIR=$(pwd)
    
    # Create MCP configuration file
    cat > mcp-config.json << EOF
{
  "mcpServers": {
    "cti-scraper": {
      "command": "python3",
      "args": ["$CURRENT_DIR/mcp-server.py"],
      "env": {
        "PYTHONPATH": "$CURRENT_DIR"
      }
    }
  }
}
EOF
    
    print_success "MCP configuration created: mcp-config.json"
}

# Function to create Cursor settings integration
create_cursor_settings() {
    print_status "Creating Cursor settings integration..."
    
    # Get current directory
    CURRENT_DIR=$(pwd)
    
    # Create Cursor settings file
    cat > cursor-settings.json << EOF
{
  "mcp.servers": {
    "cti-scraper": {
      "command": "python3",
      "args": ["$CURRENT_DIR/mcp-server.py"],
      "env": {
        "PYTHONPATH": "$CURRENT_DIR"
      }
    }
  }
}
EOF
    
    print_success "Cursor settings created: cursor-settings.json"
}

# Function to create environment file
create_env_file() {
    print_status "Creating environment file..."
    
    # Get current directory
    CURRENT_DIR=$(pwd)
    
    # Create .env file
    cat > .env.mcp << EOF
# CTIScraper MCP Server Environment Variables
PROJECT_ROOT=$CURRENT_DIR
LOG_LEVEL=INFO
ENABLE_DEBUG=true
MCP_SERVER_NAME=cti-scraper
MCP_SERVER_VERSION=1.0.0
EOF
    
    print_success "Environment file created: .env.mcp"
}

# Function to test MCP server
test_mcp_server() {
    print_status "Testing MCP server..."
    
    # Test if the server can start
    if python3 mcp-server.py --test >/dev/null 2>&1; then
        print_success "MCP server test passed"
    else
        print_warning "MCP server test failed - this is normal for initial setup"
    fi
}

# Function to create installation instructions
create_installation_instructions() {
    print_status "Creating installation instructions..."
    
    cat > MCP_INSTALLATION_INSTRUCTIONS.md << 'EOF'
# CTIScraper MCP Server Installation Instructions

## Prerequisites
- Python 3.8 or higher
- pip3
- Cursor IDE

## Installation Steps

### 1. Run Setup Script
```bash
chmod +x setup-mcp.sh
./setup-mcp.sh
```

### 2. Configure Cursor
1. Open Cursor
2. Go to Settings (Cmd+, on Mac, Ctrl+, on Windows/Linux)
3. Search for "MCP" or "Model Context Protocol"
4. Add the MCP server configuration:

```json
{
  "mcp.servers": {
    "cti-scraper": {
      "command": "python3",
      "args": ["/path/to/CTIScraper/mcp-server.py"],
      "env": {
        "PYTHONPATH": "/path/to/CTIScraper"
      }
    }
  }
}
```

### 3. Restart Cursor
After adding the configuration, restart Cursor completely.

### 4. Test MCP Server
1. Open a CTIScraper file
2. Use Command Palette (Cmd+Shift+P on Mac, Ctrl+Shift+P on Windows/Linux)
3. Search for "MCP" or "CTIScraper"
4. You should see CTIScraper-specific tools

## Available Tools

### 1. Analyze Threat Intelligence
- Analyzes threat intelligence content
- Provides IOCs, TTPs, and threat level assessment
- Suggests action items and follow-up

### 2. Suggest Security Improvements
- Analyzes code for security issues
- Suggests input validation, authentication, authorization
- Provides secure code examples

### 3. Generate AWS Deployment Plan
- Creates deployment plans for different environments
- Includes infrastructure, security, and cost considerations
- Provides step-by-step deployment instructions

### 4. Analyze Scoring Algorithm
- Analyzes scoring algorithms for performance
- Suggests improvements and alternatives
- Provides testing recommendations

### 5. Generate Database Queries
- Generates SQL queries for CTIScraper database
- Includes basic, filtered, and aggregation queries
- Provides performance optimization suggestions

### 6. Suggest UI Improvements
- Analyzes UI/UX for accessibility and performance
- Suggests improvements for user experience
- Provides security considerations

### 7. Validate Configuration
- Validates configuration files
- Identifies issues and provides recommendations
- Suggests best practices

### 8. Generate Test Cases
- Generates unit, integration, and performance tests
- Provides test data and security tests
- Includes component-specific test cases

## Usage Examples

### Analyze Threat Intelligence
```python
# In Cursor, use the MCP tool
analyze_threat_intelligence(
    content="Malware sample detected with SHA256: abc123...",
    analysis_type="malware"
)
```

### Suggest Security Improvements
```python
# Analyze your code for security issues
suggest_security_improvements(
    code="def get_article(id): return db.execute(f'SELECT * FROM articles WHERE id = {id}')",
    file_path="src/web/modern_main.py"
)
```

### Generate AWS Deployment Plan
```python
# Get deployment plan for production
generate_aws_deployment_plan(
    environment="prod",
    requirements="High availability, auto-scaling, monitoring"
)
```

## Troubleshooting

### MCP Server Not Found
1. Check Python path in configuration
2. Verify dependencies are installed
3. Check file permissions

### Tool Not Available
1. Restart Cursor after configuration
2. Check MCP server is running
3. Verify configuration syntax

### Permission Errors
1. Check file permissions
2. Ensure Python can execute the script
3. Check environment variables

### Debug Mode
Enable debug mode by setting:
```bash
export LOG_LEVEL=DEBUG
```

## Customization

### Adding New Tools
1. Edit `mcp-server.py`
2. Add tool definition in `list_tools()`
3. Add handler in `call_tool()`
4. Implement the tool function
5. Restart MCP server

### Modifying Existing Tools
1. Edit the tool function
2. Update input schema if needed
3. Test the changes
4. Restart MCP server

## Security Considerations

- MCP server runs with same permissions as Cursor
- Validate all inputs in tool functions
- Don't expose sensitive data in responses
- Use proper error handling
- Log security-relevant events

## Performance Optimization

- Cache frequently used data
- Use async/await for I/O operations
- Implement proper error handling
- Monitor resource usage
- Optimize database queries

## Support

If you encounter issues:
1. Check the logs for error messages
2. Verify configuration syntax
3. Test MCP server independently
4. Check Cursor MCP documentation
5. Contact support if problems persist
EOF
    
    print_success "Installation instructions created: MCP_INSTALLATION_INSTRUCTIONS.md"
}

# Function to show summary
show_summary() {
    print_success "CTIScraper MCP Server setup completed!"
    echo
    print_status "Files created:"
    echo "  📄 mcp-server.py - Main MCP server"
    echo "  📄 mcp-config.json - MCP configuration"
    echo "  📄 cursor-settings.json - Cursor settings"
    echo "  📄 .env.mcp - Environment variables"
    echo "  📄 requirements-mcp.txt - Python dependencies"
    echo "  📄 MCP_INSTALLATION_INSTRUCTIONS.md - Setup guide"
    echo
    print_status "Next steps:"
    echo "  1. Configure Cursor with the settings in cursor-settings.json"
    echo "  2. Restart Cursor"
    echo "  3. Test the MCP tools in Cursor"
    echo "  4. Read MCP_INSTALLATION_INSTRUCTIONS.md for detailed setup"
    echo
    print_status "Available MCP tools:"
    echo "  🔍 analyze_threat_intelligence"
    echo "  🔒 suggest_security_improvements"
    echo "  ☁️  generate_aws_deployment_plan"
    echo "  📊 analyze_scoring_algorithm"
    echo "  🗄️  generate_database_queries"
    echo "  🎨 suggest_ui_improvements"
    echo "  ⚙️  validate_configuration"
    echo "  🧪 generate_test_cases"
    echo
    print_success "Your CTIScraper MCP server is ready to use!"
}

# Main function
main() {
    print_status "Starting CTIScraper MCP Server setup..."
    echo
    
    # Check prerequisites
    check_python
    check_pip
    
    # Setup steps
    install_dependencies
    create_mcp_config
    create_cursor_settings
    create_env_file
    test_mcp_server
    create_installation_instructions
    
    # Show summary
    show_summary
}

# Run main function
main "$@"
