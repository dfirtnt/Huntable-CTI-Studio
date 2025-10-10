# SIGMA Rule Generation Feature

## Overview

The SIGMA Rule Generation feature automatically creates detection rules from threat intelligence articles using AI-powered analysis. This feature integrates with pySIGMA for validation and provides iterative fixing capabilities to ensure rule compliance.

## Features

### 🤖 AI-Powered Rule Generation
- **Multiple AI Models**: Supports ChatGPT (OpenAI), Claude (Anthropic), and Ollama (local LLM)
- **Content Analysis**: Analyzes article content to extract relevant detection patterns
- **Context Awareness**: Understands threat techniques and attack patterns
- **Multiple Rule Generation**: Can generate multiple rules per article when appropriate
- **Content Filtering**: ML-based content optimization to reduce token usage and costs

### ✅ pySIGMA Validation
- **Automatic Validation**: All generated rules are validated using pySIGMA
- **Compliance Checking**: Ensures rules meet SIGMA format requirements
- **Error Detection**: Identifies syntax errors, missing fields, and format issues
- **Warning Detection**: Flags potential issues and best practice violations

### 🔄 Iterative Rule Fixing
- **Automatic Retry**: Failed rules are automatically retried with error feedback
- **Up to 3 Attempts**: Maximum of 3 generation attempts per rule set
- **Error Feedback**: GPT-4 receives detailed validation errors for improvement
- **Progressive Improvement**: Each attempt incorporates previous validation results

### 📊 Metadata Storage
- **Complete Audit Trail**: Stores all generation attempts and validation results
- **Attempt Tracking**: Records number of attempts made for each rule set
- **Validation Results**: Stores detailed validation errors and warnings
- **Generation Timestamps**: Tracks when rules were generated and validated

### 🔄 Conversation Log Display
- **Interactive Visualization**: Shows the full back-and-forth conversation between LLM and pySigma validator
- **Attempt-by-Attempt View**: Each retry attempt is displayed in a separate card with clear visual indicators
- **Collapsible Sections**: Long prompts and responses can be collapsed/expanded for better readability
- **Color-Coded Feedback**: Visual indicators for valid (green) and invalid (red) validation results
- **Detailed Error Messages**: Shows specific validation errors and warnings from pySigma
- **Progressive Learning**: See how the LLM improves its output based on validation feedback

## Usage

### Prerequisites
- Article must be classified as "chosen" (required)
- Threat hunting score < 65 shows warning but allows proceeding
- AI model API key must be configured (varies by model)
- pySIGMA library must be installed

### How to Use

1. **Navigate to Article**: Go to any article classified as "chosen"
2. **Click Generate Button**: Click "Generate SIGMA Rules" button
3. **AI Processing**: Selected AI model analyzes the article content
4. **Rule Generation**: AI generates appropriate SIGMA detection rules
5. **Validation**: pySIGMA validates the generated rules
6. **Iterative Fixing**: If validation fails, rules are retried with error feedback (up to 3 attempts)
7. **Storage**: Valid rules are stored with complete metadata
8. **View Results**: Click to view the generated rules and conversation log showing the LLM ↔ pySigma interaction

### API Endpoint

```http
POST /api/articles/{article_id}/generate-sigma
Content-Type: application/json

{
  "force_regenerate": false,
  "include_content": true,
  "ai_model": "chatgpt",
  "api_key": "your_api_key_here",
  "author_name": "CTIScraper User",
  "temperature": 0.2,
  "optimization_options": {
    "useFiltering": true,
    "minConfidence": 0.7
  }
}
```

**Response:**
```json
{
  "success": true,
  "article_id": 633,
  "sigma_rules": "Generated SIGMA rule content...",
  "generated_at": "2025-10-10T15:28:28.134389",
  "content_type": "full content",
  "model_used": "ollama",
  "model_name": "llama3.2:1b",
  "validation_results": [
    {
      "rule_index": 1,
      "is_valid": false,
      "errors": ["Invalid YAML syntax"],
      "warnings": [],
      "rule_info": {}
    }
  ],
  "conversation": [...],
  "validation_passed": false,
  "attempts_made": 3,
  "temperature": 0.0,
  "optimization": {
    "enabled": true,
    "cost_savings": 0.014549999999999999,
    "tokens_saved": 2910,
    "chunks_removed": 15,
    "min_confidence": 0.7
  },
  "message": "⚠️ SIGMA rules generated but failed pySIGMA validation after 3 attempts. Please review the validation errors and consider manual correction."
}
```

## Configuration

### AI Model Support

The system supports multiple AI models:

**ChatGPT (OpenAI)**
- Model: GPT-4 or GPT-3.5-turbo
- API Key: Required in request body
- Best for: High-quality rule generation

**Claude (Anthropic)**
- Model: claude-3-haiku-20240307
- API Key: Required in request body
- Best for: Complex analysis and reasoning

**Ollama (Local LLM)**
- Model: llama3.2:1b (configurable)
- API Key: Not required
- Best for: Local processing and privacy

### Request Parameters

```json
{
  "force_regenerate": false,        // Skip cache and regenerate
  "include_content": true,          // Use full content vs metadata only
  "ai_model": "chatgpt",           // chatgpt, anthropic, or ollama
  "api_key": "your_key_here",      // Required for ChatGPT/Claude
  "author_name": "Your Name",       // Rule author name
  "temperature": 0.2,              // LLM creativity (0.0-1.0)
  "optimization_options": {         // Content filtering options
    "useFiltering": true,
    "minConfidence": 0.7
  }
}
```

### Prerequisites

Articles are eligible for SIGMA rule generation if:
- Article is classified as "chosen" (required)
- Threat hunting score < 65 shows warning but allows proceeding
- Content contains threat intelligence indicators

## Technical Details

### Generation Process

1. **Content Analysis**: Selected AI model analyzes article title and content
2. **Content Filtering**: ML-based optimization reduces token usage and costs
3. **Pattern Extraction**: Identifies relevant attack patterns and techniques
4. **Rule Creation**: Generates appropriate SIGMA detection rules
5. **Format Compliance**: Ensures proper YAML structure and required fields
6. **Validation**: pySIGMA validates the generated rules
7. **Iterative Fixing**: Failed rules trigger retry with error feedback (up to 3 attempts)
8. **Storage**: Rules stored in article metadata with complete audit trail

### Validation Process

```python
# Example validation result
{
  "rule_index": 1,
  "is_valid": True,
  "errors": [],
  "warnings": ["Consider adding more specific conditions"],
  "rule_info": {
    "title": "Generated rule title",
    "level": "high",
    "logsource": "windows/sysmon"
  }
}
```

### Error Handling

**Common Validation Errors:**
- Missing required fields (title, logsource, detection)
- Invalid YAML syntax
- Incorrect field types
- Missing condition statements
- Invalid logsource configurations

**Retry Logic:**
- Maximum 3 attempts per rule set
- Error feedback provided to selected AI model
- Progressive improvement with each attempt
- Graceful failure after max attempts
- Complete conversation log captured for debugging

### Content Filtering System

The system includes ML-based content filtering to optimize costs and performance:

**Features:**
- Reduces token usage by filtering irrelevant content
- Maintains high-confidence content for rule generation
- Configurable confidence thresholds
- Cost savings tracking and reporting

**Configuration:**
```json
{
  "optimization_options": {
    "useFiltering": true,      // Enable content filtering
    "minConfidence": 0.7       // Minimum confidence threshold
  }
}
```

## Examples

### Successful Generation

**Input Article**: "APT29 Uses PowerShell for Lateral Movement"
**Generated Rule**:
```yaml
title: APT29 PowerShell Lateral Movement
description: Detects PowerShell commands used for lateral movement by APT29
logsource:
  product: windows
  service: powershell
detection:
  selection:
    CommandLine: 
      - '*Invoke-Command*'
      - '*Enter-PSSession*'
      - '*New-PSSession*'
  condition: selection
level: high
```

### Failed Generation with Retry

**First Attempt**: Missing logsource field
**Validation Error**: "Missing required field: logsource"
**Second Attempt**: Added logsource, but invalid syntax
**Validation Error**: "Invalid YAML syntax in logsource section"
**Third Attempt**: Fixed syntax and generated valid rule

## Monitoring and Metrics

### Health Checks
- OpenAI API connectivity
- pySIGMA validation status
- Generation success rates
- Average attempts per rule set

### Metrics Tracked
- Rules generated per day
- Validation success rate
- Average attempts per generation
- Most common validation errors
- Generation processing time

## Troubleshooting

### Common Issues

**API Key Errors:**
- Check API key configuration in request body
- Verify API quota and billing for ChatGPT/Claude
- Monitor rate limiting

**pySIGMA Validation Failures:**
- Ensure pySIGMA is properly installed
- Check rule format compliance
- Review validation error messages
- Examine conversation log for debugging

**Generation Failures:**
- Verify article is classified as "chosen"
- Check threat hunting score (warning below 65)
- Review AI model availability and configuration
- Check content filtering settings

### Debug Information

Enable debug logging:
```bash
LOG_LEVEL=DEBUG
```

Check generation logs:
```bash
docker-compose logs -f web | grep "SIGMA"
```

## Security Considerations

### Data Privacy
- Article content sent to selected AI model for analysis
- No sensitive data stored in AI provider logs
- Rules stored locally in database
- Ollama option provides local processing

### Input Validation
- Article ID validation
- Classification requirement ("chosen")
- Threat score thresholds (warning below 65)
- Rate limiting on generation requests
- API key validation for external models

### Output Validation
- pySIGMA validation ensures rule safety
- No arbitrary code execution
- Structured rule format only

## Future Enhancements

### Planned Features
- **Custom Rule Templates**: User-defined rule templates
- **Rule Optimization**: Automatic rule performance optimization
- **Bulk Generation**: Generate rules for multiple articles
- **Rule Testing**: Integration with SIEM testing frameworks
- **Rule Sharing**: Export and import rule collections

### Integration Opportunities
- **SIEM Integration**: Direct export to SIEM platforms
- **Rule Repositories**: Integration with SIGMA rule repositories
- **Threat Intelligence**: Enhanced TTP extraction and mapping
- **Machine Learning**: ML-based rule quality assessment

## Support

For issues and questions:
- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: Check this guide and API documentation
- **Community**: Join the CTI Scraper community discussions

---

**Note**: This feature supports multiple AI models (ChatGPT, Claude, Ollama) and requires pySIGMA validation. Ensure proper configuration and monitoring for production use.
