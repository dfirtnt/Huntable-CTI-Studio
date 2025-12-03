# Changelog

All notable changes to CTI Scraper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Distilled Model Detection Modal**: Added Distilled Model Detection feature to AI/ML Assistant
  - Comprehensive modal explaining DistilBERT-style model approach for commandline detection
  - Overview of 10-30× faster inference compared to LLM-based extraction
  - Architecture options (sentence-level vs token-level classification)
  - Inference pipeline documentation and benefits
  - Placeholder functions for test detection and training guide
  - Dark mode support with responsive layout
- **DistilBERT Commandline Detection Test Script**: Created test script for evaluating DistilBERT models
  - `utils/temp/test_distilbert_cmdline_detection.py` - Tests DistilBERT/CTI-BERT for Windows commandline detection
  - Supports NER-based and pattern-matching fallback approaches
  - Can compare against eval dataset for precision/recall/F1 metrics
  - Configurable model selection and article filtering
- **OS Detection Agent OS Selection**: Added OS selection checkboxes to OS Detection Agent configuration
  - Options: Windows, Linux, MacOS, Network, Other, All
  - Windows enabled by default; other options disabled (stub implementation)
  - Selections stored in `agent_models.OSDetectionAgent_selected_os` array
  - Auto-saves when OS selection changes
- **QA Max Retries Configuration**: Added `qa_max_retries` field to workflow configuration
  - Configurable maximum QA retry attempts (1-20, default: 5)
  - Added database migration script `scripts/migrate_add_qa_max_retries.sh`
  - UI field in QA Settings panel on workflow config page

### Fixed
- **Web Application Startup**: Fixed ImportError preventing application startup
  - Removed non-existent `test_scrape` import from route registration
  - Restored missing `dashboard.html.orig` template from git history
  - Dashboard page now loads correctly at root URL
- **Evaluation DB connections**: Cached synchronous DB engine/session to prevent opening new pools on each request and exhausting Postgres connections when visiting evaluation pages
- **Database Migration**: Fixed missing `qa_max_retries` column in `agentic_workflow_config` table
  - Created migration to add column with default value of 5
  - Resolved SQL errors when querying workflow configuration

### Added
- **File Organization Structure**: Implemented standardized file organization for temporary scripts, reports, and utilities
  - Created directory structure: `utils/temp/` (temporary scripts), `scripts/` (reusable utilities), `outputs/` (reports/exports/benchmarks)
  - Moved 84 temporary scripts from root level to appropriate directories
  - Updated `.gitignore` to properly handle temporary files while tracking `utils/temp/` scripts
  - Added file organization guidelines to `CONTRIBUTING.md` and `AGENTS.md`
  - Organized scripts by purpose: `scripts/maintenance/` (fix scripts), `scripts/testing/`, `scripts/analysis/`

### Fixed
- **Documentation: LangGraph Debug Button Behavior**: Corrected documentation to accurately reflect debug button functionality
  - Fixed `docs/LANGGRAPH_INTEGRATION.md` and `docs/LANGGRAPH_QUICKSTART.md` to state that debug button opens LangFuse traces (post-execution viewing), not Agent Chat UI
  - Clarified that step-into debugging requires manual setup with LangSmith Studio or Local Agent Chat UI
  - Updated API response example to show actual LangFuse trace URL format
  - Added notes about trace availability (only exists if execution ran with LangFuse tracing enabled)
- **Browser Extension Manual Source Creation**: Fixed duplicate key violations when creating manual source from browser extension
  - Changed manual source lookup from name-based (`LIKE '%manual%'`) to identifier-based (`identifier='manual'`) to match unique constraint
  - Implemented atomic `INSERT ... ON CONFLICT DO NOTHING` pattern using PostgreSQL's native upsert for race condition handling
  - Added proper `IntegrityError` handling for both identifier conflicts and primary key sequence issues
  - Fixed missing required database fields (`consecutive_failures`, `total_articles`, `average_response_time`, `created_at`, `updated_at`) in manual source creation
  - Added retry logic with fresh session queries to handle concurrent requests
  - Applied same fix to PDF upload endpoint for consistency
  - Fixed PostgreSQL sequence sync issue that was causing primary key conflicts

### Added
- **LMStudio Context Window Command Generator**: Added button on workflow config page to generate terminal commands for setting context windows
  - Collects all selected LLM models from workflow configuration
  - Excludes BERT and text encoder models (embedding models)
  - Generates commands using `scripts/set_lmstudio_context.sh` script
  - Includes unload command to clear existing models before loading
  - Commands displayed in modal with copy-to-clipboard functionality
  - Configurable context length (default: 16384 tokens)

### Fixed
- **Disabled Sub-Agents Execution**: Fixed issue where disabled sub-agents were still being executed
  - Added disabled agents check to `langgraph_server.py` workflow execution path
  - Fixed duplicate try block that was preventing disabled check from working
  - Disabled agents now properly skipped with empty results instead of executing
  - Added comprehensive logging to track disabled agent configuration reading
- **LMStudio Context Limits**: Context command generator now respects model-specific limits and disabled agents
  - Skips disabled sub-agent models when generating commands
  - Caps to LMStudio-reported limits when present
  - Manual cap added for `meta-llama-3-8b-instruct` (8192 tokens)
- **Workflow Config UI Improvements**:
  - Made all agent prompts collapsible and collapsed by default on workflow config page
  - Fixed model display mismatch where dropdown selection didn't match prompt display
  - Prompts now read current model from dropdown instead of cached config value
  - Model updates immediately refresh prompt displays
- **LMStudio Context Script**: Updated `set_lmstudio_context.sh` to only unload specific model being loaded
  - Prevents unloading all models when loading multiple models sequentially
  - Checks if model is already loaded and unloads only that specific instance
  - Handles model identifiers with suffixes (e.g., `:2`, `:3`) correctly
  - Allows multiple models to remain loaded simultaneously
- **QA Agent Toggle Logic**: QA Agents can no longer be enabled when their corresponding subagent is disabled
  - Added `updateQAStateForSubagent()` function to sync QA checkbox state with subagent enabled status
  - QA checkboxes are automatically disabled and unchecked when subagent is disabled
  - Visual feedback added with opacity and cursor styling for disabled QA toggles
  - Logic applies on page load, config sync, and manual toggle changes

### Added
- **Comprehensive UI Test Coverage**: Added 17 new comprehensive UI test files covering all major pages (544 tests total)
  - `test_workflow_comprehensive_ui.py`: 89 tests for workflow configuration, executions, and queue management
  - `test_articles_advanced_ui.py`: 74 tests for advanced search, filtering, sorting, pagination, bulk actions, and classification modal
  - `test_article_detail_advanced_ui.py`: 21 tests for article detail page features
  - `test_analytics_comprehensive_ui.py`: 47 tests for analytics pages (main, scraper metrics, hunt metrics)
  - `test_sources_comprehensive_ui.py`: 39 tests for source management, configuration, and adhoc scraping
  - `test_settings_comprehensive_ui.py`: 39 tests for backup, AI/ML config, API config, and data export
  - `test_chat_comprehensive_ui.py`: 57 tests for RAG chat interface, message display, article/rule results, YAML modal
  - `test_dashboard_comprehensive_ui.py`: 37 tests for dashboard widgets, charts, and quick actions
  - `test_pdf_upload_advanced_ui.py`: 19 tests for PDF upload functionality
  - `test_health_checks_advanced_ui.py`: 20 tests for health check monitoring
  - `test_diagnostics_advanced_ui.py`: 21 tests for system diagnostics page
  - `test_jobs_advanced_ui.py`: 19 tests for job monitoring
  - `test_cross_page_navigation_ui.py`: 15 tests for navigation and deep linking
  - `test_error_handling_comprehensive_ui.py`: 16 tests for error scenarios
  - `test_accessibility_comprehensive_ui.py`: 22 tests for keyboard navigation, ARIA, and screen reader compatibility
  - `test_performance_comprehensive_ui.py`: 18 tests for page load and rendering performance
  - `test_mobile_responsiveness_ui.py`: 30 tests for mobile layout and touch interactions
  - All tests integrated into pytest suite and run via `run_tests.py ui` wrapper
  - Tests follow existing patterns and use Playwright with pytest fixtures
- **Subagent Evaluation Pages**: Added dedicated evaluation pages for ExtractAgent subagents
  - Created subagent evaluation pages at `/evaluations/ExtractAgent/{subagent_name}` for CmdlineExtract, SigExtract, EventCodeExtract, ProcTreeExtract, and RegExtract
  - Added subagent links section on ExtractAgent evaluation page with cards for each subagent
  - Subagent pages show purpose, evaluation history, and link back to parent agent
- **SIGMA Test Pages Navigation**: Moved SIGMA A/B Test and SIGMA Similarity Test links from main navigation to Evaluations page
  - Links now appear as cards on the Evaluations page alongside agent evaluation cards
  - Removed from main navigation bar for cleaner interface
- **Generator Error Handling**: Enhanced Langfuse trace cleanup to suppress generator protocol errors
  - Generator errors during Langfuse cleanup no longer fail workflows
  - Added comprehensive error suppression in trace context managers
  - Generator errors are logged as warnings but don't propagate as workflow failures
- **LMStudio Error Message Formatting**: Improved error message display for context length issues
  - Context length errors now show formatted messages instead of raw JSON
  - Error detection distinguishes between genuine "busy" conditions and other errors
  - Better user experience with actionable error messages
- **Playwright Test for Error Messages**: Added test to verify error message formatting
  - Tests verify formatted error messages are displayed correctly
  - Ensures "busy" errors don't appear for context length issues

- **Workflow Executions observability toggle**: Added toggle for showing extract observable counts in the executions table
  - Execution API now exposes an `extraction_counts` map populated from `extraction_result.subresults` or the merged observable list, covering Cmdline, ProcTree, Reg, Signature, and EventID sub-agents
  - The toggle inserts CmdLine#/ProcTree#/Reg#/Signature#/EventID# columns immediately after the ranking score so teams can quickly see which telemetry families produced observables

### Fixed
- **ML Comparison Chart Enhancements**: Added zoom and scroll controls for evaluation metrics chart
  - Horizontal scrolling to view all model version history
  - Zoom in/out controls with preset levels (5, 10, 15, 20, 30, 50, all versions)
  - Fixed legend and chart title remain centered during scroll/zoom operations
  - Default view shows latest models with ability to scroll left for history
- **Enhanced Backup/Restore Verification**: Comprehensive verification for critical configuration data
  - Backup metadata now tracks ML model versions, agent configs, and source configurations
  - Restore verification checks all critical tables (ml_model_versions, agentic_workflow_config, agent_prompt_versions, app_settings, sources, source_checks)
  - Verification compares restored counts against backup metadata for data integrity confirmation
  - Added documentation for source configuration precedence (database vs. YAML)
- **Source Configuration Precedence**: Database values now take precedence over sources.yaml after initial setup
  - Application only syncs from sources.yaml for brand new builds (< 5 sources)
  - Restored database configurations are preserved and not overwritten by sources.yaml on container rebuilds
  - Added DISABLE_SOURCE_AUTO_SYNC environment variable to disable YAML sync entirely
  - Database is authoritative source for source settings (active status, lookback_days, check_frequency) after initial setup

### Fixed
- **Generator Errors Failing Workflows**: Fixed "generator didn't stop after throw()" errors causing workflow failures
  - Generator errors from Langfuse cleanup are now suppressed and logged as warnings
  - Workflows complete successfully even when Langfuse trace cleanup encounters generator protocol issues
  - Fixed error handling in ranking node to detect and suppress generator errors
- **LMStudio "Busy" False Positives**: Fixed incorrect "busy" error detection for context length issues
  - Error detection now distinguishes between genuine connection failures and context length errors
  - Context length errors show appropriate error messages instead of misleading "busy" messages
  - Improved error detection logic to check for chained exceptions and prioritize original errors
- **Context Length Configuration**: Fixed context length mismatch causing 400 errors
  - Updated LMStudio context length override from 16384 to 4096 to match actual configured value
  - Content truncation now works correctly with actual context length
  - Ranking tests now succeed without context length errors
- **Test Article IDs**: Updated all test buttons to use article 2155 instead of 1427
  - RankAgent test button updated
  - All sub-agent test buttons (CmdlineExtract, SigExtract, EventCodeExtract, ProcTreeExtract, RegExtract) updated
  - Playwright test updated to use article 2155
- **OS Detection Display Logic**: Fixed workflow continuation display when OS is detected as Windows
  - UI now correctly shows "Continue" when Windows is detected even if initial detection was "Unknown"
  - Fixed OS detection threshold logic to use 50% similarity with clear winner detection
  - Workflow state correctly reflects continuation decision
- **Redis Validation Blocking Smoke Tests**: Made Redis validation non-blocking for smoke tests
  - Smoke tests now execute even if Redis connection fails
  - Redis validation failures logged as warnings but don't block test execution
  - Fixed smoke test path to use `tests/smoke/` directory instead of marker-based discovery
- **IndentationError in ContentFilter**: Fixed critical syntax error preventing web service startup
  - Corrected indentation of sklearn imports in try/except block
  - Web container now starts successfully and serves requests
- **Workflow Configuration Section Order**: Reordered configuration panels to match workflow execution
  - OS Detection Agent panel now appears before Junk Filter panel
  - UI order now matches actual workflow step sequence (Step 0: OS Detection → Step 1: Junk Filter)
- **Workflow Order in Configuration UI**: Fixed workflow overview to show correct 7-step order
  - Added OS Detection as Step 0 (was missing)
  - Renumbered all subsequent steps: Junk Filter (1), LLM Ranking (2), Extract Agent (3), Generate SIGMA (4), Similarity Search (5), Queue (6)
  - Updated step count from 6 to 7 steps in description
  - Workflow execution order matches UI display
- **Duplicate Placeholder Options in Model Selectors**: Fixed duplicate placeholder options in all agent model selector dropdowns
  - Removed hardcoded placeholder options that conflicted with `buildOptions()` function
  - Fixed Rank Agent model selector duplicate placeholder
  - Fixed all 6 QA model selectors (Rank QA, CmdLine QA, Sig QA, EventCode QA, ProcTree QA, Reg QA)
  - All dropdowns now display single placeholder option correctly
- **Duplicate Model Entries in Dropdowns**: Fixed duplicate model entries (e.g., "Mistral7" and "Mistral7:2") in all model selector dropdowns
  - Added normalization to remove numbered suffixes (`:2`, `:3`, etc.) from model IDs
  - Deduplication now prefers base model names (without suffix) over numbered instances
  - Applied to all dropdowns: Rank Agent, Extract Agent, Sigma Agent, OS Detection fallback, all sub-agents, and all QA model selectors
- **LLMService Context Length Detection**: Improved context length handling to trust detected values when reasonable
  - Now uses model-specific context limits based on model size (1B: 2048, 3B: 4096, 7B/8B: 8192, 13B/14B: 16384, 32B: 32768)
  - Trusts detected context when between 4096 and model max (with 10% safety margin)
  - Only uses very conservative caps when detection is unreliable or too small
  - Respects environment variable overrides completely
  - Fixes issue where models loaded with 16384 context were only using 1536 tokens
  - Added Playwright tests to verify no duplicate models appear in dropdowns
- **LLMService Context Length NameError**: Fixed `NameError: name 'MAX_SAFE_CONTEXT_NORMAL' is not defined` in Rank Agent testing
  - Removed all references to `MAX_SAFE_CONTEXT_NORMAL` and `MAX_SAFE_CONTEXT_REASONING` constants
  - Updated `rank_article`, `extract_behaviors`, and `extract_observables` methods to use consistent model-specific context detection
  - Fixed logger statements to use new context detection variables
  - All methods now use the same improved context length logic

### Added
- **Help Circles for All Agents**: Contextual help buttons with detailed information for all agent and sub-agent model selectors
  - Help circles added to Rank Agent, Extract Agent, SIGMA Agent, and OS Detection Agent model selectors
  - Help circles added to all sub-agents: CmdlineExtract, SigExtract, EventCodeExtract, ProcTreeExtract, RegExtract
  - Comprehensive help text explaining each agent's purpose, configuration options, and recommendations
  - Consistent help UI pattern matching Junk Filter Threshold help button
- **OS Detection Fallback Model Toggle**: Added toggle button to enable/disable fallback model selection for OS Detection Agent
  - Toggle switch positioned next to "Fallback Model (Optional)" label
  - When disabled, fallback model dropdown is disabled and value is cleared
  - When enabled, user can select a custom fallback LLM model
  - Toggle state persists with workflow configuration
  - Matches existing toggle UI pattern used for QA agents
- **Workflow Model Loader**: Added `utils/load_workflow_models.py` utility script
  - Reads active workflow configuration from database
  - Loads all configured models with 16384 context tokens
  - Verifies each model can be loaded before workflow execution
  - Helps prevent context length errors in production workflows
- **Workflow Context Fix Documentation**: Added `docs/WORKFLOW_CONTEXT_FIX.md`
  - Troubleshooting guide for context length errors
  - Instructions for loading models with proper context
  - Prevention strategies and troubleshooting tips

### Changed
- **Test Wrapper Configuration**: Updated test runner to exclude infrastructure and production data tests by default
  - `run_tests.py` now automatically excludes `infrastructure`, `prod_data`, and `production_data` markers
  - `conftest.py` auto-skips infrastructure and production data tests during collection
  - Added `prod_data` and `production_data` markers to `pytest.ini`
  - Tests requiring test infrastructure or production data access are now skipped automatically
- **Workflow Configuration UI Reorganization**: Improved organization and accessibility of workflow configuration
  - Converted "Other Thresholds" section to collapsible "Junk Filter" dropdown panel at top of configuration
  - Moved Similarity Threshold from "Other Thresholds" to SIGMA Agent panel (under SIGMA Agent model selector)
  - Moved QA model selectors from Extract Agent panel to their respective sub-agent panels:
    * CmdLine QA Model → CmdlineExtract sub-agent panel
    * Sig QA Model → SigExtract sub-agent panel
    * EventCode QA Model → EventCodeExtract sub-agent panel
    * ProcTree QA Model → ProcTreeExtract sub-agent panel
    * Reg QA Model → RegExtract sub-agent panel
  - Improved UI consistency with agent panel collapsible pattern
- **Source health checks**: `check_all_sources` now uses the hierarchical `ContentFetcher` (RSS → modern scraping → legacy) with safer bookkeeping for articles/errors, improving health metrics and logging across all sources.
- **Source scraping configs**: Updated selectors and discovery for Assetnote Research (verified RSS URL and Webflow containers), Picus Security Blog (HubSpot body selectors), and Splunk Security Blog (AEM containers) to improve extraction coverage.

### Current Status & Next Steps
- Assetnote, Picus, and Splunk remain failing due to JS-rendered/anti-bot content; selectors are in place but static fetch still returns empty. Next steps: add headless/JS-capable fetch (Playwright) or alternative article API path; retest and adjust min_content_length as needed.
- Group-IB, NCSC UK, MSRC: still blocked (403/SPA/placeholder feeds). Next steps: investigate API/back-end endpoints or headless rendering; consider temporary deactivation if access remains blocked.

### Removed
- **OS Detection QA Agent**: Removed QA validation system for OS Detection Agent
  - Removed QA retry loop and evaluation logic from OS Detection workflow node
  - Removed OS Detection QA toggle, model selector, and badge from UI
  - Removed JavaScript references to OS Detection QA functionality
  - OS Detection now runs without QA validation (single-pass detection)
- **Description Field**: Removed optional description textarea from workflow configuration form
  - Removed description field from workflow.html and workflow_config.html
  - Removed JavaScript references to description field
  - Backend continues to use default description values when not provided

### Fixed
- **QA Agent Indentation Error**: Fixed syntax error in qa_agent_service.py
  - Corrected indentation of code block inside `with trace_llm_call()` statement
  - Resolved "expected an indented block after 'with' statement" error

### Improved
- **LMStudio Busy Error Handling**: Enhanced error messages and user experience when LMStudio is busy or unavailable
  - Updated LangFuse client to provide informative error messages when generator errors occur (often indicates LMStudio busy)
  - Enhanced test agent endpoints (`test-subagent`, `test-rankagent`) to detect LMStudio busy conditions
  - Added user-friendly error messages with retry options in test agent modal
  - Frontend now shows "Wait and Retry" button when LMStudio is detected as busy
  - Improved error detection for timeout, connection, and overload scenarios

### Added
- **Workflow Agent Config Subpages Test**: Playwright test suite to verify workflow agent configuration subpages remain visible
  - TypeScript Playwright test (`tests/playwright/workflow_tabs.spec.ts`) with 10 test cases
  - Python pytest wrapper (`tests/ui/test_workflow_tabs_ui.py`) integrated into UI test suite
  - Verifies all three subpages (Configuration, Executions, SIGMA Queue) are accessible and functional
  - Tests tab navigation, hash URL routing, and content visibility
  - Prevents regression where tabs disappear after UI changes
- **Modal Interactions UI Test**: Comprehensive test suite for modal behavior (`tests/ui/test_modal_interactions_ui.py`)
  - 20 test cases covering Escape key closing, click-outside closing, and Cmd/Ctrl+Enter submission
  - Tests all modals: result, source config, execution, trigger workflow, rule, classification, custom prompt, help
  - Ensures consistent modal UX across the application
- **Comprehensive Test Documentation Update**: Complete audit and update of test inventory
  - Updated `tests/TEST_INDEX.md` with all 100+ test files across 9 categories
  - Documented 28 UI test files (383+ tests), 12 API test files (123+ tests), 19 E2E test files (120+ tests), 25 integration test files (200+ tests)
  - Added CLI tests (3 files), Utils tests (4 files), Workflows tests (1 file), and Smoke tests (2 files)
  - Updated test statistics: 1200+ total tests, 900+ active tests (75%+), 205 skipped (~17%), 32 failing (~3%)
  - Updated `tests/TESTING.md` and `tests/README.md` to reflect comprehensive test coverage
- **Agentic Workflow Test Coverage**: Comprehensive integration tests for the agentic workflow and LangGraph server
  - **LangGraph Server Tests**: `tests/workflows/test_langgraph_server.py` covering chat logic, input parsing, and node transitions
  - **Comprehensive Integration Test**: `tests/integration/test_agentic_workflow_comprehensive.py` simulating full "happy path" run with Article 1427
  - **Full Workflow Simulation**: Verifies end-to-end flow: Chat -> ID Parse -> OS Detect -> Junk Filter -> Rank -> Extract -> Sigma -> Queue
  - **State Verification**: Ensures correct state transitions and database updates at each step
- **OS Detection Agent**: Operating system detection for threat intelligence articles
  - Embedding-based detection using CTI-BERT or SEC-BERT models
  - Configurable embedding model selection (CTI-BERT, SEC-BERT)
  - Configurable LLM fallback model for low-confidence cases
  - Integration into agentic workflow (Step 1.5, after ranking, before extraction)
  - Workflow continues only if Windows detected; otherwise gracefully terminates
  - AI/ML Assistant modal with OS detection functionality
  - Manual testing script: `test_os_detection_manual.py`
- **SpaCy-Based Sentence Splitting**: Improved sentence boundary detection for content chunking
  - Replaced regex-based sentence splitting with SpaCy's sentencizer component
  - Better handling of abbreviations (Dr., CVE-, IOC, APT, etc.) and technical content
  - Improved chunk boundaries: 100% sentence boundary accuracy (up from 75%)
  - Eliminated mid-sentence breaks and fragmented sentences
  - Applied to `ContentCleaner.extract_summary()`, `ContentFilter.chunk_content()`, and chat sentence extraction
  - Fallback to regex if SpaCy unavailable for backward compatibility
- **SIGMA A/B Testing Interface**: Interactive web UI for comparing SIGMA rule similarity search logic
  - Side-by-side rule comparison with real-time YAML validation
  - Separate embedding and LLM model selection dropdowns
  - Detailed similarity breakdown by section (Title, Description, Tags, Signature)
  - LLM reranking with explanation and model attribution
  - Semantic overlap analysis showing literal detection value matches
  - Debug view showing exact embedding text used for comparison
  - LocalStorage persistence for Rule A and Rule B textareas
  - Combined Signature segment (logsource + detection) for improved similarity matching
- **Enhanced SIGMA Similarity Search**: Improved embedding-based similarity calculation
  - Removed "Title: " prefix from title embeddings to focus on semantic content
  - Combined logsource and detection into single "Signature" segment (87.4% weight)
  - Updated similarity weights: Title 4.2%, Description 4.2%, Tags 4.2%, Signature 87.4%
- **LMStudio Model Selection**: Database-driven model selection for embedding and LLM operations
  - Embedding model dropdown filtered to only show embedding models
  - LLM model dropdown filtered to only show chat models
  - Model selection persists through Settings page configuration

### Changed
- **OS Detection Similarity Logic**: Improved decision-making for embedding-based OS detection
  - High confidence (>0.8): Prefer top OS unless gap to second is < 0.5%
  - Prevents false "multiple" classifications when one OS is clearly dominant
  - Updated SEC-BERT model name: `nlpaueb/sec-bert-base` (was incorrect placeholder)
  - Suppressed harmless transformers warnings about uninitialized pooler weights
- **SIGMA Title Embeddings**: Removed "Title: " prefix to improve semantic similarity accuracy
- **SIGMA Section Embeddings**: Combined logsource, detection_structure, and detection_fields into single "Signature" segment
- **Similarity Calculation**: Updated weights to reflect combined Signature segment

### Fixed
- **LLM Model Dropdown**: Fixed duplicate ID conflict causing dropdown to stop working
- **Embedding Model Selection**: Fixed similarity search to use selected embedding model instead of default
- **LLM Reranking Model**: Fixed to use selected LLM model from dropdown instead of default

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
