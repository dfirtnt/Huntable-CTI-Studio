# RAG (Retrieval-Augmented Generation) System

## Overview

The CTI Scraper implements a comprehensive RAG system that combines semantic search with LLM-powered response generation to provide intelligent threat intelligence analysis through conversational AI.

## Architecture

### Core Components

1. **Embedding Service** (`src/services/embedding_service.py`)
   - **Model**: Sentence Transformers `all-mpnet-base-v2` (768-dimensional vectors)
   - **Device**: CUDA if available, else CPU
   - **Enriched Text**: Combines title, source, summary, tags, content
   - **Batch Processing**: Supports batch embedding generation

2. **Vector Storage** (`src/database/models.py`)
   - **Articles Table**: `embedding` column (Vector(768)) with pgvector index
   - **Annotations Table**: `embedding` column for chunk-level search
   - **Model Tracking**: `embedding_model` field for version control

3. **RAG Service** (`src/services/rag_service.py`)
   - **Dual Search**: Article-level + chunk-level retrieval
   - **Similarity**: Cosine similarity using pgvector `<=>` operator
   - **Chunk Strategy**: Uses `article_annotations` table for fine-grained retrieval

4. **LLM Generation Service** (`src/services/llm_generation_service.py`)
   - **Multi-Provider**: OpenAI GPT-4o, Anthropic Claude, Ollama
   - **Auto-Selection**: Automatically chooses best available provider
   - **Fallback**: Graceful degradation to template responses
   - **Context Management**: Conversation history integration

5. **API Endpoint** (`src/web/routes/chat.py`)
   - **Endpoint**: `POST /api/chat/rag`
   - **Parameters**: Message, conversation history, LLM provider selection
   - **Response**: Synthesized analysis with source citations

## Features

### Conversational AI
- **Multi-Turn Conversations**: Maintains context across multiple exchanges
- **Context Memory**: Last 4 conversation turns used for LLM context
- **Follow-Up Questions**: Natural conversation flow with reference resolution

### Multi-Provider LLM Support
- **OpenAI GPT-4o**: Primary provider for high-quality analysis
- **Anthropic Claude**: Alternative provider with different strengths
- **Ollama**: Local LLM for privacy-sensitive environments
- **Template Fallback**: Structured responses when LLM unavailable

### Semantic Search
- **Vector Similarity**: 768-dimensional embeddings for semantic matching
- **Hybrid Retrieval**: Both article-level and chunk-level search
- **Configurable Thresholds**: Adjustable similarity thresholds
- **Source Attribution**: All responses include source citations

### Response Synthesis
- **Professional Format**: Structured threat intelligence analysis
- **Actionable Recommendations**: Specific security guidance
- **Source Integration**: Seamless incorporation of retrieved content
- **Confidence Scoring**: Relevance scores for all sources

## Usage

### API Request
```json
{
  "message": "What are the latest ransomware threats?",
  "conversation_history": [
    {
      "role": "user",
      "content": "Previous question",
      "timestamp": "2025-01-23T00:00:00Z"
    }
  ],
  "use_llm_generation": true,
  "llm_provider": "auto",
  "max_results": 10,
  "similarity_threshold": 0.3,
  "use_chunks": false,
  "context_length": 2000
}
```

### API Response
```json
{
  "response": "Synthesized threat intelligence analysis...",
  "conversation_history": [...],
  "relevant_articles": [...],
  "total_results": 5,
  "llm_provider": "openai",
  "use_llm_generation": true,
  "timestamp": "2025-01-23T00:00:00Z"
}
```

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for GPT-4o access
- `ANTHROPIC_API_KEY`: Anthropic API key for Claude access
- `LLM_API_URL`: Ollama service URL (default: http://cti_ollama:11434)
- `LLM_MODEL`: Ollama model name (default: llama3.2:1b)

### Frontend Configuration
- **LLM Provider Selection**: Dropdown to choose provider
- **LLM Synthesis Toggle**: Enable/disable LLM generation
- **Similarity Threshold**: Adjust search precision
- **Max Results**: Control response length

## System Prompt

The RAG system uses a specialized cybersecurity analyst prompt:

```
You are a cybersecurity threat intelligence analyst. Your role is to analyze threat intelligence data and provide synthesized, actionable insights.

Guidelines:
- Synthesize information from multiple sources into coherent insights
- Focus on threat hunting relevance and detection opportunities
- Provide specific, actionable recommendations
- Cite sources when making claims
- Be concise but comprehensive
- Prioritize recent and high-confidence intelligence
- Identify patterns, trends, and correlations across sources

Response format:
- Start with a clear, direct answer to the user's question
- Provide synthesized insights with supporting evidence
- Include actionable recommendations
- Mention key sources and their relevance scores
```

## Performance

### Response Times
- **Template Mode**: < 2 seconds
- **OpenAI GPT-4o**: 3-5 seconds
- **Anthropic Claude**: 4-6 seconds
- **Ollama Local**: 10-30 seconds (depending on model size)

### Quality Metrics
- **Relevance**: 60-95% similarity scores for retrieved content
- **Synthesis**: Professional threat intelligence format
- **Actionability**: Specific security recommendations
- **Accuracy**: Source attribution with confidence scores

## Troubleshooting

### Common Issues
1. **LLM Timeout**: Falls back to template responses
2. **API Key Missing**: Uses Ollama or template mode
3. **No Results**: Adjust similarity threshold or query
4. **Slow Responses**: Check LLM provider status

### Debugging
- Check service logs: `docker-compose logs web`
- Verify API keys: `docker-compose exec web env | grep API_KEY`
- Test LLM providers individually
- Monitor conversation history in database

## Future Enhancements

### Planned Features
- **Streaming Responses**: Real-time response generation
- **Custom Prompts**: User-defined analysis templates
- **Advanced Chunking**: ML-based content segmentation
- **Multi-Language Support**: Non-English threat intelligence
- **Integration APIs**: External tool connectivity

### Performance Optimizations
- **Embedding Caching**: Reduce redundant computations
- **Response Caching**: Cache common queries
- **Batch Processing**: Multiple query optimization
- **Model Quantization**: Faster local inference
