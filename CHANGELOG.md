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

### Added
- **Comprehensive Source Coverage**: 11+ major security sources now operational for threat intelligence collection

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

