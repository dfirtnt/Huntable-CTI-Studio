# Changelog

All notable changes to CTI Scraper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0 "Kepler"] - 2025-11-04

### Added
- **Agentic Workflow System**: Complete LangGraph-based workflow orchestration for automated threat intelligence processing
  - **6-Step Automated Pipeline**: Junk Filter → LLM Ranking → Extract Agent → SIGMA Generation → Similarity Search → Queue Promotion
  - **LangGraph State Machine**: Stateful workflow execution with conditional routing and error handling
  - **Workflow Configuration**: Configurable thresholds (min_hunt_score, ranking_threshold, similarity_threshold, junk_filter_threshold)
  - **Execution Tracking**: Complete audit trail with `agentic_workflow_executions` table tracking status, steps, and results
  - **State Management**: TypedDict-based state management with intermediate results stored at each step
  - **Conditional Logic**: Smart routing based on LLM ranking scores (threshold-based continue/stop)
  - **LangFuse Integration**: Full observability and tracing for workflow execution and LLM calls
  - **Celery Integration**: Asynchronous workflow execution via Celery workers
  - **Workflow Trigger Service**: Automated triggering for high-scoring articles
  - **API Endpoints**: `/api/workflow/trigger`, `/api/workflow/executions`, `/api/workflow/config`
  - **Workflow UI**: Complete web interface for monitoring executions, configuring thresholds, and triggering workflows
  - **Extract Agent**: Specialized agent for extracting telemetry-aware attacker behaviors and observables
  - **Rank Agent**: LLM-based scoring agent for SIGMA huntability assessment
  - **Sigma Agent**: Automated SIGMA rule generation with validation and retry logic
  - **Similarity Integration**: Automatic similarity matching against existing SigmaHQ rules
  - **Queue Management**: Automatic promotion of unique rules to review queue
- **Agent Prompt Version Control**: Complete version control system for agent prompts with history tracking and rollback
  - Prompts are viewable and editable from workflow config page (`/workflow#config`)
  - Prompts start as read-only with Edit button to enable editing
  - Version history modal shows all previous versions with timestamps and change descriptions
  - Rollback functionality to restore any previous prompt version
  - Change descriptions optional field when saving prompt updates
  - Database table `agent_prompt_versions` tracks all prompt changes with workflow config version linking
  - API endpoints: `/api/workflow/config/prompts/{agent_name}/versions` (GET), `/api/workflow/config/prompts/{agent_name}/rollback` (POST)
- **Database Schema Migration**: Migration script to fix `agent_prompt_versions` table schema alignment with SQLAlchemy model
  - Renamed columns: `prompt_text` → `prompt`, `version_number` → `version`, `config_version_id` → `workflow_config_version`
  - Added missing `instructions` column for ExtractAgent instructions template support
  - Updated column types and indexes to match model expectations
- **RAG (Retrieval-Augmented Generation) System**: Complete conversational AI implementation
  - Multi-Provider LLM Integration: OpenAI GPT-4o, Anthropic Claude, and Ollama support
  - Conversational Context: Multi-turn conversation support with context memory
  - Synthesized Responses: LLM-generated analysis instead of raw article excerpts
  - Vector Embeddings: Sentence Transformers (all-mpnet-base-v2) for semantic similarity search
  - RAG Generation Service: `src/services/llm_generation_service.py` for response synthesis
  - Auto-Fallback System: Graceful degradation between LLM providers
  - RAG Chat API: `POST /api/chat/rag` endpoint with conversation history
  - Frontend RAG Controls: LLM provider selection and synthesis toggle
  - Professional System Prompt: Cybersecurity analyst persona for threat intelligence analysis
  - Source Attribution: All responses include relevance scores and source citations
  - RAG Documentation: Comprehensive RAG system documentation in `docs/RAG_SYSTEM.md`
- **Allure Reports Integration**: Rich visual test analytics with pie charts, bar charts, and trend graphs
  - Dedicated Allure Container: Containerized Allure Reports server for reliable access
  - Interactive Test Dashboard: Step-by-step test visualization for debugging and analysis
  - Enhanced Test Reporting: Comprehensive test execution reports with ML/AI debugging capabilities
  - Visual Test Tracking: Professional test reporting system for development and CI/CD pipelines
  - Allure Management Script: `./manage_allure.sh` for easy container management
- **Unified Testing Interface**: New `run_tests.py` and `run_tests.sh` for standardized test execution
  - Docker Testing Support: Added `--docker` flag for containerized test execution
  - Virtual Environment Documentation: Comprehensive guide for `venv-test`, `venv-lg`, and `venv-ml`
  - Testing Workflow Guide: Complete documentation for different execution contexts and test categories
- **Comprehensive Test Suite**: Fixed 5 high-priority test modules with 195 new passing tests
  - ContentFilter Tests: ML-based filtering, cost optimization, and quality scoring (25 tests)
  - SigmaValidator Tests: SIGMA rule validation, error handling, and batch processing (50 tests)
  - SourceManager Tests: Source configuration management and validation (35 tests)
  - ContentCleaner Tests: HTML cleaning, text processing, and metadata extraction (30 tests)
  - HTTPClient Tests: Rate limiting, async handling, and request configuration (38/39 tests)
  - Supporting Classes: FilterResult, FilterConfig, ValidationError, SigmaRule, SourceConfig, ContentExtractor, TextNormalizer, RateLimiter
  - Dependencies: Added scikit-learn and pandas for ML-based content filtering
  - Test Documentation: Updated SKIPPED_TESTS.md with current test status and progress tracking
  - Test Coverage: Dramatically improved from 27 to 222 passing tests (722% increase)
  - Test Infrastructure: Enhanced test reliability and maintainability with comprehensive supporting classes

### Changed
- **Workflow Config UI**: Enhanced agent prompts section with edit/view toggle and version history access
- **Prompt Update API**: Now saves version history automatically on each prompt update
- **Version History Modal**: Improved text readability with larger font sizes, better contrast, and enhanced formatting
  - Font size increased from `text-xs` to `text-sm`
  - Added borders and improved padding for better visual separation
  - Increased max height for better content visibility
  - Enhanced line spacing and word wrapping
- **RAG Architecture**: Upgraded from template-only to full LLM synthesis
- **API Response Format**: Enhanced with LLM provider and synthesis status
- **Frontend Configuration**: Added LLM provider selection and synthesis controls
- **Documentation**: Updated README, API endpoints, and Docker architecture docs

### Fixed
- **Database Schema Mismatch**: Fixed `agent_prompt_versions` table column names to match SQLAlchemy model
- **Version History Display**: Improved readability of prompt and instructions text in version history modal
- **Database Migration**: Created migration script `20250130_fix_agent_prompt_versions_schema.sql` for schema alignment
- **SIGMA Generation Quality Restoration**: Fixed deteriorated SIGMA rule generation that was producing malformed rules
  - Reverted uncommitted prompt simplification in `src/prompts/sigma_generation.txt` that removed critical guidance
  - Restored detailed SIGMA Rule Requirements and Rule Guidelines explaining separation of detection vs tags
  - Fixed LMStudio model configuration mismatch (1B → 8B model) in `.env` and `docker-compose.yml`
  - Implemented dynamic context window sizing based on model size (1B: 2.2K, 3B: 10.4K, 8B: 26.8K chars)
  - Optimized retry prompts to remove wasteful article content repetition (~500 token savings per retry)
  - Fixed issue where MITRE ATT&CK tags were incorrectly placed in detection/selection fields
  - Temperature correctly set to 0.2 for deterministic SIGMA YAML generation
- **OpenAI API Integration**: Proper API key handling and error fallback
- **Conversation Context**: Fixed context truncation and memory management
- **Response Quality**: Improved synthesis quality with professional formatting
- **Test Suite Reliability**: Fixed 5 major test modules with comprehensive supporting class implementations
- **ContentFilter Logic**: Fixed ML-based filtering, cost optimization, and quality scoring algorithms
- **SigmaValidator Logic**: Fixed rule validation, error handling, and batch processing
- **SourceManager Logic**: Fixed source configuration management and validation error handling
- **ContentCleaner Logic**: Fixed HTML cleaning, Unicode normalization, and text processing
- **HTTPClient Logic**: Fixed rate limiting, async/await issues, and request configuration

### Security
- None (security hardening was completed in previous versions)

### Removed
- **Redundant UI Cleanup**: Removed redundant "Save Configuration" button from settings page

### Technical Details
- **Database Migration**: PostgreSQL migration script updates table schema while preserving existing data
- **Version Control**: Each prompt update creates a new version linked to workflow config version
- **UI Improvements**: Enhanced modal display with better typography and spacing
- **Embedding Model**: all-mpnet-base-v2 (768-dimensional vectors)
- **Vector Storage**: PostgreSQL with pgvector extension
- **Context Management**: Last 4 conversation turns for LLM context
- **Response Times**: 3-5 seconds (OpenAI), 4-6 seconds (Claude), 10-30 seconds (Ollama)
- **Fallback Strategy**: Template → Ollama → Claude → OpenAI priority order
- **Workflow Architecture**: LangGraph state machine with PostgreSQL checkpointing
- **Agent System**: Extract Agent, Rank Agent, and Sigma Agent orchestrated via LangGraph
- **Observability**: LangFuse integration for workflow and LLM call tracing

## [3.0.0 "Copernicus"] - 2025-01-28

### Added
- **SIGMA Rule Similarity Search**: Advanced similarity matching between generated SIGMA rules and existing SigmaHQ rules
- **Weighted Hybrid Embeddings**: Enhanced embedding strategy combining title, description, tags, logsource, and detection logic
- **Interactive Similar Rules Modal**: UI modal showing similar SIGMA rules with coverage status (covered/extend/new)
- **Embed Article Button**: One-click embedding generation for articles with async Celery task processing
- **Coverage Classification**: Automatic classification of rule matches as "covered", "extend", or "new"
- **Article Embedding Status**: Real-time tracking of article embedding status with disabled button tooltips
- **Enhanced Sigma Generation**: Added MITRE ATT&CK technique extraction and tagging to SIGMA rule generation
- **PostgreSQL Vector Index**: Efficient vector similarity search using pgvector extension

### Changed
- **Embedding Model**: Enhanced to use all-mpnet-base-v2 (768-dimensional vectors)
- **Sigma Sync Service**: Updated to generate weighted hybrid embeddings for better semantic matching
- **Article Detail UI**: Enhanced modal with dynamic button states based on embedding status
- **Sigma Matching Service**: Improved similarity search with proper SQL parameter binding

### Fixed
- **SQL Syntax Errors**: Fixed mixing SQLAlchemy named parameters with psycopg2 format
- **PostgreSQL Index Size**: Removed B-tree index on embedding column exceeding size limits
- **Pydantic Model**: Added embedding, embedding_model, and embedded_at fields to Article model
- **NumPy Array Truth Value**: Fixed ambiguous truth value when checking embedding existence
- **Article Embedding API**: Proper handling of list-like embeddings with length validation

### Technical Details
- **Vector Similarity**: Cosine similarity with configurable threshold (default 0.7)
- **API Endpoints**: `/api/articles/{id}/embed`, `/api/sigma/matches/{article_id}`, `/api/generate-sigma`
- **Async Processing**: Celery workers for background embedding generation
- **Database**: Article and Sigma rule embeddings stored in PostgreSQL with pgvector

## [Unreleased]

### Fixed
- **SIGMA Generation Quality Restoration**: Fixed deteriorated SIGMA rule generation that was producing malformed rules
  - Reverted uncommitted prompt simplification in `src/prompts/sigma_generation.txt` that removed critical guidance
  - Restored detailed SIGMA Rule Requirements and Rule Guidelines explaining separation of detection vs tags
  - Fixed LMStudio model configuration mismatch (1B → 8B model) in `.env` and `docker-compose.yml`
  - Implemented dynamic context window sizing based on model size (1B: 2.2K, 3B: 10.4K, 8B: 26.8K chars)
  - Optimized retry prompts to remove wasteful article content repetition (~500 token savings per retry)
  - Fixed issue where MITRE ATT&CK tags were incorrectly placed in detection/selection fields
  - Temperature correctly set to 0.2 for deterministic SIGMA YAML generation

### Added
- **Full GitHub Hygiene Audit (LG)**: Comprehensive security and quality audit completed
- **Dependency Security**: All 269 dependencies audited with pip-audit - no CVE vulnerabilities found
- **Enhanced Security Posture**: Comprehensive .gitignore, secure env configuration, proper credential handling
- **RAG (Retrieval-Augmented Generation) System**: Complete conversational AI implementation
- **Multi-Provider LLM Integration**: OpenAI GPT-4o, Anthropic Claude, and Ollama support
- **Conversational Context**: Multi-turn conversation support with context memory
- **Synthesized Responses**: LLM-generated analysis instead of raw article excerpts
- **Vector Embeddings**: Sentence Transformers (all-mpnet-base-v2) for semantic similarity search
- **RAG Generation Service**: `src/services/llm_generation_service.py` for response synthesis
- **Auto-Fallback System**: Graceful degradation between LLM providers
- **RAG Chat API**: `POST /api/chat/rag` endpoint with conversation history
- **Frontend RAG Controls**: LLM provider selection and synthesis toggle
- **Professional System Prompt**: Cybersecurity analyst persona for threat intelligence analysis
- **Source Attribution**: All responses include relevance scores and source citations
- **RAG Documentation**: Comprehensive RAG system documentation in `docs/RAG_SYSTEM.md`

### Changed
- **RAG Architecture**: Upgraded from template-only to full LLM synthesis
- **API Response Format**: Enhanced with LLM provider and synthesis status
- **Frontend Configuration**: Added LLM provider selection and synthesis controls
- **Documentation**: Updated README, API endpoints, and Docker architecture docs

### Fixed
- **OpenAI API Integration**: Proper API key handling and error fallback
- **Conversation Context**: Fixed context truncation and memory management
- **Response Quality**: Improved synthesis quality with professional formatting

### Technical Details
- **Embedding Model**: all-mpnet-base-v2 (768-dimensional vectors)
- **Vector Storage**: PostgreSQL with pgvector extension
- **Context Management**: Last 4 conversation turns for LLM context
- **Response Times**: 3-5 seconds (OpenAI), 4-6 seconds (Claude), 10-30 seconds (Ollama)
- **Fallback Strategy**: Template → Ollama → Claude → OpenAI priority order

### Added
- **Allure Reports Integration**: Rich visual test analytics with pie charts, bar charts, and trend graphs
- **Dedicated Allure Container**: Containerized Allure Reports server for reliable access
- **Interactive Test Dashboard**: Step-by-step test visualization for debugging and analysis
- **Enhanced Test Reporting**: Comprehensive test execution reports with ML/AI debugging capabilities
- **Visual Test Tracking**: Professional test reporting system for development and CI/CD pipelines
- **Allure Management Script**: `./manage_allure.sh` for easy container management
- **Database-Based Training System**: Refactored ML training from CSV to PostgreSQL database storage
- **Chunk Classification Feedback Table**: New database table for storing user feedback on ML predictions
- **Auto-Expand Annotation UI**: Automatic 1000-character text selection for optimal training data
- **Length Validation**: Frontend and backend validation for 950-1050 character annotations
- **Training Data Migration**: Script to migrate existing CSV feedback to database
- **Enhanced API Endpoints**: Updated retraining API with database integration and proper version tracking
- **Usage Tracking**: `used_for_training` flag to prevent duplicate data usage
- **Real-Time Feedback Count**: API endpoint showing available training samples from database

### Changed
- **Training Data Source**: Now uses database tables instead of CSV files
- **Annotation Requirements**: Enforces 950-1050 character length for training data quality
- **Retraining Workflow**: Synchronous execution with complete results returned
- **Model Version Display**: Shows proper version numbers and training sample counts
- **Error Handling**: Improved error messages for missing training data

### Fixed
- **JavaScript Infinite Loops**: Fixed auto-expand functionality causing repeated errors
- **Modal Recreation Issues**: Prevented infinite loops in annotation modal updates
- **API Response Format**: Consistent response structure for retraining endpoints
- **Training Sample Counting**: Accurate count of available feedback and annotations
- **Version Information Display**: Proper model version and accuracy reporting

### Technical Details
- **Database Schema**: Added `chunk_classification_feedback` table with proper indexes
- **API Updates**: Modified `/api/model/retrain` and `/api/model/feedback-count` endpoints
- **UI Improvements**: Streamlined annotation modal without manual adjustment controls
- **Test Updates**: Updated unit tests for database-based training system
- **Documentation**: Added comprehensive database training system documentation

### Added
- **Chunk Deduplication System**: Database unique constraint prevents duplicate chunk storage
- **Chunk Analysis Tests**: Comprehensive test suite verifying deduplication and data integrity
- **ML-Powered Content Filtering**: Machine learning model for automated chunk classification with RandomForest
- **Interactive Feedback System**: User feedback collection for continuous model improvement and retraining
- **Model Versioning System**: Track model performance changes with database-backed version history
- **Confidence Tracking**: Huntable probability tracking for consistent before/after comparisons
- **Model Comparison Interface**: Visual comparison of model versions showing confidence improvements
- **Feedback Impact Analysis**: Modal showing how user feedback improved model confidence on specific chunks
- **Automated Model Retraining**: One-click model retraining with user feedback integration
- **ML Feedback API Endpoints**: RESTful APIs for model versioning, comparison, and feedback analysis
- **Essential Regression Tests**: 3 critical tests for ML feedback features to prevent breakage
- **Automated Backup System**: Daily backup scheduling with cron jobs (2:00 AM daily, 3:00 AM weekly cleanup)
- **Backup Retention Policy**: 7 daily + 4 weekly + 3 monthly backups with 50GB max size limit
- **Intelligent Backup Detection**: API automatically detects automated backups by analyzing backup frequency
- **Backup System Integration**: Fixed database backup integration using existing backup_database_v3.py
- **Backup Verification**: Added comprehensive backup testing with test database restore validation
- **Security Hardening**: Removed hardcoded credentials and moved to environment variables
- **Enhanced .gitignore**: Added comprehensive .gitignore with Docker and security exclusions
- **Environment Variables**: Updated docker-compose.yml to use environment variables for credentials
- **Backup Status API**: Fixed backup status parsing to show accurate size and last backup information
- **Redundant UI Cleanup**: Removed redundant "Save Configuration" button from settings page

### Fixed
- **Chunk Analysis Duplicates**: Fixed bug where chunks were stored twice (duplicate entries) for same article/model
- **ML Prediction Optimization**: Eliminated redundant `predict_huntability()` calls (50% reduction from 2x to 1x per chunk)
- **List Backups API**: Fixed parsing to show all numbered backups (1-10) instead of just the first one
- **Backup List Display**: Corrected multi-line backup entry parsing to extract names and sizes properly
- **Database Backup**: Fixed database backup to include actual data (1,187 articles, 35 sources)
- **Backup Size Display**: Corrected backup size display from 29.9 GB to actual 0.03 GB
- **Volume Mount**: Added scripts volume mount to Docker web container
- **API Arguments**: Removed invalid --type argument from backup API calls
- **Status Parsing**: Fixed backup status parsing to extract correct backup names and sizes
- **Container Permissions**: Resolved Docker socket permission issues for backup operations

### Security
- **Credential Removal**: Removed hardcoded passwords from docker-compose.yml and backup scripts
- **Environment Variables**: All sensitive configuration now uses environment variables
- **Security Scanning**: Comprehensive security audit with no critical vulnerabilities found
- **Dependency Updates**: All dependencies verified secure with latest versions
- **Threshold Selector**: Added confidence threshold slider to Chunk Debug modal with 3 preset levels (0.5, 0.7, 0.8)
- **Real-time Threshold Updates**: Implemented dynamic threshold changes with immediate API calls and UI updates
- **User Feedback System**: Added feedback mechanism to Chunk Debug modal for ML model improvement
- **Model Retraining**: Added retraining button to update ML model using collected user feedback
- **Enhanced Statistics Cards**: Added unique IDs to statistics cards for reliable real-time updates
- **Dynamic Chunk Visualization**: Updated chunk visualization to reflect threshold changes in real-time
- **Article Detail Page Readability**: Enhanced article content readability with black text for maximum contrast
- **Dark Mode Support**: Improved dark mode support for keyword highlights and user annotations
- **Enhanced Annotation System**: Updated JavaScript annotation classes for consistent dark mode styling
- **LLM Integration**: Added LLM integration with template fallback for RAG chat responses
- **Ollama Parallelism**: Increased Ollama parallelism to handle multiple concurrent AI endpoints

### Changed
- **Chunk Debug Modal**: Enhanced with threshold selector, real-time updates, and user feedback system
- **ML Model Integration**: Improved model loading and retraining capabilities with user feedback
- **Statistics Display**: Fixed statistics cards to update dynamically with threshold changes
- **Chunk Visualization**: Updated to reflect threshold changes in real-time
- **Keyword Highlighting**: Updated `highlight_keywords` filter to support dark mode with proper contrast
- **User Annotations**: Enhanced annotation spans with dark mode classes for better visibility
- **Content Display**: Improved article content text contrast and readability across themes
- **Chat Interface**: Updated UI message from "LLM disabled" to "AI-powered responses enabled"
- **Ollama Configuration**: Increased `OLLAMA_NUM_PARALLEL` from 1 to 3 and `OLLAMA_MAX_LOADED_MODELS` from 1 to 2

### Fixed
- **Statistics Cards**: Fixed statistics cards not updating when threshold slider changes
- **Chunk Visualization**: Fixed chunk visualization not reflecting threshold changes
- **Threshold Selector**: Fixed null reference errors in threshold update functions
- **Readability Issues**: Resolved low contrast issues in article detail page content display
- **Dark Mode Compatibility**: Fixed keyword highlights and annotations to work properly in dark mode
- **Visual Consistency**: Ensured consistent styling across light and dark themes
- **LLM Resource Contention**: Fixed Ollama timeout issues caused by multiple AI endpoints competing for resources
- **Chat Interface Status**: Removed hardcoded "LLM disabled" message and implemented proper status display

## [Previous Releases]
- **SIGMA Conversation Log**: Enhanced SIGMA rule generation UI to display the full back-and-forth conversation between LLM and pySigma validator
  - Shows each attempt with prompts, LLM responses, and validation results
  - Collapsible sections for long content to improve readability
  - Color-coded validation feedback (green for valid, red for invalid)
  - Visual indicators for retry attempts vs. final attempt
  - Detailed error and warning messages from pySigma validator
- **Unified Testing Interface**: New `run_tests.py` and `run_tests.sh` for standardized test execution
- **Docker Testing Support**: Added `--docker` flag for containerized test execution
- **Virtual Environment Documentation**: Comprehensive guide for `venv-test`, `venv-lg`, and `venv-ml`
- **Testing Workflow Guide**: Complete documentation for different execution contexts and test categories
- **Comprehensive Test Suite**: Fixed 5 high-priority test modules with 195 new passing tests
- **ContentFilter Tests**: ML-based filtering, cost optimization, and quality scoring (25 tests)
- **SigmaValidator Tests**: SIGMA rule validation, error handling, and batch processing (50 tests)
- **SourceManager Tests**: Source configuration management and validation (35 tests)
- **ContentCleaner Tests**: HTML cleaning, text processing, and metadata extraction (30 tests)
- **HTTPClient Tests**: Rate limiting, async handling, and request configuration (38/39 tests)
- **Supporting Classes**: FilterResult, FilterConfig, ValidationError, SigmaRule, SourceConfig, ContentExtractor, TextNormalizer, RateLimiter
- **Dependencies**: Added scikit-learn and pandas for ML-based content filtering
- **Test Documentation**: Updated SKIPPED_TESTS.md with current test status and progress tracking

### Removed
- **Vestigial Fields**: Removed unused `tier` and `weight` fields from source management (all sources had identical default values, no logic utilized these fields)

### Added (Previous)
- **Source Config Workspace**: Interactive tab for editing source metadata, filtering, crawlers, and selectors with local regex testing
- **SIGMA Rule Generation**: AI-powered detection rule generation from threat intelligence articles
- **pySIGMA Validation**: Automatic validation of generated SIGMA rules for compliance
- **Iterative Rule Fixing**: Automatic retry mechanism with error feedback (up to 3 attempts)
- **Rule Metadata Storage**: Complete audit trail of generation attempts and validation results
- **Source Management Enhancements**: Individual source refresh and check frequency configuration
- **CISA Analysis Reports**: New threat intelligence source for CISA cybersecurity advisories
- **Group-IB Threat Intelligence**: Content-filtered source for threat intelligence research
- **Non-English Word Analysis**: Advanced keyword analysis for threat hunting discriminators
- **Enhanced Keyword Lists**: Updated perfect and good discriminators based on analysis
- **Performance Optimizations**: Faster LLM model (Phi-3 Mini) for database queries
- GitHub Actions CI/CD pipeline with security scanning
- Comprehensive security policy and contributing guidelines
- Enhanced .gitignore with security-focused patterns
- Environment variable configuration template
- Automated dependency vulnerability scanning

### Changed
- **Test Coverage**: Dramatically improved from 27 to 222 passing tests (722% increase)
- **Test Infrastructure**: Enhanced test reliability and maintainability with comprehensive supporting classes
- **Database Chatbot**: Switched from Mistral 7B to Phi-3 Mini for faster query processing
- **Keyword Scoring**: Enhanced threat hunting discriminators based on non-English word analysis
- **Source Configuration**: Improved content filtering and threat intelligence focus
- Updated all dependencies to latest secure versions
- Removed hardcoded credentials from configuration
- Improved code documentation and type hints
- Enhanced security practices and guidelines

### Fixed
- **Test Suite Reliability**: Fixed 5 major test modules with comprehensive supporting class implementations
- **ContentFilter Logic**: Fixed ML-based filtering, cost optimization, and quality scoring algorithms
- **SigmaValidator Logic**: Fixed rule validation, error handling, and batch processing
- **SourceManager Logic**: Fixed source configuration management and validation error handling
- **ContentCleaner Logic**: Fixed HTML cleaning, Unicode normalization, and text processing
- **HTTPClient Logic**: Fixed rate limiting, async/await issues, and request configuration
- **Iteration Counter Bug**: Fixed off-by-one error in SIGMA rule generation attempt counting
- **SQL Query Safety**: Enhanced query validation and safety checks
- **Content Filtering**: Improved non-English word detection and filtering
- **Documentation Accuracy**: Fixed README.md to accurately reflect disabled readability scoring feature
- Fixed potential SQL injection vulnerabilities
- Updated cryptography library to latest version
- Removed debug prints and sensitive TODOs
- Implemented proper environment variable handling

### Security
- Enhanced input validation for SIGMA rule generation
- Improved query safety validation for database chatbot
- Updated cryptography library to latest version
- Removed debug prints and sensitive TODOs
- Implemented proper environment variable handling

## [2.0.0 "Tycho"] - 2025-01-15

### Added
- **PostgreSQL Database**: Replaced SQLite with production-grade PostgreSQL
- **Async/Await Support**: Full async support with FastAPI and SQLAlchemy
- **Connection Pooling**: Efficient database connection management
- **Background Tasks**: Celery worker system for async operations
- **Redis Caching**: High-performance caching and message queuing
- **Docker Containerization**: Production-ready container orchestration
- **Content Quality Assessment**: LLM-based quality scoring system
- **TTP Extraction Engine**: Advanced threat technique detection
- **Modern Web Interface**: HTMX-powered dynamic UI

### Changed
- **Architecture**: Complete rewrite with modern async architecture
- **Performance**: 10x improvement in concurrent operations
- **Scalability**: Horizontal scaling support
- **Security**: Enhanced security features and practices
- **Monitoring**: Built-in health checks and metrics

### Deprecated
- SQLite database support
- Old CLI interface
- Legacy web interface

### Removed
- Old architecture components
- Deprecated APIs and endpoints
- Legacy configuration formats

### Fixed
- Database locking issues
- Memory leaks in long-running processes
- Connection timeout problems
- Rate limiting inconsistencies

### Security
- Input validation for all endpoints
- SQL injection protection
- XSS protection
- Rate limiting implementation
- CORS configuration
- Environment variable configuration

## [1.2.3] - 2024-12-10

### Fixed
- SQL injection vulnerability in search functionality
- Memory leak in RSS parsing
- Connection timeout issues
- Rate limiting bypass

### Security
- Updated dependencies with security patches
- Enhanced input validation
- Improved error handling

## [1.2.2] - 2024-11-25

### Added
- Enhanced logging system
- Better error reporting
- Configuration validation

### Fixed
- RSS feed parsing issues
- Database connection problems
- Memory usage optimization

## [1.2.1] - 2024-11-15

### Added
- Content deduplication
- Source health monitoring
- Basic web interface

### Changed
- Improved RSS parsing accuracy
- Better error handling
- Enhanced logging

### Fixed
- Memory leaks in content processing
- Database connection issues
- File handling problems

## [1.2.0] - 2024-10-30

### Added
- RSS feed support
- Content extraction
- Basic database storage
- CLI interface

### Changed
- Improved content parsing
- Better source management
- Enhanced error handling

## [1.1.0] - 2024-09-15

### Added
- Basic web scraping functionality
- Source configuration
- Simple data storage

### Changed
- Improved performance
- Better error handling

## [1.0.0] - 2024-08-01

### Added
- Initial release
- Basic web scraping
- Simple data collection
- Basic CLI interface

---

## Migration Guides

### Upgrading from 1.x to 2.0

1. **Database Migration**: Export data from SQLite and import to PostgreSQL
2. **Configuration**: Update to new environment variable format
3. **Dependencies**: Install new requirements
4. **Docker**: Use new docker-compose configuration

### Upgrading from 1.1 to 1.2

1. **Database**: Backup existing data
2. **Configuration**: Update RSS feed configurations
3. **Dependencies**: Update to latest versions

---

## Release Notes

### Version 2.0.0
This is a major release with significant architectural improvements. The new async architecture provides better performance, scalability, and reliability. The addition of PostgreSQL, Redis, and Docker makes CTI Scraper production-ready.

### Version 1.2.3
Security-focused release addressing critical vulnerabilities and improving overall stability.

### Version 1.0.0
Initial release with basic functionality for web scraping and data collection.

---

## Support

For support and questions:
- **Issues**: GitHub issue tracker
- **Documentation**: Project README and docs
- **Security**: See SECURITY.md for security issues

---

**Note**: This changelog follows the Keep a Changelog format. All dates are in YYYY-MM-DD format.
