# AI Features Documentation

This document describes the AI-powered features available in CTI Scraper, including content summarization, SIGMA rule generation, and IOC extraction.

## Overview

CTI Scraper integrates with OpenAI's GPT-4 model to provide intelligent analysis of threat intelligence articles. All AI features include caching mechanisms to reduce API costs and improve response times.

## Available AI Features

### 1. Content Summarization
- **Purpose**: Generate comprehensive summaries of threat intelligence articles
- **Use Case**: Quick understanding of article content and key points
- **Access**: Available on article detail pages via "Generate Summary" button

### 2. SIGMA Rule Generation
- **Purpose**: Create detection rules for SIEM systems based on threat intelligence
- **Use Case**: Operationalizing threat intelligence into actionable detection rules
- **Access**: Available on article detail pages via "Generate SIGMA Rules" button
- **Requirement**: Article must be marked as "chosen" in training category

### 3. IOC Extraction
- **Purpose**: Extract Indicators of Compromise from threat intelligence content
- **Use Case**: Identifying specific threat indicators for threat hunting and detection
- **Access**: Available on article detail pages via "Extract IOCs" button

## Feature Comparison

| **Feature** | **Summary** | **SIGMA** | **IOCs** |
|-------------|-------------|-----------|----------|
| **Storage Key** | `chatgpt_summary` | `sigma_rules` | `extracted_iocs` |
| **Caching** | ✅ | ✅ | ✅ |
| **Force Regenerate** | ✅ | ✅ | ✅ |
| **Database Update** | ✅ | ✅ | ✅ |
| **Content Limit** | 8,000 chars | 8,000 chars | 8,000 chars |
| **Model** | gpt-4 | gpt-4 | gpt-4 |
| **Max Tokens** | 2048 | 2048 | 2048 |
| **Temperature** | 0.3 | 0.2 | 0.1 |
| **Timeout** | 120s | 120s | 120s |
| **Metadata Fields** | `summary`, `summarized_at`, `content_type`, `model_used`, `model_name` | `rules`, `generated_at`, `content_type`, `model_used`, `model_name` | `iocs`, `extracted_at`, `content_type`, `model_used`, `model_name` |

## API Endpoints

### Content Summarization
```
POST /api/articles/{article_id}/chatgpt-summary
```

**Request Body:**
```json
{
  "include_content": true,
  "api_key": "your-openai-api-key",
  "force_regenerate": false
}
```

### SIGMA Rule Generation
```
POST /api/articles/{article_id}/generate-sigma
```

**Request Body:**
```json
{
  "include_content": true,
  "api_key": "your-openai-api-key",
  "force_regenerate": false
}
```

### IOC Extraction
```
POST /api/articles/{article_id}/extract-iocs
```

**Request Body:**
```json
{
  "include_content": true,
  "api_key": "your-openai-api-key",
  "force_regenerate": false
}
```

## Configuration

### Environment Variables
- `CHATGPT_API_URL`: OpenAI API endpoint (default: `https://api.openai.com/v1/chat/completions`)
- `CHATGPT_CONTENT_LIMIT`: Maximum content length for AI processing (default: `8000`)

### Settings Page Configuration
- **OpenAI API Key**: Required for all AI features
- **AI Model Selection**: Choose between ChatGPT and Ollama (local)

## Caching Mechanism

All AI features implement intelligent caching:

1. **Cache Check**: Before making API calls, check if results already exist
2. **Cache Storage**: Store results in article metadata with timestamps
3. **Force Regenerate**: Option to bypass cache and generate new results
4. **Cache Invalidation**: Manual regeneration available via UI

### Cache Structure
```json
{
  "chatgpt_summary": {
    "summary": "Generated summary text...",
    "summarized_at": "2024-01-01T12:00:00",
    "content_type": "full content",
    "model_used": "chatgpt",
    "model_name": "gpt-4"
  },
  "sigma_rules": {
    "rules": "Generated SIGMA rules...",
    "generated_at": "2024-01-01T12:00:00",
    "content_type": "full content",
    "model_used": "chatgpt",
    "model_name": "gpt-4"
  },
  "extracted_iocs": {
    "iocs": "{\"ip\": [], \"domain\": [], ...}",
    "extracted_at": "2024-01-01T12:00:00",
    "content_type": "full content",
    "model_used": "chatgpt",
    "model_name": "gpt-4"
  }
}
```

## Error Handling

### Common Error Scenarios
1. **Missing API Key**: User must configure OpenAI API key in Settings
2. **Invalid API Key**: Authentication failure with OpenAI
3. **Rate Limiting**: OpenAI API rate limits exceeded
4. **Token Limits**: Content too long for model context
5. **Network Issues**: Connection problems with OpenAI API

### Error Responses
All endpoints return structured error responses:
```json
{
  "detail": "Error description",
  "status_code": 400
}
```

## Usage Guidelines

### Best Practices
1. **Content Quality**: Ensure articles have sufficient content for meaningful analysis
2. **API Key Management**: Keep API keys secure and rotate regularly
3. **Rate Limiting**: Be mindful of OpenAI API rate limits
4. **Cache Usage**: Use cached results when possible to reduce costs
5. **Content Length**: Articles with 1000+ characters work best

### Limitations
1. **Content Length**: Maximum 8,000 characters processed
2. **Model Context**: GPT-4 has 8,192 token limit
3. **API Dependencies**: Requires active internet connection
4. **Cost Considerations**: Each API call incurs OpenAI charges

## Troubleshooting

### Common Issues
1. **"API key required"**: Configure OpenAI API key in Settings
2. **"Article not found"**: Check article ID and permissions
3. **"Training category required"**: SIGMA generation requires "chosen" articles
4. **"JSON parse error"**: IOC extraction may include explanatory text
5. **"Timeout"**: Increase timeout or reduce content length

### Debug Steps
1. Check browser console for JavaScript errors
2. Verify API key configuration
3. Test with shorter content
4. Check network connectivity
5. Review server logs for detailed errors

## Future Enhancements

### Planned Features
1. **Batch Processing**: Process multiple articles simultaneously
2. **Custom Prompts**: User-defined prompts for each feature
3. **Result Export**: Export AI results in various formats
4. **Quality Scoring**: AI-powered content quality assessment
5. **Integration**: Connect with external threat intelligence platforms

### Technical Improvements
1. **Streaming Responses**: Real-time AI response streaming
2. **Model Selection**: Support for additional AI models
3. **Advanced Caching**: Intelligent cache invalidation
4. **Performance Optimization**: Parallel processing capabilities
5. **Enhanced Error Recovery**: Automatic retry mechanisms
