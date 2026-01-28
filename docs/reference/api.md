# CTI Scraper API Endpoints

This document provides a comprehensive list of all API endpoints available in the CTI Scraper application.

## Overview

The CTI Scraper provides **170+ API endpoints** across multiple categories:
- **Health & Monitoring**: 8 endpoints
- **Web Pages**: 19 endpoints
- **Sources Management**: 10 endpoints  
- **Articles Management**: 12 endpoints
- **AI & Analysis**: 15 endpoints
- **RAG Chat Interface**: 1 endpoint
- **ML Feedback & Model Management**: 10 endpoints
- **Annotations**: 8 endpoints
- **Jobs & Tasks**: 7 endpoints
- **Metrics & Dashboard**: 20 endpoints
- **Backup Management**: 3 endpoints
- **Workflow Execution**: 9 endpoints
- **Workflow Configuration**: 9 endpoints
- **ML vs Hunt Comparison**: 7 endpoints
- **Embeddings & ML**: 3 endpoints
- **Observable Evaluation**: 4 endpoints
- **Observable Training**: 2 endpoints
- **Sigma Queue**: 3 endpoints
- **File Upload**: 1 endpoint

## Health & Monitoring Endpoints

### Basic Health Checks
- `GET /health` - Basic health check
- `GET /api/health` - API health check
- `GET /api/health/database` - Database health with statistics
- `GET /api/health/deduplication` - Deduplication system health
- `GET /api/health/services` - External services health (Redis)
- `GET /api/health/celery` - Celery workers health
- `GET /api/health/ingestion` - Ingestion analytics health
- `GET /api/metrics/health` - Metrics health check

## RAG Chat Interface Endpoints

### Conversational AI
- `POST /api/chat/rag` - Interactive chat with threat intelligence database using semantic search
  - **Parameters**: 
    - `message` (string): User query
    - `conversation_history` (array): Previous conversation context
    - `use_llm_generation` (boolean): Enable LLM synthesis (default: true)
    - `llm_provider` (string): LLM provider ("auto", "openai", "anthropic", "template")
    - `max_results` (integer): Maximum results to retrieve (default: 10)
    - `similarity_threshold` (float): Similarity threshold (default: 0.3)
    - `use_chunks` (boolean): Use chunk-level search (default: false)
    - `context_length` (integer): Context length per chunk (default: 2000)
  - **Response**: Synthesized analysis with source citations and conversation history
  - **Features**: Multi-turn conversations, context memory, LLM synthesis with fallback

## ML Feedback & Model Management Endpoints

### Model Versioning & Comparison
- `GET /api/model/versions` - List all model versions with performance metrics
- `GET /api/model/compare/{version_id}` - Compare model versions and get performance differences
- `GET /api/model/feedback-comparison` - Get feedback impact analysis showing confidence changes
- `GET /api/model/classification-timeline` - Get classification trends data across model versions
- `GET /api/model/feedback-count` - Get count of available feedback samples for retraining
- `GET /api/model/eval-chunk-count` - Get evaluation chunk count
- `GET /api/model/retrain-status` - Get model retraining status
- `POST /api/model/retrain` - Retrain model with user feedback data
- `POST /api/model/evaluate` - Evaluate current model on test set with detailed metrics
- `POST /api/feedback/chunk-classification` - Submit user feedback on chunk classifications
- `GET /api/feedback/chunk-classification/{article_id}/{chunk_id}` - Get specific feedback

## ML vs Hunt Comparison Endpoints

### Comparison Operations
- `GET /api/ml-hunt-comparison/summary` - Get dashboard summary statistics
- `GET /api/ml-hunt-comparison/stats` - Get detailed comparison statistics
- `GET /api/ml-hunt-comparison/eligible-count` - Get count of articles eligible for processing
- `GET /api/ml-hunt-comparison/results` - Get comparison results
- `GET /api/ml-hunt-comparison/model-versions` - Get model versions for comparison

## Backup Management Endpoints

### Backup Operations
- `POST /api/backup/create` - Create a new system backup
- `GET /api/backup/list` - List all available backups with sizes
- `GET /api/backup/status` - Get backup system status and statistics

## Workflow Execution Endpoints

### Agentic Workflow Operations
- `GET /api/workflow/executions` - List workflow executions with filtering
  - **Query Parameters**:
    - `article_id` (optional): Filter by article ID
    - `status` (optional): Filter by execution status
    - `limit` (default: 50): Maximum number of results
- `GET /api/workflow/executions/{execution_id}` - Get detailed workflow execution information
  - **Response**: Includes execution status, step results, ranking score, and error logs
- `POST /api/workflow/executions/{execution_id}/retry` - Retry a failed workflow execution
- `GET /api/workflow/executions/{execution_id}/debug-info` - Get debug information for workflow execution
  - **Response**: Detailed debug data and execution state
- `POST /api/workflow/articles/{article_id}/trigger` - Manually trigger agentic workflow for an article via Celery

### Workflow Configuration
- `GET /api/workflow/config` - Get current workflow configuration (includes `agent_models` and prompts)
- `PUT /api/workflow/config` - Update workflow configuration (including agent model assignments via `agent_models`)
- `GET /api/workflow/config/prompts` - Get all agent prompts
- `GET /api/workflow/config/prompts/{agent_name}` - Get single agent prompt
- `PUT /api/workflow/config/prompts` - Update agent prompts; body includes `agent_name`, `system_prompt`, `user_prompt` (bulk update)
- `GET /api/workflow/config/prompts/{agent_name}/versions` - Get prompt version history
- `POST /api/workflow/config/prompts/{agent_name}/rollback` - Rollback prompt to a prior version
- `GET /api/workflow/config/preset/list`, `GET /api/workflow/config/versions`, `GET /api/workflow/config/version/{version_number}` - Presets and version history

## Sources Management Endpoints

### Source Operations
- `GET /api/sources` - List all sources with filtering
- `GET /api/sources/failing` - Get failing sources for dashboard
- `GET /api/sources/{source_id}` - Get specific source details
- `POST /api/sources/{source_id}/toggle` - Toggle source active status
- `POST /api/sources/{source_id}/collect` - Manually trigger collection
- `PUT /api/sources/{source_id}/min_content_length` - Update minimum content length
- `PUT /api/sources/{source_id}/lookback` - Update source lookback window
- `PUT /api/sources/{source_id}/check_frequency` - Update check frequency
- `GET /api/sources/{source_id}/stats` - Get source statistics
- `POST /api/scrape-url` - Scrape a single URL manually
- `GET /api/test-route` - Test route for verification

## Articles Management Endpoints

### Article Operations
- `GET /api/articles` - List articles with pagination and filtering
- `GET /api/articles/{article_id}` - Get specific article details
- `GET /api/articles/search` - Search articles with advanced queries
- `GET /api/articles/next` - Get next article by ID
- `GET /api/articles/previous` - Get previous article by ID
- `GET /api/articles/top` - Get top-scoring articles for dashboard
- `GET /api/articles/{article_id}/similar` - Get similar articles using embeddings
- `POST /api/articles/bulk-action` - Bulk delete articles (action `delete` only)
- `DELETE /api/articles/{article_id}` - Delete specific article
- `GET /api/search/help` - Get search syntax help

### Article Analysis
- `POST /api/articles/{article_id}/custom-prompt` - Custom AI prompt analysis
- `POST /api/articles/{article_id}/generate-sigma` - Generate SIGMA detection rules
- `POST /api/articles/{article_id}/extract-iocs` - Extract IOCs using hybrid approach
- `POST /api/articles/{article_id}/rank-with-gpt4o` - GPT4o huntability ranking
- `POST /api/articles/{article_id}/gpt4o-rank-optimized` - Optimized GPT4o ranking
- `POST /api/articles/{article_id}/embed` - Generate article embedding
- `GET /api/articles/{article_id}/chunk-debug` - Debug chunk classification (see detailed description below)

## AI & Analysis Endpoints

### AI Services
- `POST /api/chat/rag` - RAG chat interface
- `POST /api/search/semantic` - Semantic search using embeddings
- `POST /api/test-openai-key` - Test OpenAI API key validity
- `POST /api/test-anthropic-key` - Test Anthropic API key validity
- `POST /api/test-claude-summary` - Test Claude summary functionality
- `POST /api/articles/{article_id}/custom-prompt` - Custom AI prompt analysis
- `POST /api/articles/{article_id}/generate-sigma` - Generate SIGMA detection rules
- `POST /api/articles/{article_id}/extract-iocs` - Extract IOCs using hybrid approach
- `POST /api/articles/{article_id}/rank-with-gpt4o` - GPT4o huntability ranking
- `POST /api/articles/{article_id}/gpt4o-rank-optimized` - Optimized GPT4o ranking
- `POST /api/articles/{article_id}/embed` - Generate article embedding
- `GET /api/articles/{article_id}/chunk-debug` - Debug chunk classification (see detailed description below)
- `GET /api/test-route` - Test route for verification

#### `GET /api/articles/{article_id}/chunk-debug`

Debug endpoint returning the ML model’s per-chunk decisions and supporting metadata.

**Query Parameters**

| Name | Default | Description |
| --- | --- | --- |
| `chunk_size` | `1000` | Maximum characters per chunk (trimmed to sentence boundaries) |
| `overlap` | `200` | Characters overlapped between adjacent chunks |
| `min_confidence` | `0.7` | Minimum ML confidence required to keep a chunk |
| `full_analysis` | `false` | When `true`, bypasses the safety cap and processes every chunk |

**Response Highlights**
- `processing_summary` – counts processed vs total chunks, indicates whether the cap was hit, reports concurrency, timeout, and remaining chunks.
- `chunk_analysis[]` – per-chunk metadata including ML predictions, feature breakdowns, timeout errors, and booleans for threat keywords/perfect discriminators.
- `ml_stats` – aggregate model accuracy metrics over the processed chunks.
- `filter_result` + `cost_estimate` – overall filtering and cost-savings information.

Use `full_analysis=true` when analysts click **Finish Full Analysis** in the UI; this may take longer but guarantees full coverage. The initial pass respects environment caps (`CHUNK_DEBUG_MAX_CHUNKS`, `CHUNK_DEBUG_CONCURRENCY`, `CHUNK_DEBUG_CHUNK_TIMEOUT`) to keep the interface responsive.

## Annotations Endpoints

### Annotation Operations
- `POST /api/articles/{article_id}/annotations` - Create new annotation
- `GET /api/articles/{article_id}/annotations` - Get all annotations for article
- `GET /api/annotations/{annotation_id}` - Get specific annotation
- `PUT /api/annotations/{annotation_id}` - Update existing annotation
- `DELETE /api/annotations/{annotation_id}` - Delete specific annotation
- `DELETE /api/articles/{article_id}/annotations/{annotation_id}` - Delete annotation from article
- `GET /api/annotations/stats` - Get annotation statistics
- `GET /api/export/annotations` - Export annotations to CSV

## Embeddings & ML Endpoints

### Embedding Operations
- `GET /api/embeddings/stats` - Get embedding statistics
- `POST /api/embeddings/update` - Update embeddings for articles/annotations

## Jobs & Tasks Endpoints

### Task Management
- `GET /api/tasks/{task_id}/status` - Get task status and result
- `GET /api/jobs/status` - Get current job status
- `GET /api/jobs/queues` - Get job queue information
- `GET /api/jobs/history` - Get job execution history

### Actions
- `POST /api/actions/rescore-all` - Rescore all articles
- `POST /api/actions/generate-report` - Generate system report
- `POST /api/actions/health-check` - Trigger health check

## Metrics & Dashboard Endpoints

### Dashboard Data
- `GET /api/dashboard/data` - Get dashboard data and statistics
- `GET /api/metrics/volume` - Get volume metrics
- `GET /api/search/help` - Get search syntax help

### Analytics Endpoints
- `GET /api/analytics/scraper/overview` - Scraper analytics overview
- `GET /api/analytics/scraper/collection-rate` - Collection rate metrics
- `GET /api/analytics/scraper/source-health` - Source health metrics
- `GET /api/analytics/scraper/source-performance` - Source performance metrics
- `GET /api/analytics/hunt/overview` - Hunt analytics overview
- `GET /api/analytics/hunt/score-distribution` - Score distribution metrics
- `GET /api/analytics/hunt/keyword-performance` - Keyword performance metrics
- `GET /api/analytics/hunt/keyword-analysis` - Keyword analysis metrics
- `GET /api/analytics/hunt/score-trends` - Score trends metrics
- `GET /api/analytics/hunt/source-performance` - Hunt source performance
- `GET /api/analytics/hunt/quality-distribution` - Quality distribution metrics
- `GET /api/analytics/hunt/advanced-metrics` - Advanced hunt metrics
- `GET /api/analytics/hunt/recent-high-scores` - Recent high scores
- `GET /api/analytics/hunt/performance-insights` - Performance insights
- `GET /api/analytics/hunt-demo/articles` - Hunt demo articles
- `GET /api/analytics/hunt-demo/sources` - Hunt demo sources
- `GET /api/analytics/hunt-demo/keywords` - Hunt demo keywords
- `GET /api/analytics/hunt-demo/ml-models` - Hunt demo ML models

## Web Pages

### HTML Pages
- `GET /` - Main dashboard page
- `GET /dashboard` - Dashboard page (alias)
- `GET /articles` - Articles listing page
- `GET /articles/{article_id}` - Article detail page
- `GET /sources` - Sources management page
- `GET /settings` - Settings page
- `GET /health-checks` - Health checks monitoring page
- `GET /chat` - RAG chat interface page
- `GET /jobs` - Jobs monitoring page
- `GET /pdf-upload` - PDF upload page
- `GET /analytics` - Analytics page
- `GET /analytics/scraper-metrics` - Scraper metrics page
- `GET /analytics/hunt-metrics` - Hunt metrics page
- `GET /analytics/hunt-metrics-demo` - Hunt metrics demo page
- `GET /ml-hunt-comparison` - ML vs Hunt comparison page
- `GET /diags` - Diagnostics page

## File Upload Endpoints

### Document Processing
- `POST /api/pdf/upload` - Upload and process PDF files
  - **Parameters**: 
    - `file`: PDF file (max 50MB)
  - **Response**: 
    - `article_id`: Created article ID
    - `threat_hunting_score`: Article's threat score
    - `page_count`: Number of pages processed
  - **Features**: 
    - Text extraction from PDF
    - Automatic page separation
    - Content deduplication
    - Integration with manual source category
    - Threat hunting score calculation

## API Documentation

### Interactive Documentation
- **Swagger UI**: `http://localhost:8001/docs`
- **ReDoc**: `http://localhost:8001/redoc`
- **OpenAPI Schema**: `http://localhost:8001/openapi.json`

### Authentication
Currently, the API does not require authentication for local development. For production deployments, consider implementing:
- API key authentication
- JWT token authentication
- OAuth2 integration

### Rate Limiting
- API endpoints: 30 requests per minute
- Web traffic: 30 requests per minute
- File uploads: 100MB maximum size

### Error Handling
All API endpoints return consistent error responses:
```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "status_code": 400
}
```

### Response Formats
- **Success responses**: Return data in JSON format
- **Error responses**: Return error information in JSON format
- **File downloads**: Return appropriate content-type headers

## Usage Examples

### Get All Sources
```bash
curl -X GET "http://localhost:8001/api/sources" \
  -H "Accept: application/json"
```

### Search Articles
```bash
curl -X GET "http://localhost:8001/api/articles/search?q=ransomware" \
  -H "Accept: application/json"
```

### Generate SIGMA Rules
```bash
curl -X POST "http://localhost:8001/api/articles/123/generate-sigma" \
  -H "Content-Type: application/json" \
  -d '{"include_content": true, "max_rules": 3}'
```

### RAG Chat
```bash
curl -X POST "http://localhost:8001/api/chat/rag" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the latest ransomware trends?", "context": "recent"}'
```

## Monitoring and Health

### Health Check Integration
All health endpoints can be integrated with monitoring systems:
- Prometheus metrics
- Grafana dashboards
- Alerting systems
- Load balancer health checks

### Performance Metrics
The API provides metrics for:
- Request latency
- Error rates
- Throughput
- Resource utilization

## Security Considerations

### Input Validation
- All inputs are validated using Pydantic models
- SQL injection protection via SQLAlchemy ORM
- XSS protection for web endpoints
- File upload validation and sanitization

### CORS Configuration
CORS is configured for localhost development:
```python
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8001"]
```

### Rate Limiting
Rate limiting is implemented to prevent abuse:
- API endpoints: 30 requests per minute
- Web traffic: 30 requests per minute

## Future Enhancements

### Planned API Improvements
- GraphQL endpoint for flexible data querying
- WebSocket support for real-time updates
- Batch operations for bulk data processing
- Advanced filtering and sorting options
- API versioning support
- Enhanced authentication and authorization

### Integration Opportunities
- SIEM platform integration
- Threat intelligence platform integration
- Security orchestration tools
- Machine learning pipeline integration

---

**Note**: This API documentation is automatically generated from the FastAPI application. For the most up-to-date information, visit the interactive documentation at `http://localhost:8001/docs`.