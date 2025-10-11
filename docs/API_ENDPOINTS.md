# CTI Scraper API Endpoints

This document provides a comprehensive list of all API endpoints available in the CTI Scraper application.

## Overview

The CTI Scraper provides 85+ API endpoints across multiple categories:
- **Health & Monitoring**: 8 endpoints
- **Sources Management**: 12 endpoints  
- **Articles Management**: 25 endpoints
- **AI & Analysis**: 15 endpoints
- **Annotations**: 8 endpoints
- **Jobs & Tasks**: 6 endpoints
- **Metrics & Dashboard**: 7 endpoints
- **Backup Management**: 3 endpoints
- **Web Pages**: 10 endpoints

## Health & Monitoring Endpoints

### Basic Health Checks
- `GET /health` - Basic health check
- `GET /api/health` - API health check
- `GET /api/health/database` - Database health with statistics
- `GET /api/health/deduplication` - Deduplication system health
- `GET /api/health/services` - External services health (Redis, Ollama)
- `GET /api/health/celery` - Celery workers health
- `GET /api/health/ingestion` - Ingestion analytics health
- `GET /api/metrics/health` - Metrics health check

## Backup Management Endpoints

### Backup Operations
- `POST /api/backup/create` - Create a new system backup
- `GET /api/backup/list` - List all available backups with sizes
- `GET /api/backup/status` - Get backup system status and statistics

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
- `GET /api/articles/next-unclassified` - Get next unclassified article
- `GET /api/articles/next` - Get next article by ID
- `GET /api/articles/previous` - Get previous article by ID
- `GET /api/articles/top` - Get top-scoring articles for dashboard
- `GET /api/articles/{article_id}/similar` - Get similar articles using embeddings
- `POST /api/articles/{article_id}/classify` - Classify article (chosen/rejected)
- `POST /api/articles/bulk-action` - Perform bulk actions on multiple articles
- `DELETE /api/articles/{article_id}` - Delete specific article

### Article Analysis
- `POST /api/articles/{article_id}/chatgpt-summary` - Generate ChatGPT summary
- `POST /api/articles/{article_id}/custom-prompt` - Custom AI prompt analysis
- `POST /api/articles/{article_id}/generate-sigma` - Generate SIGMA detection rules
- `POST /api/articles/{article_id}/extract-iocs` - Extract IOCs using hybrid approach
- `POST /api/articles/{article_id}/rank-with-gpt4o` - GPT4o huntability ranking
- `POST /api/articles/{article_id}/gpt4o-rank-optimized` - Optimized GPT4o ranking
- `POST /api/articles/{article_id}/embed` - Generate article embedding
- `GET /api/articles/{article_id}/chunk-debug` - Debug chunk classification

## AI & Analysis Endpoints

### AI Services
- `POST /api/chat/rag` - RAG chat interface
- `POST /api/search/semantic` - Semantic search using embeddings
- `POST /api/test-chatgpt-summary` - Test ChatGPT summary functionality
- `POST /api/test-openai-key` - Test OpenAI API key validity
- `POST /api/test-anthropic-key` - Test Anthropic API key validity
- `POST /api/test-claude-summary` - Test Claude summary functionality

### Embeddings & ML
- `GET /api/embeddings/stats` - Get embedding statistics
- `POST /api/embeddings/update` - Update embeddings for articles/annotations
- `POST /api/feedback/chunk-classification` - Provide feedback on chunk classifications
- `POST /api/model/retrain` - Trigger model retraining using user feedback

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

## Jobs & Tasks Endpoints

### Task Management
- `GET /api/tasks/{task_id}/status` - Get task status and result
- `GET /api/jobs/status` - Get current job status
- `GET /api/jobs/queues` - Get job queue information
- `GET /api/jobs/history` - Get job execution history

### Actions
- `POST /api/actions/rescore-all` - Rescore all articles
- `POST /api/actions/generate-report` - Generate system report

## Metrics & Dashboard Endpoints

### Dashboard Data
- `GET /api/dashboard/data` - Get dashboard data and statistics
- `GET /api/metrics/volume` - Get volume metrics
- `GET /api/search/help` - Get search syntax help

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
- `GET /help` - Help page
- `GET /pdf-upload` - PDF upload page

## File Upload Endpoints

### Document Processing
- `POST /api/pdf/upload` - Upload and process PDF files

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
