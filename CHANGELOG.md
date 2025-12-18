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

