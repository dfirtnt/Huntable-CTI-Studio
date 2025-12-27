## 2025-12-27

### Fixed
- **Eval Workflow Boolean Handling**: Fixed skip flags (skip_os_detection, skip_rank_agent, skip_sigma_generation) to handle both boolean and string "true"/"false" values from JSONB config_snapshot
- **Eval Workflow Execution**: Fixed eval workflows not skipping OS detection due to string boolean values in config_snapshot
- **Config Snapshot Parsing**: Added JSONB parsing fallback for config_snapshot when it's not already a dict

### Added
- **Aggregate Eval Scoring**: Added comprehensive aggregate scoring per workflow config version
  - Mean Score: Average deviation across all eval articles
  - Mean Absolute Error (MAE): Average absolute deviation
  - Mean Squared Error (MSE): Squared deviation metric
  - Perfect Match Percentage: % of articles with exact match (score = 0)
  - Score Distribution: Breakdown of scores by range (0, ±1-2, ±3+)
  - API endpoint: `/api/evaluations/subagent-eval-aggregate` with config version grouping
  - UI display: "Aggregate Scores by Config Version" section in agent evals page
  - Color-coded MAE display (green/yellow/red based on threshold)

### Changed
- **Eval Articles**: Removed BleepingComputer article from cmdline extractor eval set (reduced from 9 to 8 articles)

## 2025-12-26

### Fixed
- **Source Configuration Fixes**: Resolved RSS and web scraping issues for multiple CTI sources
  - Sekoia.io: Switched to web scraping with proper article discovery
  - VMRay Blog: RSS URL corrected, quality filters adjusted
  - Splunk Security Blog: Web scraping configuration updated
  - Assetnote Research: Switched from broken RSS to web scraping
  - CrowdStrike Intelligence Blog: Web scraping selectors improved
  - Corelight Bright Ideas Blog: Atlas framework selectors added
  - Group-IB Threat Intelligence: RSS URL corrected
  - Red Canary Blog: RSS quality filters optimized
- **RSS Parser Enhancements**: Improved quality filtering for RSS-only sources with configurable word/content limits
- **Dashboard Metrics**: Excluded manual source from failing sources metrics to show accurate CTI source health
- **API Improvements**: Failing sources API now filters out system-generated manual source
- **Eval System Fixes**: Fixed config merge to preserve nested dicts (agent_models, agent_prompts, qa_enabled) when merging config_snapshot
- **Eval Record Updates**: Fixed eval records not updating when workflow execution status is already 'completed'
- **API Endpoint Bug**: Fixed indentation bug in subagent-eval-results endpoint that caused incorrect result filtering

### Added
- **Comprehensive Source Coverage**: 11+ major security sources now operational for threat intelligence collection
- **Subagent Evaluation System**: Complete evaluation framework for testing extractor subagents
  - Evaluation articles stored in `config/eval_articles.yaml` with expected observable counts
  - `SubagentEvaluationTable` database table for tracking evaluation results
  - UI at `/mlops/agent-evals` for running and viewing evaluations
  - Scoring system: perfect score is 0 (exact match), shows deviation from expected count
  - Color-coded results: green (0), yellow (±1-2), red (±3+)
- **Eval Workflow Optimizations**: 
  - Skip OS Detection, Rank Agent, and SIGMA generation for eval runs to save time
  - Filter out SigmaAgent models during eval runs to prevent loading unnecessary 30b model
  - Eval runs terminate after extractor agent completes
- **Clear Pending Records**: Added button to delete pending evaluation records from UI

## 2025-12-18

### Fixed
- Model provider dropdowns in workflow configuration now respect Settings selection
- Deselected providers in AL/ML Assistant Configuration no longer appear in agent workflow config page
- Provider options are dynamically filtered based on `WORKFLOW_*_ENABLED` settings from `/api/settings`
- LMStudio Context Window Commands panel now hidden when no LMStudio providers are selected in workflow config
- LMStudio Context Window Commands panel visibility now checks for actual model selection (not just provider)
- Model dropdowns now only show models from selected provider (LMStudio dropdowns only contain LMStudio models)
- Model fields are cleared when provider changes to prevent cross-provider model selection
- Sub-agent and QA agent model dropdowns check provider before populating
- OS Detection fallback now persists correctly (only saves when toggle is checked)
- Fixed LMStudio model selection being cleared unnecessarily when provider dropdowns refresh
- Selected Models display now filters by QA enabled status (Rank/Extract/SIGMA only show if QA enabled)

### Added
- OS Detection fallback LLM now supports cloud providers (OpenAI, Anthropic)
- Provider selector added for OS Detection fallback model configuration
- Fallback model respects provider selection and uses appropriate input type
- Current Configuration display now shows selected models with their providers (filtered by enabled status)

## 2025-12-16

### Changed
- Refactored all collapsible panels to use global `initCollapsiblePanels()` system in base.html
- Entire panel header is now clickable (not just caret icon)
- Added keyboard support (Enter/Space) and proper ARIA attributes for accessibility
- Updated panels: articles.html (filters), workflow.html (12 panels), article_detail.html (keyword matches), diags.html (job history), scraper_metrics.html (source performance), hunt_metrics.html (keyword analysis)

