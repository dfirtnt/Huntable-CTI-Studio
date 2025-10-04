# SIGMA Rule Generation Feature

## Overview

The SIGMA Rule Generation feature automatically creates detection rules from threat intelligence articles using AI-powered analysis. This feature integrates with pySIGMA for validation and provides iterative fixing capabilities to ensure rule compliance.

## Features

### 🤖 AI-Powered Rule Generation
- **GPT-4 Integration**: Uses OpenAI's GPT-4 model for intelligent rule generation
- **Content Analysis**: Analyzes article content to extract relevant detection patterns
- **Context Awareness**: Understands threat techniques and attack patterns
- **Multiple Rule Generation**: Can generate multiple rules per article when appropriate

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
- Article must have a threat hunting score > 70
- OpenAI API key must be configured in environment variables
- pySIGMA library must be installed

### How to Use

1. **Navigate to Article**: Go to any article with threat hunting score > 70
2. **Click Generate Button**: Click "Generate SIGMA Rules" button
3. **AI Processing**: GPT-4 analyzes the article content
4. **Rule Generation**: AI generates appropriate SIGMA detection rules
5. **Validation**: pySIGMA validates the generated rules
6. **Iterative Fixing**: If validation fails, rules are retried with error feedback
7. **Storage**: Valid rules are stored with complete metadata
8. **View Results**: Click to view the generated rules and conversation log showing the LLM ↔ pySigma interaction

### API Endpoint

```http
POST /api/articles/{article_id}/generate-sigma-rules
Content-Type: application/json

{
  "include_content": true,
  "max_rules": 3
}
```

**Response:**
```json
{
  "success": true,
  "rules": [
    {
      "title": "Detection Rule Title",
      "description": "Rule description",
      "logsource": {
        "product": "windows",
        "service": "sysmon"
      },
      "detection": {
        "selection": {
          "CommandLine": "malicious_command"
        },
        "condition": "selection"
      },
      "level": "high"
    }
  ],
  "metadata": {
    "generated_at": "2025-01-27T10:30:00Z",
    "model_used": "gpt-4",
    "validation_passed": true,
    "attempts_made": 1,
    "validation_results": [...]
  }
}
```

## Configuration

### Environment Variables

```bash
# OpenAI Configuration
CHATGPT_API_KEY=your_openai_api_key_here
OPENAI_API_URL=https://api.openai.com/v1

# Optional: Custom model selection
SIGMA_GENERATION_MODEL=gpt-4
```

### Source Configuration

Articles are eligible for SIGMA rule generation if:
- Threat hunting score > 70
- Content length > 2000 characters
- Article is classified as "chosen"
- Content contains threat intelligence indicators

## Technical Details

### Generation Process

1. **Content Analysis**: GPT-4 analyzes article title and content
2. **Pattern Extraction**: Identifies relevant attack patterns and techniques
3. **Rule Creation**: Generates appropriate SIGMA detection rules
4. **Format Compliance**: Ensures proper YAML structure and required fields
5. **Validation**: pySIGMA validates the generated rules
6. **Error Handling**: Failed rules trigger retry with error feedback
7. **Storage**: Valid rules stored in article metadata

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
- Error feedback provided to GPT-4
- Progressive improvement with each attempt
- Graceful failure after max attempts

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

**OpenAI API Errors:**
- Check API key configuration
- Verify API quota and billing
- Monitor rate limiting

**pySIGMA Validation Failures:**
- Ensure pySIGMA is properly installed
- Check rule format compliance
- Review validation error messages

**Generation Failures:**
- Verify article content quality
- Check threat hunting score threshold
- Review OpenAI model availability

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
- Article content sent to OpenAI for analysis
- No sensitive data stored in OpenAI logs
- Rules stored locally in database

### Input Validation
- Article ID validation
- Content length checks
- Threat score thresholds
- Rate limiting on generation requests

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

**Note**: This feature requires OpenAI API access and pySIGMA validation. Ensure proper configuration and monitoring for production use.
