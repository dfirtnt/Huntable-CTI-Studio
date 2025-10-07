# LMStudio MCP Integration for CTIScraper

## 🎯 Overview

This integration adds LMStudio MCP server capabilities to your CTIScraper project, enabling local LLM inference directly within Cursor IDE. Perfect for threat intelligence analysis, code review, and documentation generation while maintaining complete privacy.

## 🚀 Quick Setup

### 1. Run Setup Script
```bash
cd /Users/starlord/CTIScraper
./setup-lmstudio-mcp.sh
```

### 2. Install LMStudio
- Download from: https://lmstudio.ai/download
- Install and launch LMStudio
- Load a model (recommended: Llama 3.1 8B or CodeLlama 7B)

### 3. Start LMStudio Server
- Open LMStudio → "Local Server" tab
- Click "Start Server" (default port: 1234)
- Ensure "Enable API" is checked

### 4. Configure Cursor
- Open Cursor → Settings (Cmd+,)
- Search "MCP" → Add configuration from `cursor-settings-lmstudio.json`
- Restart Cursor

### 5. Test Integration
```python
# In Cursor, test the connection
lmstudio_check_models()
```

## 🛠️ Available Tools

### Core LMStudio Tools

| Tool | Description | Example |
|------|-------------|---------|
| `lmstudio_chat` | Chat with local model | `lmstudio_chat(message="Explain SQL injection")` |
| `lmstudio_complete` | Complete code/text | `lmstudio_complete(prompt="def authenticate_user(")` |
| `lmstudio_check_models` | List available models | `lmstudio_check_models()` |

### Code Analysis Tools

| Tool | Description | Example |
|------|-------------|---------|
| `lmstudio_analyze_code` | Security/performance analysis | `lmstudio_analyze_code(code="...", analysis_type="security")` |
| `lmstudio_explain_code` | Code explanation | `lmstudio_explain_code(code="...", detail_level="detailed")` |
| `lmstudio_refactor_code` | Code refactoring | `lmstudio_refactor_code(code="...", refactor_type="optimize")` |

### Development Tools

| Tool | Description | Example |
|------|-------------|---------|
| `lmstudio_generate_tests` | Generate test cases | `lmstudio_generate_tests(code="...", test_framework="pytest")` |
| `lmstudio_generate_docs` | Generate documentation | `lmstudio_generate_docs(code="...", doc_type="docstring")` |

## 🎯 CTIScraper-Specific Use Cases

### Threat Intelligence Analysis
```python
# Analyze threat intelligence content
lmstudio_chat(
    message="""
    Analyze this threat intelligence:
    
    APT29 (Cozy Bear) has been observed using new techniques:
    - C2: malware.example.com
    - Hash: a1b2c3d4e5f6...
    - TTPs: Persistence, Defense Evasion
    
    Provide actionable recommendations.
    """,
    temperature=0.3
)
```

### Security Code Review
```python
# Review API endpoint security
lmstudio_analyze_code(
    code="""
    @app.post("/api/articles")
    async def create_article(article: ArticleCreate):
        return db.execute(f"INSERT INTO articles VALUES ('{article.title}')")
    """,
    analysis_type="security"
)
```

### Test Generation for Security Components
```python
# Generate security tests
lmstudio_generate_tests(
    code="""
    class ThreatScorer:
        def score_content(self, content: str) -> float:
            # Scoring logic here
            pass
    """,
    test_framework="pytest",
    test_type="security"
)
```

### Documentation for Threat Hunting Tools
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
    doc_type="api",
    style="google"
)
```

## ⚙️ Configuration

### Environment Variables
```bash
# .env.lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234
LMSTUDIO_API_KEY=  # Optional for local use
LOG_LEVEL=INFO
```

### Model Configuration
- **Default**: Auto-detected from LMStudio
- **Recommended Models**:
  - `llama-3.1-8b-instruct` - General purpose
  - `codellama-7b-instruct` - Code-focused
  - `mistral-7b-instruct` - Balanced performance

### Cursor Settings
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

## 🔧 Advanced Usage

### Custom Prompts for Threat Intelligence
```python
# Create specialized threat analysis prompts
threat_prompt = """
As a threat intelligence analyst, analyze this content:

{content}

Provide:
1. Threat level assessment (Low/Medium/High/Critical)
2. IOCs identified
3. TTPs observed
4. Recommended actions
5. Confidence level
"""

lmstudio_chat(
    message=threat_prompt.format(content=threat_intel_content),
    temperature=0.2  # Low temperature for consistent analysis
)
```

### Batch Code Analysis
```python
# Analyze multiple files
import os
from pathlib import Path

for py_file in Path("src").rglob("*.py"):
    with open(py_file, 'r') as f:
        code = f.read()
    
    lmstudio_analyze_code(
        code=code,
        analysis_type="security"
    )
```

### Performance Optimization
```python
# Use smaller models for faster responses
lmstudio_chat(
    message="Quick security check",
    model="llama-3.1-8b-instruct",  # Smaller model
    temperature=0.1,                # Low creativity
    max_tokens=200                  # Short response
)
```

## 🚨 Troubleshooting

### LMStudio Not Running
```bash
# Check if server is running
curl http://localhost:1234/v1/models

# Expected response: {"data": [{"id": "model-name", ...}]}
```

### Connection Issues
```bash
# Test Python connection
python3 -c "
import requests
try:
    response = requests.get('http://localhost:1234/v1/models')
    print('✅ LMStudio accessible:', response.status_code == 200)
except Exception as e:
    print('❌ LMStudio not accessible:', e)
"
```

### Model Loading Issues
- Ensure at least one model is loaded in LMStudio
- Check model compatibility with your hardware
- Use `lmstudio_check_models()` to verify available models
- Try different model sizes based on your RAM/VRAM

### Performance Issues
- Use GPU acceleration if available
- Load models in memory for faster inference
- Adjust model size based on hardware capabilities
- Use appropriate temperature settings (0.1-0.3 for analysis, 0.7+ for creative tasks)

## 🔒 Security Benefits

### Complete Privacy
- **No external API calls** - All processing happens locally
- **No data transmission** - Your code and data never leave your machine
- **No rate limits** - Unlimited usage without API costs
- **Offline capability** - Works without internet connection

### Threat Intelligence Focus
- **Sensitive data protection** - Analyze threat intelligence without external exposure
- **Compliance friendly** - No third-party data processing
- **Audit trail** - All analysis happens on your infrastructure
- **Custom models** - Fine-tune models for your specific threat landscape

## 📊 Performance Comparison

| Aspect | LMStudio (Local) | External APIs |
|--------|------------------|---------------|
| **Privacy** | ✅ Complete | ❌ Data shared |
| **Cost** | ✅ One-time | ❌ Per-request |
| **Speed** | ⚠️ Hardware dependent | ✅ Fast |
| **Offline** | ✅ Yes | ❌ No |
| **Customization** | ✅ Full control | ❌ Limited |
| **Rate Limits** | ✅ None | ❌ Yes |

## 🎯 Integration with CTIScraper Workflow

### 1. Threat Intelligence Processing
```python
# Analyze incoming threat intelligence
for article in new_articles:
    analysis = lmstudio_chat(
        message=f"Analyze this threat intelligence: {article.content}",
        temperature=0.2
    )
    # Process analysis results
```

### 2. Code Security Review
```python
# Review security-critical components
lmstudio_analyze_code(
    code=scraper_code,
    analysis_type="security"
)
```

### 3. Documentation Generation
```python
# Generate documentation for threat hunting tools
lmstudio_generate_docs(
    code=threat_scoring_function,
    doc_type="api"
)
```

### 4. Test Case Generation
```python
# Generate tests for security components
lmstudio_generate_tests(
    code=authentication_module,
    test_type="security"
)
```

## 🚀 Next Steps

1. **Install LMStudio** and load a model
2. **Run setup script**: `./setup-lmstudio-mcp.sh`
3. **Configure Cursor** with provided settings
4. **Test integration** with `lmstudio_check_models()`
5. **Start using tools** for threat intelligence analysis
6. **Customize prompts** for your specific use cases
7. **Fine-tune models** for better threat intelligence analysis

## 📚 Additional Resources

- **LMStudio Documentation**: https://lmstudio.ai/docs
- **MCP Protocol**: https://modelcontextprotocol.io
- **CTIScraper MCP**: `MCP_README.md`
- **Configuration Guide**: `LMSTUDIO_MCP_CONFIG.md`

Your LMStudio MCP server is now ready to provide local LLM capabilities for threat intelligence analysis! 🎉
