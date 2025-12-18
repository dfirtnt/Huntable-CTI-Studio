## 2025-12-18

### Fixed
- Model provider dropdowns in workflow configuration now respect Settings selection
- Deselected providers in AL/ML Assistant Configuration no longer appear in agent workflow config page
- Provider options are dynamically filtered based on `WORKFLOW_*_ENABLED` settings from `/api/settings`

## 2025-12-16

### Changed
- Refactored all collapsible panels to use global `initCollapsiblePanels()` system in base.html
- Entire panel header is now clickable (not just caret icon)
- Added keyboard support (Enter/Space) and proper ARIA attributes for accessibility
- Updated panels: articles.html (filters), workflow.html (12 panels), article_detail.html (keyword matches), diags.html (job history), scraper_metrics.html (source performance), hunt_metrics.html (keyword analysis)

