# LMStudio MCP Server Configuration

## Overview
This configuration adds LMStudio MCP server integration to your Cursor IDE, enabling local LLM inference capabilities.

## LMStudio MCP Server Configuration

### 1. LMStudio MCP Server File
```json
{
  "mcpServers": {
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

### 2. Cursor Settings Integration
Add this to your Cursor settings.json:

```json
{
  "mcp.servers": {
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

## Prerequisites

### 1. Install LMStudio
- Download from: https://lmstudio.ai/download
- Install and launch LMStudio
- Load a model (e.g., Llama 3.1, CodeLlama, etc.)

### 2. Enable LMStudio API Server
- In LMStudio, go to "Local Server" tab
- Click "Start Server" 
- Note the port (default: 1234)
- Ensure "Enable API" is checked

### 3. Install Python Dependencies
```bash
pip install requests mcp
```

## Available Tools

### 1. 🗣️ Chat with LMStudio
```python
lmstudio_chat(
    message="Explain how to implement authentication in FastAPI",
    model="llama-3.1-8b-instruct",  # Optional
    temperature=0.7,               # Optional
    max_tokens=1000               # Optional
)
```

### 2. ✏️ Complete Text
```python
lmstudio_complete(
    prompt="def calculate_fibonacci(n):",
    model="codellama-7b-instruct",  # Optional
    temperature=0.7,                # Optional
    max_tokens=500                  # Optional
)
```

### 3. 🔍 Analyze Code
```python
lmstudio_analyze_code(
    code="def get_user(id): return db.execute(f'SELECT * FROM users WHERE id = {id}')",
    language="python",
    analysis_type="security"  # security, performance, style, bugs, documentation
)
```

### 4. 🧪 Generate Tests
```python
lmstudio_generate_tests(
    code="def add(a, b): return a + b",
    test_framework="pytest",  # pytest, unittest, jest, mocha
    test_type="unit"          # unit, integration, performance, security
)
```

### 5. 📖 Explain Code
```python
lmstudio_explain_code(
    code="async def process_articles(): ...",
    detail_level="detailed"  # brief, detailed, comprehensive
)
```

### 6. 🔧 Refactor Code
```python
lmstudio_refactor_code(
    code="def old_function(): ...",
    refactor_type="optimize",  # optimize, simplify, modernize, clean, restructure
    language="python"
)
```

### 7. 📚 Generate Documentation
```python
lmstudio_generate_docs(
    code="def calculate_score(content): ...",
    doc_type="docstring",  # docstring, readme, api, tutorial, comments
    style="google"         # google, numpy, sphinx, markdown
)
```

### 8. 📋 Check Models
```python
lmstudio_check_models()
```

## Configuration Options

### Environment Variables
Create a `.env.lmstudio` file:
```bash
# LMStudio Configuration
LMSTUDIO_BASE_URL=http://localhost:1234
LMSTUDIO_API_KEY=your_api_key_here  # Optional
LOG_LEVEL=INFO
```

### Model Configuration
- Default models are auto-detected from LMStudio
- Specify model names in tool calls for specific models
- Popular models: `llama-3.1-8b-instruct`, `codellama-7b-instruct`, `mistral-7b-instruct`

## Usage Examples

### Code Analysis
```python
# Analyze security issues
lmstudio_analyze_code(
    code="""
    @app.post("/api/users")
    async def create_user(user_data: dict):
        return db.execute(f"INSERT INTO users VALUES ('{user_data['name']}')")
    """,
    analysis_type="security"
)
```

### Test Generation
```python
# Generate comprehensive tests
lmstudio_generate_tests(
    code="""
    class ArticleProcessor:
        def __init__(self, db):
            self.db = db
        
        def process_article(self, article_id):
            article = self.db.get_article(article_id)
            return self.score_content(article.content)
    """,
    test_framework="pytest",
    test_type="unit"
)
```

### Documentation Generation
```python
# Generate API documentation
lmstudio_generate_docs(
    code="""
    def calculate_threat_score(content: str, keywords: List[str]) -> float:
        score = 0
        for keyword in keywords:
            if keyword.lower() in content.lower():
                score += 1
        return min(score / len(keywords), 1.0)
    """,
    doc_type="docstring",
    style="google"
)
```

## Troubleshooting

### LMStudio Not Running
```bash
# Check if LMStudio is running
curl http://localhost:1234/v1/models

# Start LMStudio server
# 1. Open LMStudio
# 2. Go to "Local Server" tab
# 3. Click "Start Server"
```

### Connection Issues
```bash
# Test connection
python -c "
import requests
try:
    response = requests.get('http://localhost:1234/v1/models')
    print('LMStudio is running:', response.status_code == 200)
except:
    print('LMStudio is not accessible')
"
```

### Model Loading
- Ensure at least one model is loaded in LMStudio
- Check model compatibility with your hardware
- Use `lmstudio_check_models()` to verify available models

### Performance Tips
- Use smaller models for faster responses
- Adjust temperature for creativity vs consistency
- Limit max_tokens for shorter responses
- Use specific models for code-related tasks

## Integration Benefits

### Local Processing
- No data sent to external services
- Complete privacy and security
- No API rate limits
- Offline capability

### CTIScraper Integration
- Analyze threat intelligence content locally
- Generate security-focused code reviews
- Create documentation for threat hunting tools
- Generate test cases for security components

### Development Efficiency
- Instant code analysis and suggestions
- Local LLM for sensitive code review
- Offline documentation generation
- Custom model fine-tuning support

## Security Considerations

- LMStudio runs locally - no data leaves your machine
- API key is optional for local use
- All processing happens on your hardware
- No external service dependencies

## Performance Optimization

- Use GPU acceleration if available
- Load models in memory for faster inference
- Adjust model size based on hardware capabilities
- Use appropriate temperature settings for task type

## Next Steps

1. **Install LMStudio** and load a model
2. **Start the LMStudio server** (port 1234)
3. **Add MCP configuration** to Cursor settings
4. **Test the integration** with `lmstudio_check_models()`
5. **Use tools** for code analysis and generation

Your LMStudio MCP server is now ready to provide local LLM capabilities in Cursor IDE! 🚀
