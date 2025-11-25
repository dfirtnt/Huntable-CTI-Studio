# CTI Scraper System - Build Prompt for Claude Code

## System Overview

Build a comprehensive threat intelligence aggregation and analysis platform that collects, processes, and analyzes cybersecurity content from multiple sources. The system must operate within a **strict $100/month AWS budget** with all architectural decisions driven by cost optimization.

## Core Requirements

### 1. Web Scraper Components

**RSS Feed Parser (Primary Method)**
- Parse RSS/Atom feeds from configured sources
- Extract article metadata: title, URL, published date, authors, summary
- Handle feed validation and error recovery
- Prefer RSS over web scraping when available

**Web Scraper (Fallback Method)**
- CSS selector-based content extraction
- JSON-LD structured data parsing
- OpenGraph metadata extraction
- Basic HTML parsing for sites without structured data
- Rate limiting and respectful crawling (robots.txt compliance)

**Source Configuration**
- Hardcoded source list (no YAML configuration system needed)
- Each source should have: name, URL, RSS URL (optional), check frequency
- Simple source health tracking (last check, success/failure)

### 2. Database Schema

**Core Tables (PostgreSQL with pgvector extension)**

- `sources`: Source configuration and health metrics
  - Fields: id, identifier, name, url, rss_url, check_frequency, active, last_check, last_success, consecutive_failures, total_articles, created_at, updated_at

- `articles`: Article content and metadata
  - Fields: id, source_id, canonical_url, title, published_at, modified_at, authors (JSON), tags (JSON), summary, content, content_hash (unique), article_metadata (JSONB), discovered_at, processing_status, word_count, embedding (Vector(768)), embedding_model, embedded_at, created_at, updated_at, archived
  - Indexes on: canonical_url, content_hash, published_at, processing_status, archived

- `source_checks`: Source check history
  - Fields: id, source_id, check_time, success, method, articles_found, response_time, error_message, check_metadata (JSON)

- `article_annotations`: User annotations for ML training
  - Fields: id, article_id, user_id (nullable), annotation_type ('huntable' or 'not_huntable'), selected_text, start_position, end_position, context_before, context_after, confidence_score, embedding (Vector(768)), embedding_model, embedded_at, used_for_training, created_at, updated_at

- `content_hashes`: Content hash tracking for deduplication
  - Fields: id, content_hash (unique), article_id, first_seen

- `chunk_analysis_results`: ML chunk classification results
  - Fields: id, article_id, chunk_index, chunk_text, ml_prediction ('huntable' or 'not_huntable'), ml_confidence, hunt_score, passed_filter, created_at

- `chunk_classification_feedback`: User feedback on ML predictions
  - Fields: id, article_id, chunk_id, chunk_text, model_classification, model_confidence, is_correct (boolean), user_classification, comment, created_at

- `agentic_workflow_config`: Workflow configuration
  - Fields: id, name, min_hunt_score, junk_filter_threshold, is_active, agent_models (JSONB), agent_prompts (JSONB), qa_enabled (JSONB), created_at, updated_at

- `agentic_workflow_executions`: Workflow execution tracking
  - Fields: id, article_id, config_id, status, current_step, ranking_score, ranking_reasoning, os_detection_result (JSONB), extraction_result (JSONB), sigma_rules (JSONB), similarity_results (JSONB), termination_reason, error_message, started_at, completed_at, created_at

- `sigma_rules`: SIGMA detection rules
  - Fields: id, rule_id (unique), title, description, logsource (JSONB), detection (JSONB), tags (JSONB), level, falsepositives, author, date, modified, references (JSONB), title_embedding (Vector(768)), description_embedding (Vector(768)), tags_embedding (Vector(768)), signature_embedding (Vector(768)), embedded_at

- `article_sigma_matches`: Article-to-SIGMA rule matches
  - Fields: id, article_id, sigma_rule_id, similarity_score, match_type, created_at

- `sigma_rule_queue`: Queue for human review of generated SIGMA rules
  - Fields: id, workflow_execution_id, article_id, rule_yaml, rule_data (JSONB), similarity_max, similarity_results (JSONB), status, created_at, reviewed_at

**Note**: Do NOT include SimHash tables or near-duplicate detection. Use content_hash for exact deduplication only.

### 3. Job Handling (Celery Alternative)

**Background Task System**
- Use AWS-native task queue (SQS + Lambda or ECS Fargate Spot) instead of Celery
- Periodic tasks:
  - Check all sources every 30 minutes
  - Generate daily reports at 6 AM
  - Embed new articles daily at 3 PM
- Task types:
  - Source checking (RSS parsing, web scraping)
  - Article processing (cleaning, scoring, deduplication)
  - Workflow triggering (for high-scoring articles)
  - ML model retraining (when sufficient feedback collected)

**Cost Optimization**: Use serverless (Lambda) for short tasks, Fargate Spot for longer-running workers. Consider AWS Batch for ML training jobs.

### 4. Hunt Scoring System

**Threat Hunting Score (0-100)**
- Keyword-based scoring using logarithmic bucket system
- Perfect discriminators (75 points max, 103 patterns): Windows malware indicators, registry keys, suspicious paths, command-line patterns
- Good discriminators (5 points max): Supporting technical content
- LOLBAS executables (10 points max): Living-off-the-land binaries
- Intelligence indicators (10 points max): Threat intelligence keywords
- Negative penalty (-10 points max): Educational/marketing content markers

**ML Hunt Score (0-100)**
- Chunk-based RandomForest classification
- Articles split into chunks (1000 chars, 200 overlap)
- Each chunk classified as "huntable" or "not_huntable" with confidence
- Aggregate chunk scores to article-level score
- Metric options: weighted_average, proportion_weighted, confidence_sum_normalized

**Implementation**: Store both scores in `article_metadata` JSONB field. Recalculate ML score when model is retrained.

### 5. Discriminator System

**Perfect Discriminators (103 patterns)**
- Windows-specific: `rundll32`, `comspec`, `msiexec`, `wmic`, `iex`, `findstr`, `hklm`, `appdata`, `programdata`, `powershell.exe`, `wbem`, `.lnk`, `D:\`, `.iso`, `<Command>`, `MZ`
- Registry patterns: `HKLM\`, `HKCU\`, registry modification keywords
- Process patterns: parent-child relationships, suspicious executables
- File system patterns: suspicious paths, temporary directories

**Usage**: 
- Hunt scoring system uses these for keyword matching
- Content filter uses these to protect chunks from being filtered
- ML model uses these as features

### 6. Chunk and Garbage Handling Content Filter System

**ML-Based Content Filter**
- Purpose: Filter out "not huntable" content before sending to AWS Bedrock (cost optimization)
- Architecture:
  1. Chunk content (1000 chars, 200 overlap)
  2. Hunt scoring per chunk
  3. Pattern-based classification (perfect discriminators = always pass)
  4. ML classification (RandomForest with TF-IDF features + hunt score)
  5. Filter chunks below confidence threshold
  6. Return filtered content (huntable chunks only)

**Filter Configuration**
- `min_confidence`: Minimum confidence threshold (default 0.7)
- `chunk_size`: 1000 characters
- `chunk_overlap`: 200 characters
- `protect_perfect_discriminators`: Always true (chunks with perfect keywords never filtered)

**Cost Savings**: Achieve 20-80% reduction in Bedrock API costs by filtering irrelevant content.

### 7. Annotation System

**Text Annotation Interface**
- Web UI for selecting text in articles (approximately 1000 characters)
- Annotation types: 'huntable' or 'not_huntable'
- Store: selected_text, start_position, end_position, context_before, context_after
- Generate embeddings for annotations (768-dimensional, pgvector)
- Track `used_for_training` flag to prevent duplicate training data usage

**Feedback Collection**
- Users can provide feedback on ML chunk classifications
- Store: model_classification, model_confidence, is_correct, user_classification, comment
- Used for model retraining

**Training Data Management**
- Query unused annotations and feedback for retraining
- Mark data as `used_for_training` after model training
- Support cumulative learning (retrain on all unused data, not just new)

### 8. Machine Learning Model Management

**Content Filter Model (RandomForest)**
- Train on annotations and feedback data
- Features: TF-IDF vectors + hunt score + pattern matches
- Output: Binary classification ('huntable' or 'not_huntable') with confidence score
- Model versioning: Store model version number, training date, accuracy metrics
- Model storage: Save trained models (pickle format) with version tracking

**Training Pipeline**
- Trigger retraining when sufficient new data available (configurable threshold)
- Train/test split: 80/20
- Store training metrics: accuracy, precision, recall, F1-score
- Update model version after successful training

**ML vs Hunt Comparison Dashboard**
- Compare ML predictions vs hunt score predictions
- Track classification trends over time
- Identify discrepancies for manual review
- Performance metrics: accuracy, false positive rate, cost savings

### 9. AIML Assistant Models (AWS Bedrock)

**Model Configuration**
- Use AWS Bedrock for all LLM operations (no LM Studio)
- Support multiple models per agent (configurable via workflow config)
- Model types:
  - RankAgent: Article ranking/scoring
  - ExtractAgent: Observable extraction
  - SigmaAgent: SIGMA rule generation
  - QAAgent: Quality assurance evaluation

**LLM Service Requirements**
- Handle Bedrock API calls (boto3)
- Support streaming responses
- Context window management (truncate content if needed)
- Retry logic with exponential backoff
- Cost tracking per API call

**Cost Optimization**:
- Use smaller/cheaper models where possible (e.g., Claude Haiku for simple tasks)
- Batch requests when possible
- Cache responses for identical content
- Use content filter to reduce input tokens

### 10. Agentic Workflow (LangGraph)

**Workflow Steps (7 steps)**

1. **Junk Filter**
   - Apply content filter to article
   - Remove non-huntable chunks
   - Store filtered content in workflow state

2. **LLM Rank Article**
   - Use RankAgent (Bedrock) to score article relevance
   - Output: ranking_score (0-100), ranking_reasoning
   - Terminate workflow if score below threshold

3. **OS Detection**
   - Keyword-based OS detection (Windows/Linux/macOS/multiple)
   - Simple pattern matching against OS-specific keywords
   - Terminate workflow if non-Windows (unless multi-OS detected)

4. **Extract Agent**
   - Use ExtractAgent (Bedrock) with sub-agents:
     - CmdlineExtract: Command-line patterns
     - SigExtract: Detection query fragments
     - EventIDExtract: Windows Event IDs
     - ProcessLineageExtract: Parent-child process chains
     - RegistryExtract: Registry key/value operations
   - Supervisor pattern: Aggregate sub-agent results
   - QA Agent: Validate outputs, retry with feedback if needed
   - Store extraction_result in workflow state

5. **Generate SIGMA Rules**
   - Use SigmaAgent (Bedrock) to generate SIGMA detection rules
   - Input: extraction_result from step 4
   - Output: Array of SIGMA rule YAML strings
   - Validate rule structure

6. **Similarity Search**
   - Use pgvector to find similar existing SIGMA rules
   - Compare generated rules against `sigma_rules` table
   - Section-based matching: title (4.2%), description (4.2%), tags (4.2%), signature (87.4%)
   - Store similarity_results with max_similarity score

7. **Queue Promotion**
   - If max_similarity below threshold, promote to `sigma_rule_queue`
   - Store rule YAML, rule_data, similarity results
   - Status: 'pending' for human review

**Workflow State Management**
- Use LangGraph StateGraph for state machine
- Store execution state in `agentic_workflow_executions` table
- Track current_step, status, error_message
- Support workflow termination at any step

**Langfuse Integration**
- Trace all LLM calls through workflow
- Log workflow steps, state transitions, errors
- Track costs per workflow execution
- Store traces in Langfuse for observability

### 11. SIGMA Rule System

**SIGMA Rule Generation**
- Generate YAML-formatted SIGMA rules from extracted observables
- Include: title, description, logsource, detection, tags, level, falsepositives, author, date
- Validate YAML structure before storing

**SIGMA Rule Similarity Matching**
- Use pgvector embeddings for semantic search
- Generate embeddings for: title, description, tags, signature (logsource + detection structure + detection fields)
- Weighted similarity: signature (87.4%), others (4.2% each)
- Store matches in `article_sigma_matches` table

**SIGMA Rule Queue**
- Human review queue for generated rules
- Display: rule YAML, similarity results, article context
- Actions: approve, reject, edit
- Link to workflow execution for full context

**SIGMA Rule Validation/Scoring**
- Validate YAML structure
- Check required fields
- Score rule quality (optional: use LLM to evaluate rule quality)

### 12. Full Web UI

**Technology Stack**
- FastAPI backend with Jinja2 templates
- PostgreSQL database (async SQLAlchemy)
- Modern responsive UI (dark mode)

**Pages/Features**

1. **Dashboard**
   - Statistics: total articles, sources, recent activity
   - Recent articles list
   - Source health status
   - Workflow execution summary

2. **Articles Page**
   - Article list with pagination
   - Search functionality (basic text search)
   - Filters: source, date range, hunt score range
   - Article detail view: full content, metadata, annotations, workflow executions

3. **Source Management**
   - List all sources (hardcoded)
   - View source health metrics
   - Manual trigger source check
   - View source check history

4. **Workflow Executions**
   - List all workflow executions
   - Filter by status, article, date
   - View execution details: steps, state, results
   - Toggle to show observable counts (cmdline, process_lineage, registry, event_ids, sigma_queries)

5. **Annotation Interface**
   - Text selection in article view
   - Create annotation (huntable/not_huntable)
   - View existing annotations
   - Annotation must be ~1000 characters

6. **ML Model Management**
   - View model version, training metrics
   - Trigger model retraining
   - View training data statistics (annotations, feedback)
   - ML vs Hunt comparison dashboard

7. **SIGMA Rule Queue**
   - List pending rules for review
   - View rule YAML, similarity matches, article context
   - Approve/reject/edit actions

**API Endpoints**
- REST API for all operations
- OpenAPI/Swagger documentation at `/docs`
- Async endpoints for better performance

### 13. Cost Management (CRITICAL)

**Budget Constraint: $100/month total AWS costs**

**Cost Optimization Principles**:
1. **Compute**: Choose based on cost analysis
   - Lambda for short tasks (<15 min)
   - ECS Fargate Spot for workers (up to 70% savings)
   - EC2 t3.micro/t4g.micro for persistent services (if needed)
   - Consider AWS Batch for ML training

2. **Database**: 
   - RDS PostgreSQL db.t3.micro (or db.t4g.micro for ARM)
   - Enable automated backups (7-day retention)
   - Use pgvector extension (no additional cost)

3. **Storage**:
- S3 for model storage and backups (minimal cost, use S3 Standard-IA for backups)
- EBS volumes only if using EC2

4. **Bedrock API**:
   - Use content filter to reduce input tokens (20-80% reduction)
   - Cache identical requests
   - Use cheaper models where appropriate (Haiku vs Sonnet)
   - Batch requests when possible
   - Monitor usage with CloudWatch

5. **Networking**:
   - Use VPC endpoints for Bedrock (reduce data transfer costs)
   - Minimize cross-AZ data transfer

6. **Monitoring**:
   - CloudWatch basic monitoring (included)
   - Set up billing alerts at $80 and $95

**Cost Estimation Guidelines**:
- RDS db.t3.micro: ~$15/month
- ECS Fargate Spot: ~$5-10/month (sparse usage)
- Lambda: ~$1-5/month (pay per request)
- Bedrock API: Target <$50/month (use content filter aggressively)
- S3: ~$2-5/month (model storage + backups, use Standard-IA for backups)
- Data transfer: ~$5/month
- **Total Target: <$100/month**

### 14. Infrastructure as Code (Terraform)

**Required**: All infrastructure must be defined in Terraform

**Components to Define**:
- VPC, subnets, security groups
- RDS PostgreSQL instance (db.t3.micro)
- ECS cluster and Fargate tasks (if used)
- Lambda functions (if used)
- S3 buckets (model storage + backups)
- IAM roles and policies
- CloudWatch alarms (billing alerts)
- VPC endpoints (Bedrock)

**Best Practices**:
- Use variables for all configurable values
- Separate environments (dev/prod) if needed
- Use Terraform modules for reusable components
- Store state in S3 with DynamoDB locking

### 15. Observability

**Langfuse Integration (REQUIRED)**
- Trace all LLM calls (Bedrock API)
- Log workflow executions, steps, state transitions
- Track costs per LLM call
- Store traces for debugging and optimization

**Basic Logging**
- Application logs to CloudWatch Logs
- Log levels: INFO, WARNING, ERROR
- Structured logging (JSON format)

**Workflow Execution Tracking**
- Store execution state in database
- Track current_step, status, errors
- Display in web UI

### 16. Testing

**Smoke Tests Only**
- Basic API endpoint health checks
- Database connectivity
- Bedrock API connectivity
- Workflow execution (single article)

**No Requirements For**:
- Unit tests
- Integration tests
- E2E tests (Playwright)

### 17. Backup and Restore System

**Backup Types**

1. **Database-Only Backup**
   - PostgreSQL database dump (compressed with gzip)
   - Includes all tables: articles, sources, annotations, workflow executions, SIGMA rules, ML models, etc.
   - Metadata JSON file with backup stats (table counts, sizes, checksums)
   - Timestamped filenames: `cti_scraper_backup_YYYYMMDD_HHMMSS.sql.gz`
   - Fast (~1-2 minutes)

2. **Full System Backup**
   - Database dump (compressed)
   - ML models (`models/` directory)
   - Configuration files (`config/` directory)
   - Training data (`outputs/` directory)
   - Application logs (`logs/` directory)
   - Metadata JSON with component checksums
   - Timestamped directory: `system_backup_YYYYMMDD_HHMMSS/`
   - Slower (~5-10 minutes)

**Backup Features**
- Automatic compression (gzip, ~70-80% reduction)
- Checksum verification (SHA256)
- Pre-restore validation
- Optional pre-restore snapshots
- Component-based restore (selective restore)
- Dry-run mode for testing
- Backup listing and verification

**CLI Commands**
- `backup create` - Create full system backup
- `backup create --type database` - Database-only backup
- `backup list` - List available backups
- `backup restore <backup_name>` - Restore from backup
- `backup restore <backup_name> --components database,models` - Selective restore
- `backup verify <backup_name>` - Verify backup integrity

**Automated Backups**
- Optional scheduled backups (daily/weekly)
- Retention policies (keep N backups, prune old ones)
- Backup to S3 for off-site storage (cost consideration)

**Implementation Notes**
- Use `pg_dump` for PostgreSQL backups
- Store backups in S3 bucket (cost-optimized storage class)
- Include verification step after restore
- Support both CLI and web UI access

### 18. Exclusions

**DO NOT Include**:
- Evaluations pages (model comparison, benchmarking)
- LM Studio components (use AWS Bedrock instead)
- SimHash for near-duplicate detection (use content_hash only)
- RAG chat interface (pgvector still needed for SIGMA similarity)
- Docker/Docker Compose (cost-driven decision)
- User authentication (single user, secure network assumed)
- Data retention/cleanup policies (builder decides)

## Technical Stack Recommendations

**Backend**:
- Python 3.11+
- FastAPI (async web framework)
- SQLAlchemy (async ORM)
- LangGraph (workflow orchestration)
- boto3 (AWS SDK)
- scikit-learn (ML models)
- pgvector (PostgreSQL extension)

**Frontend**:
- Jinja2 templates
- Modern CSS (dark mode)
- JavaScript for interactivity (annotation selection, etc.)

**Infrastructure**:
- Terraform for IaC
- AWS services: RDS, ECS/Lambda, Bedrock, S3, CloudWatch
- PostgreSQL with pgvector extension

## Deliverables

1. **Complete source code** with all components
2. **Terraform configuration** for AWS infrastructure
3. **Database migration scripts** (Alembic or raw SQL)
4. **Backup/restore scripts** (CLI commands)
5. **README.md** with setup instructions
6. **Cost analysis document** explaining architecture decisions
7. **Smoke test suite** for basic validation

## Success Criteria

1. System collects articles from hardcoded sources (RSS + web scraping fallback)
2. Articles processed through hunt scoring and ML filtering
3. High-scoring articles trigger agentic workflow
4. Workflow generates SIGMA rules and checks similarity
5. Rules queued for human review
6. ML model can be retrained from annotations/feedback
7. Full web UI for all operations
8. Langfuse tracing integrated
9. **Total AWS costs < $100/month**
10. All infrastructure defined in Terraform
11. Backup and restore system functional (database + full system backups)

## Notes

- All architectural decisions must prioritize cost optimization
- Use AWS Bedrock instead of self-hosted models (LM Studio)
- Content filter is critical for cost reduction (20-80% savings)
- Langfuse is required for LLM observability
- Terraform is required for infrastructure
- Single user, no authentication needed
- Builder decides on content processing details based on functional requirements

