# CTIScraper MCP Server Configuration

## MCP Server Configuration File

```json
{
  "mcpServers": {
    "cti-scraper": {
      "command": "python",
      "args": ["/Users/starlord/CTIScraper/mcp-server.py"],
      "env": {
        "PYTHONPATH": "/Users/starlord/CTIScraper"
      }
    },
    "lmstudio": {
      "command": "python",
      "args": ["/Users/starlord/CTIScraper/lmstudio-mcp-server.py"],
      "env": {
        "PYTHONPATH": "/Users/starlord/CTIScraper",
        "LMSTUDIO_BASE_URL": "http://localhost:1234",
        "LMSTUDIO_API_KEY": ""
      }
    }
  }
}
```

## Cursor Settings Integration

Add this to your Cursor settings.json:

```json
{
  "mcp.servers": {
    "cti-scraper": {
      "command": "python",
      "args": ["/Users/starlord/CTIScraper/mcp-server.py"],
      "env": {
        "PYTHONPATH": "/Users/starlord/CTIScraper"
      }
    },
    "lmstudio": {
      "command": "python",
      "args": ["/Users/starlord/CTIScraper/lmstudio-mcp-server.py"],
      "env": {
        "PYTHONPATH": "/Users/starlord/CTIScraper",
        "LMSTUDIO_BASE_URL": "http://localhost:1234",
        "LMSTUDIO_API_KEY": ""
      }
    }
  }
}
```

## Environment Variables

Create a `.env` file for the MCP server:

```bash
# CTIScraper MCP Server Environment Variables
PROJECT_ROOT=/path/to/CTIScraper
LOG_LEVEL=INFO
ENABLE_DEBUG=true
```

## Dependencies

Install required Python packages:

```bash
pip install mcp
pip install asyncio
pip install pathlib
pip install logging
```

## Usage Examples

### 1. Analyze Threat Intelligence
```python
# In Cursor, use the MCP tool
analyze_threat_intelligence(
    content="Malware sample detected with SHA256: abc123...",
    analysis_type="malware"
)
```

### 2. Suggest Security Improvements
```python
# Analyze your code for security issues
suggest_security_improvements(
    code="def get_article(id): return db.execute(f'SELECT * FROM articles WHERE id = {id}')",
    file_path="src/web/modern_main.py"
)
```

### 3. Generate AWS Deployment Plan
```python
# Get deployment plan for production
generate_aws_deployment_plan(
    environment="prod",
    requirements="High availability, auto-scaling, monitoring"
)
```

### 4. Analyze Scoring Algorithm
```python
# Analyze your scoring algorithm
analyze_scoring_algorithm(
    algorithm_type="threat_hunting",
    current_implementation="def score_threat_hunting(content): return len(content) * 0.1"
)
```

### 5. Generate Database Queries
```python
# Generate SQL queries for your database
generate_database_queries(
    query_type="articles",
    filters={"source_id": 1, "date_range": "last_7_days"},
    aggregation="count"
)
```

### 6. Suggest UI Improvements
```python
# Get UI improvement suggestions
suggest_ui_improvements(
    page="dashboard",
    current_html="<div class='dashboard'>...</div>"
)
```

### 7. Validate Configuration
```python
# Validate your configuration files
validate_configuration(
    config_type="sources",
    config_content="sources:\n  - id: test\n    name: Test Source"
)
```

### 8. Generate Test Cases
```python
# Generate test cases for your components
generate_test_cases(
    component="scraper",
    existing_code="class ContentScraper: ..."
)
```

## Setup Instructions

### 1. Install Dependencies
```bash
cd CTIScraper
pip install -r requirements-mcp.txt
```

### 2. Configure Cursor
1. Open Cursor settings
2. Add MCP server configuration
3. Restart Cursor

### 3. Test MCP Server
```bash
python mcp-server.py
```

### 4. Use in Cursor
1. Open a CTIScraper file
2. Use Command Palette (Cmd+Shift+P)
3. Search for "MCP" tools
4. Select CTIScraper tools

## Troubleshooting

### Common Issues
1. **MCP server not found**: Check Python path and dependencies
2. **Tool not available**: Restart Cursor after configuration
3. **Permission errors**: Check file permissions and paths

### Debug Mode
Enable debug mode in the MCP server:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Customization

### Adding New Tools
1. Add tool definition in `list_tools()`
2. Add handler in `call_tool()`
3. Implement the tool function
4. Restart MCP server

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

## Integration with CTIScraper

The MCP server integrates with CTIScraper by:
- Reading project files and configuration
- Analyzing code patterns and security
- Providing context-aware suggestions
- Generating project-specific solutions
- Maintaining consistency with project standards
