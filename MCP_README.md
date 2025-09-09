# CTIScraper MCP Tool for Cursor

## 🎯 **Overview**

This custom MCP (Model Context Protocol) tool provides AI assistance specifically for the CTIScraper threat intelligence platform. It integrates with Cursor IDE to offer context-aware suggestions, security analysis, and development assistance tailored to your project.

## 🚀 **Quick Start**

### **1. Run Setup Script**
```bash
cd CTIScraper
chmod +x setup-mcp.sh
./setup-mcp.sh
```

### **2. Configure Cursor**
1. Open Cursor → Settings (Cmd+, on Mac)
2. Search for "MCP" or "Model Context Protocol"
3. Add the configuration from `cursor-settings.json`
4. Restart Cursor

### **3. Test MCP Tools**
1. Open a CTIScraper file
2. Command Palette (Cmd+Shift+P) → Search "MCP"
3. Select CTIScraper tools

## 🛠️ **Available Tools**

### **1. 🔍 Analyze Threat Intelligence**
```python
analyze_threat_intelligence(
    content="Malware sample detected with SHA256: abc123...",
    analysis_type="malware"  # ioc, ttp, malware, apt, general
)
```
**Features:**
- IOC detection and counting
- TTP identification
- Threat level assessment
- Confidence scoring
- Action item recommendations

### **2. 🔒 Suggest Security Improvements**
```python
suggest_security_improvements(
    code="def get_article(id): return db.execute(f'SELECT * FROM articles WHERE id = {id}')",
    file_path="src/web/modern_main.py"
)
```
**Features:**
- Security vulnerability detection
- Input validation suggestions
- Authentication/authorization recommendations
- Secure code examples
- Best practices guidance

### **3. ☁️ Generate AWS Deployment Plan**
```python
generate_aws_deployment_plan(
    environment="prod",  # dev, staging, prod
    requirements="High availability, auto-scaling, monitoring"
)
```
**Features:**
- Infrastructure component recommendations
- Security considerations
- Cost estimation
- Deployment steps
- Monitoring and alerting setup

### **4. 📊 Analyze Scoring Algorithm**
```python
analyze_scoring_algorithm(
    algorithm_type="threat_hunting",  # quality, threat_hunting, ioc, ttp
    current_implementation="def score_threat_hunting(content): return len(content) * 0.1"
)
```
**Features:**
- Algorithm performance analysis
- Improvement suggestions
- Alternative approaches
- Testing recommendations
- Performance metrics

### **5. 🗄️ Generate Database Queries**
```python
generate_database_queries(
    query_type="articles",  # articles, sources, analytics, reports
    filters={"source_id": 1, "date_range": "last_7_days"},
    aggregation="count"
)
```
**Features:**
- SQL query generation
- Filtered queries
- Aggregation queries
- Performance optimization
- Indexing recommendations

### **6. 🎨 Suggest UI Improvements**
```python
suggest_ui_improvements(
    page="dashboard",  # dashboard, articles, sources, settings
    current_html="<div class='dashboard'>...</div>"
)
```
**Features:**
- Accessibility improvements
- Performance optimizations
- UX enhancements
- Security considerations
- Code examples

### **7. ⚙️ Validate Configuration**
```python
validate_configuration(
    config_type="sources",  # sources, models, aws, docker
    config_content="sources:\n  - id: test\n    name: Test Source"
)
```
**Features:**
- Configuration syntax validation
- Issue identification
- Best practices recommendations
- Security validation
- Performance optimization

### **8. 🧪 Generate Test Cases**
```python
generate_test_cases(
    component="scraper",  # scraper, processor, scorer, api, ui
    existing_code="class ContentScraper: ..."
)
```
**Features:**
- Unit test generation
- Integration tests
- Performance tests
- Security tests
- Test data creation

## 🔧 **Installation Details**

### **Prerequisites**
- Python 3.8+
- pip3
- Cursor IDE

### **Dependencies**
```bash
pip install -r requirements-mcp.txt
```

### **Configuration Files**
- `mcp-server.py` - Main MCP server
- `mcp-config.json` - MCP configuration
- `cursor-settings.json` - Cursor integration
- `.env.mcp` - Environment variables

## 📋 **Usage Examples**

### **Threat Intelligence Analysis**
```python
# Analyze malware content
analyze_threat_intelligence(
    content="""
    APT29 (Cozy Bear) has been observed using new techniques:
    - C2: malware.example.com
    - Hash: a1b2c3d4e5f6...
    - TTPs: Persistence, Defense Evasion
    """,
    analysis_type="apt"
)
```

### **Security Code Review**
```python
# Review API endpoint security
suggest_security_improvements(
    code="""
    @app.post("/api/articles")
    async def create_article(article: ArticleCreate):
        return db.execute(f"INSERT INTO articles VALUES ('{article.title}')")
    """,
    file_path="src/web/modern_main.py"
)
```

### **AWS Production Deployment**
```python
# Generate production deployment plan
generate_aws_deployment_plan(
    environment="prod",
    requirements="High availability, auto-scaling, monitoring, WAF protection"
)
```

### **Scoring Algorithm Optimization**
```python
# Analyze threat hunting scoring
analyze_scoring_algorithm(
    algorithm_type="threat_hunting",
    current_implementation="""
    def score_threat_hunting_content(title, content):
        score = 0
        if 'malware' in content.lower():
            score += 20
        if 'ioc' in content.lower():
            score += 15
        return min(score, 100)
    """
)
```

### **Database Query Generation**
```python
# Generate analytics queries
generate_database_queries(
    query_type="analytics",
    filters={"date_range": "last_30_days", "source_tier": "premium"},
    aggregation="avg"
)
```

## 🎯 **Integration Benefits**

### **Context-Aware Assistance**
- Understands CTIScraper architecture
- Provides project-specific suggestions
- Maintains consistency with project standards

### **Security-Focused**
- Specialized threat intelligence analysis
- Security best practices for cybersecurity tools
- Compliance considerations

### **Development Efficiency**
- Automated code analysis
- Quick security reviews
- AWS deployment assistance
- Test case generation

### **Threat Intelligence Expertise**
- IOC extraction and analysis
- TTP identification
- Threat level assessment
- Action item recommendations

## 🔍 **Troubleshooting**

### **MCP Server Not Found**
```bash
# Check Python path
which python3

# Verify dependencies
pip3 list | grep mcp

# Test server manually
python3 mcp-server.py --test
```

### **Tool Not Available in Cursor**
1. Restart Cursor completely
2. Check configuration syntax in settings
3. Verify file paths are correct
4. Check Cursor MCP documentation

### **Permission Errors**
```bash
# Check file permissions
ls -la mcp-server.py

# Make executable if needed
chmod +x mcp-server.py
```

### **Debug Mode**
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python3 mcp-server.py
```

## 🚀 **Advanced Usage**

### **Custom Tool Development**
1. Edit `mcp-server.py`
2. Add tool definition in `list_tools()`
3. Add handler in `call_tool()`
4. Implement the tool function
5. Restart MCP server

### **Integration with CI/CD**
```bash
# Use MCP tools in CI/CD pipeline
python3 mcp-server.py --tool validate_configuration --config-type aws --config-content "$(cat terraform/main.tf)"
```

### **Batch Analysis**
```python
# Analyze multiple files
for file in src/**/*.py:
    suggest_security_improvements(
        code=read_file(file),
        file_path=file
    )
```

## 📊 **Performance Considerations**

- MCP server runs with same permissions as Cursor
- Tools are optimized for CTIScraper-specific patterns
- Caching for frequently accessed data
- Async operations for I/O-bound tasks

## 🔒 **Security Features**

- Input validation for all tool functions
- No sensitive data exposure in responses
- Proper error handling and logging
- Security-focused analysis capabilities

## 📈 **Future Enhancements**

- Machine learning model integration
- Real-time threat intelligence updates
- Advanced pattern recognition
- Integration with external threat feeds
- Automated security testing

## 🆘 **Support**

If you encounter issues:
1. Check `MCP_INSTALLATION_INSTRUCTIONS.md`
2. Verify configuration syntax
3. Test MCP server independently
4. Check Cursor MCP documentation
5. Review logs for error messages

## 🎉 **Success!**

Your CTIScraper MCP tool is now ready to provide AI-powered assistance for:
- Threat intelligence analysis
- Security code reviews
- AWS deployment planning
- Scoring algorithm optimization
- Database query generation
- UI/UX improvements
- Configuration validation
- Test case generation

Enjoy your enhanced development experience with CTIScraper! 🚀
