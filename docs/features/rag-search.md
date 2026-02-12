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
   - **Similarity**: Cosine similarity using pgvector `<=>` operator (used for RAG retrieval)
   - **Chunk Strategy**: Uses `article_annotations` table for fine-grained retrieval

Note: SIGMA rule similarity matching uses a behavioral novelty scoring algorithm (Atom Jaccard 70% + Logic Shape Similarity 30%). Cosine similarity is retained for RAG-style document retrieval only and is not used for final SIGMA similarity ranking.

4. **LLM Generation Service** (`src/services/llm_generation_service.py`)
   - **Multi-Provider**: OpenAI GPT-4o, Anthropic Claude, LMStudio (local)
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
- **LMStudio (Local)**: Fully supported via LMStudio (see [LM Studio Integration](../llm/lmstudio.md))
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
  "context_length": 2000,
  "include_sigma_rules": true,
  "llm_model": "gpt-4o"
}
```

### API Response
```json
{
  "response": "Synthesized threat intelligence analysis...",
  "conversation_history": [...],
  "relevant_articles": [...],
  "relevant_rules": [...],
  "total_results": 5,
  "total_rules": 42,
  "llm_provider": "openai",
  "llm_model_name": "gpt-4o",
  "use_llm_generation": true,
  "timestamp": "2025-01-23T00:00:00Z"
}
```

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for GPT-4o access
- `ANTHROPIC_API_KEY`: Anthropic API key for Claude access

### Frontend Configuration
- **LLM Provider Selection**: Dropdown to choose provider
- **LLM Synthesis Toggle**: Enable/disable LLM generation
- **Similarity Threshold**: Adjust search precision
- **Max Results**: Control response length

## System Prompt

The RAG system uses the **Huntable Analyst** prompt for detection-focused threat intelligence analysis:

```
SYSTEM PROMPT — Huntable Analyst (RAG Chat Completion)

You are **Huntable Analyst**, a Retrieval-Augmented Cyber Threat Intelligence assistant.  
You analyze retrieved CTI article content to answer user questions about threat behavior, TTPs, and detection engineering.

== Core Behavior ==
1. Ground every statement in retrieved text. Never hallucinate.
2. If retrieval lacks support, say: "No evidence found in retrieved articles."
3. Extract technical signals: process names, command lines, registry paths, API calls, network indicators, telemetry types.
4. Map behavior to MITRE ATT&CK techniques when possible.
5. Provide detection insight: relevant Sysmon EventIDs, Windows Security events, or Sigma rule elements.
6. Rate confidence as **High / Medium / Low** based on textual support.
7. Write concisely—one short paragraph per section.

== Output Template ==
**Answer:** factual synthesis from retrieved sources.  
**Evidence:** article titles or source IDs with one-line justification.  
**Detection Notes:** Sigma-style cues (EventIDs, keywords, log sources).  
**Confidence:** High / Medium / Low.  
**If context insufficient:** say so and suggest refined query terms.

== Conversation Memory ==
- Assume model retains last ~6–8k tokens of dialogue.  
- Re-reference prior context briefly when relevant.  
- Stay consistent across turns; summarize only when asked.
```

## Performance

### Response Times
- **Template Mode**: < 2 seconds
- **OpenAI GPT-4o**: 3-5 seconds
- **Anthropic Claude**: 4-6 seconds
- **LMStudio (Local)**: Fully supported via LMStudio (see [LM Studio Integration](../llm/lmstudio.md))

### Quality Metrics
- **Relevance**: 60-95% similarity scores for retrieved content
- **Synthesis**: Professional threat intelligence format
- **Actionability**: Specific security recommendations
- **Accuracy**: Source attribution with confidence scores

## Troubleshooting

### Common Issues
1. **LLM Timeout**: Falls back to template responses
2. **API Key Missing**: Uses template mode
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
