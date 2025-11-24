# UI Test Coverage Analysis

## Main User Interfaces Identified

### Core Pages
1. **Dashboard** (`/`, `/dashboard`) - Main landing page
2. **Articles List** (`/articles`) - Article listing with filters
3. **Article Detail** (`/articles/{id}`) - Individual article view
4. **Sources** (`/sources`) - Source management
5. **Settings** (`/settings`) - Application settings
6. **Chat** (`/chat`) - RAG chat interface
7. **Analytics** (`/analytics`) - Analytics dashboard
8. **Scraper Metrics** (`/analytics/scraper-metrics`) - Scraper analytics
9. **Hunt Metrics** (`/analytics/hunt-metrics`) - Hunt scoring metrics
10. **Hunt Metrics Demo** (`/analytics/hunt-metrics-demo`) - Advanced hunt visualizations
11. **ML Hunt Comparison** (`/ml-hunt-comparison`) - ML vs Hunt comparison
12. **Workflow** (`/workflow`) - Unified workflow management (tabs: config, executions, queue)
13. **Health Checks** (`/health-checks`) - Health monitoring
14. **Diagnostics** (`/diags`) - System diagnostics (jobs + health)
15. **Jobs** (`/jobs`) - Job monitoring
16. **PDF Upload** (`/pdf-upload`) - PDF upload interface

### Excluded Pages (Not Production)
- `/sigma-ab-test` - Excluded per requirements
- `/sigma-similarity-test` - Excluded per requirements
- `/evaluations` - Excluded per requirements
- `/evaluations/compare` - Excluded per requirements
- `/evaluations/{agent_name}` - Excluded per requirements

---

## Existing Test Coverage

### ✅ Fully Tested Pages

#### Dashboard (`/`, `/dashboard`)
- **Tests**: `test_dashboard_functionality.py` (11 tests)
- **Coverage**: Page load, high-score articles, quick actions, navigation, data refresh

#### Articles List (`/articles`)
- **Tests**: `test_article_interactions_ui.py` (10 tests), `test_article_classification.py` (9 tests)
- **E2E**: `test_article_classification_workflow.py` (6 tests), `test_article_navigation.py`
- **Coverage**: Filtering, sorting, pagination, classification, navigation

#### Article Detail (`/articles/{id}`)
- **Tests**: `test_article_interactions_ui.py`, `test_article_classification.py`
- **E2E**: `test_annotation_workflow.py` (9 tests), `test_ai_assistant_workflow.py` (9 tests)
- **Coverage**: Classification, annotations, AI assistant, IOC extraction, navigation

#### Sources (`/sources`)
- **Tests**: `test_sources_ui.py` (8 tests), `test_collect_now_button.py` (9 tests)
- **E2E**: `test_source_management_workflow.py`
- **Coverage**: Source list, toggle status, collect now, source stats

#### Settings (`/settings`)
- **Tests**: `test_settings_ui.py` (63 tests)
- **E2E**: `test_settings_workflow.py`
- **Coverage**: Settings CRUD, bulk updates, categories, validation

#### Chat (`/chat`)
- **Tests**: `test_rag_chat_ui.py` (16 tests)
- **E2E**: `test_rag_chat_workflow.py` (8 tests)
- **Coverage**: Query submission, results display, conversation history, provider switching

#### Analytics (`/analytics`)
- **Tests**: `test_analytics_ui.py` (20 tests), `test_analytics_pages_ui.py` (11 tests)
- **E2E**: `test_analytics_workflow.py`
- **Coverage**: Dashboard cards, navigation, metrics display

#### Scraper Metrics (`/analytics/scraper-metrics`)
- **Tests**: `test_analytics_pages_ui.py`
- **Coverage**: Page load, metrics display

#### Hunt Metrics (`/analytics/hunt-metrics`)
- **Tests**: `test_analytics_pages_ui.py`
- **Coverage**: Page load, metrics display

#### Hunt Metrics Demo (`/analytics/hunt-metrics-demo`)
- **Tests**: `test_analytics_pages_ui.py`
- **Coverage**: Page load, visualizations

#### ML Hunt Comparison (`/ml-hunt-comparison`)
- **Tests**: `test_ml_hunt_comparison_workflow.py` (E2E)
- **Coverage**: Comparison display, filtering, backfill processing

#### Workflow (`/workflow`)
- **Tests**: `test_workflow_tabs_ui.py` (3 tests)
- **E2E**: `test_agentic_workflow_comprehensive.py` (integration)
- **Coverage**: Tab visibility, basic navigation

#### Health Checks (`/health-checks`)
- **Tests**: `test_health_page.py` (15 tests)
- **Coverage**: Page load, health status display, source checks

#### Diagnostics (`/diags`)
- **Tests**: `test_diags_ui.py` (51 tests)
- **Coverage**: Jobs display, health monitoring, real-time updates

#### Jobs (`/jobs`)
- **Tests**: `test_jobs_monitor_ui.py` (8 tests)
- **Coverage**: Job list, status display, queue information

#### PDF Upload (`/pdf-upload`)
- **Tests**: `test_pdf_upload_ui.py` (6 tests)
- **E2E**: `test_pdf_upload_workflow.py`
- **Coverage**: File upload, processing, error handling

---

## Missing Test Coverage

### 🔴 Critical Priority (Core Functionality)

#### 1. **Workflow Page - Comprehensive Feature Coverage** (`/workflow`)
**Priority**: CRITICAL
**Missing Coverage**:

**Tab Navigation**:
- Configuration tab button
- Executions tab button
- Queue tab button
- Tab switching functionality
- Active tab styling
- Tab content visibility toggle

**Configuration Tab - General**:
- Workflow config form
- Collapsible panel toggles (Junk Filter, OS Detection, Rank Agent, Extract Agent, SIGMA Generator)
- Panel toggle chevron rotation
- Current config display
- Config display loading state
- Reset button
- Save Configuration button
- Save button disabled state
- Config load API call
- Config save API call
- Config save success/error handling
- Auto-save on model changes

**Configuration Tab - Junk Filter Panel**:
- Junk Filter Threshold input (0-1, step 0.05)
- Threshold validation (0-1 range)
- Threshold error message display
- Help button for threshold
- Help modal display

**Configuration Tab - OS Detection Agent Panel**:
- OS Detection model container (dynamic)
- OS Detection prompt container (dynamic)
- Panel collapse/expand

**Configuration Tab - Rank Agent Panel**:
- Rank Agent QA badge (QA: OFF/ON)
- Rank Agent model container (dynamic)
- Test Rank Agent button (Article 2155)
- Test Rank Agent API call
- Test Rank Agent results display
- Ranking Threshold input (0-10, step 0.1)
- Ranking Threshold validation
- Ranking Threshold error message
- Ranking Threshold help button
- Rank Agent prompt container (dynamic)
- Rank QA Agent toggle checkbox
- Rank QA badge update on toggle
- Rank QA Model dropdown
- Rank QA Agent prompt container (hidden/shown based on toggle)

**Configuration Tab - Extract Agent Panel**:
- Extract Agent Supervisor badge
- Extract Agent model container (dynamic)
- Extract Agent prompt container (dynamic)
- Extract Agent QA prompt container (hidden/shown)
- Sub-Agents section header
- Sub-Agents panel collapse/expand

**Configuration Tab - Extract Sub-Agents** (CmdlineExtract, SigExtract, EventCodeExtract, ProcTreeExtract, RegExtract):
- Sub-agent panel collapse/expand
- Sub-agent QA badge (QA: OFF/ON)
- Model dropdown (Use Extract Agent Model or override)
- Temperature input (0-2, step 0.1)
- Test Sub-Agent button (Article 2155)
- Test Sub-Agent API call
- Test Sub-Agent results display
- Sub-agent prompt container (dynamic)
- Sub-agent QA Agent toggle checkbox
- Sub-agent QA badge update on toggle
- Sub-agent QA Model dropdown
- Sub-agent QA prompt container (hidden/shown)

**Configuration Tab - SIGMA Generator Agent Panel**:
- SIGMA Agent QA badge (QA: OFF/ON)
- SIGMA Agent model container (dynamic)
- Similarity Threshold input (0-1, step 0.05)
- Similarity Threshold validation
- Similarity Threshold error message
- Similarity Threshold help button
- SIGMA Agent prompt container (dynamic)
- SIGMA QA Agent toggle checkbox
- SIGMA QA badge update on toggle
- SIGMA QA Agent prompt container (hidden/shown)
- SIGMA Fallback toggle checkbox
- SIGMA Fallback description
- Embedding Model dropdown (for SIGMA Similarity Search)
- Embedding Model loading state

**Configuration Tab - Workflow Overview**:
- Workflow steps visualization (7 steps: OS Detection, Junk Filter, LLM Ranking, Extract Agent, Generate SIGMA, Similarity Search, Queue)
- Extract Agent sub-agents detail visualization (5 sub-agents)
- Step color coding
- Step highlighting

**Executions Tab - Actions**:
- Refresh button
- Trigger Workflow button
- Trigger Stuck Executions button
- Cleanup Stale Executions button
- Status filter dropdown (All, Pending, Running, Completed, Failed)
- Filter executions functionality

**Executions Tab - Workflow Visualization**:
- Workflow state machine visualization toggle
- SVG workflow diagram
- Workflow nodes (OS Detection, Junk Filter, Rank, Extract, Generate SIGMA, Similarity Search, Queue, End)
- Workflow edges/arrows
- Node highlighting based on current step
- Visualization collapse/expand

**Executions Tab - Statistics**:
- Total Executions stat card
- Running Executions stat card
- Completed Executions stat card
- Failed Executions stat card
- Stats update on filter change
- Stats API integration

**Executions Tab - Executions Table**:
- Table columns (ID, Article, Status, Current Step, Ranking Score, Created, Actions)
- Execution row rendering
- Status badges (Pending, Running, Completed, Failed)
- Step badges (Filter, Rank, Extract, SIGMA, Similarity, Queue)
- Ranking score display
- Created timestamp display
- View button (opens execution detail modal)
- Live button (for running/pending executions)
- Retry button (for failed executions)
- Cancel button (for running/pending executions)
- Table loading state
- Table empty state
- Table error state

**Executions Tab - Execution Detail Modal**:
- Modal open/close functionality
- Modal fullscreen toggle
- Fullscreen icon toggle
- Modal backdrop click to close
- Modal Escape key to close
- Execution detail content loading
- Execution detail API call
- Execution detail content display (structured details, logs, etc.)
- Execution detail error handling
- Modal scrollable content

**Executions Tab - Trigger Workflow Modal**:
- Modal open/close functionality
- Article ID input
- Article ID validation
- Trigger button
- Cancel button
- Trigger workflow API call
- Trigger workflow success/error message
- Message display area

**Queue Tab - Actions**:
- Refresh button
- Status filter dropdown
- Filter queue functionality

**Queue Tab - Queue Table**:
- Table columns (Rule ID, Title, Status, Similarity, Created, Actions)
- Queue row rendering
- Status badges
- Similarity score display
- View button
- Delete button
- Table loading state
- Table empty state
- Table error state

**Queue Tab - Queue Detail Modal**:
- Modal open/close functionality
- Queue detail content loading
- Queue detail API call
- Queue detail content display
- Queue detail error handling

**Why Critical**: Core feature for agentic workflow management with 100+ interactive elements. Currently only has basic tab visibility tests.

---

### 🟡 High Priority (Important Features)

#### 2. **Articles List - Comprehensive Feature Coverage**
**Priority**: HIGH
**Missing Coverage**:

**Search & Filter Features**:
- Search help button toggle and modal display
- Predefined search pattern links (High-Value Detection, Technical Intelligence, Actionable Intelligence)
- Title-only checkbox toggle
- Boolean search query parsing (AND, OR, NOT, quoted phrases)
- Search help modal content display
- Source filter dropdown
- Classification filter dropdown (chosen/rejected/unclassified)
- Threat hunting score range filter
- Filter summary display with active filters
- Clear all filters link
- Default filters save functionality
- Default filters clear functionality
- Default filters indicator display
- Filter persistence via sessionStorage
- URL parameter filter parsing and application

**Sorting Features**:
- Sort by dropdown (discovered_at, published_at, title, source_id, threat_hunting_score, annotation_count, word_count, id)
- Sort order dropdown (asc/desc)
- Dynamic sorting auto-submit on change
- Sort parameter preservation in URL
- Sort indicators display

**Pagination Features**:
- Per-page selector (20/50/100)
- Page number links with ellipsis
- Previous/Next navigation
- Pagination state preservation with filters
- Page count display
- Results range display (start_idx-end_idx of total)

**Statistics Features**:
- Article statistics toggle (collapsible)
- Statistics panel display (total, chosen, rejected counts)
- Statistics panel collapse/expand

**Bulk Selection Features**:
- Select all visible checkbox
- Individual article checkboxes
- Bulk actions toolbar visibility toggle
- Selected count display
- Select all visible button
- Clear selection button
- Bulk action buttons (Mark as Chosen, Reject, Unclassify, Delete)
- Bulk action confirmation modals
- Bulk action success/error notifications
- Bulk action API error handling

**Article Card Features**:
- Article title link navigation
- Article ID badge display
- Source name display and link
- Published date display
- Content length display
- Classification badge display (chosen/rejected/unclassified)
- RegexHuntScore badge with color coding (80+, 60+, 40+, <40)
- ML Hunt Score badge with color coding
- ML Hunt Score "TBD" state with tooltip
- Annotation count badge display
- Keyword matches display (perfect, good, LOLBAS)
- Keyword match truncation (+N indicator)
- Article content preview (first 300 chars)
- Copy article content button
- Original source link
- Article card hover effects

**Classification Modal Features**:
- Modal open/close functionality
- Modal article data loading
- Modal loading state display
- Article title display in modal
- Article source/date/length display
- Article content display in modal
- Current classification display
- Classification buttons in modal (chosen/rejected/unclassified)
- Modal navigation (Previous, Next Unclassified)
- Modal keyboard shortcuts (Escape to close)
- Modal click-away to close
- Classification success notifications
- Classification error handling

**Empty State Features**:
- No articles found message
- Empty state with filters active message
- Empty state without filters message

**Why High**: Many features exist but lack comprehensive test coverage. Critical for user workflow.

#### 3. **Article Detail - Advanced Features**
**Priority**: HIGH
**Missing Coverage**:
- Workflow execution status display
- Workflow execution history
- SIGMA rule generation from article
- SIGMA rule queue integration
- Article metadata editing
- Article content editing
- Article deletion confirmation
- Article duplicate detection
- Article similarity search
- Article export (multiple formats)

**Why High**: Extends core article functionality testing.

#### 4. **Analytics - Comprehensive Feature Coverage**
**Priority**: HIGH
**Missing Coverage**:

**Main Analytics Page** (`/analytics`):
- Analytics dashboard cards (ML vs Hunt Comparison, Scraper Metrics, Hunt Scoring Metrics)
- Card hover effects
- Card navigation links
- Quick Overview stats (Total Articles, Active Sources, Avg Hunt Score, Filter Efficiency)
- Quick stats API call (`/api/dashboard/data`)
- Quick stats display updates
- Quick stats error handling

**Scraper Metrics Page** (`/analytics/scraper-metrics`):
- Breadcrumb navigation
- Metrics overview cards (Articles Today, Active Sources, Avg Response Time, Error Rate)
- Collection Rate Chart (Last 7 Days) with Chart.js
- Source Health Distribution Chart with Chart.js
- Hunt Score Ranges Chart (Last 30 Days) with Chart.js
- Hourly Distribution Chart (Today) with Chart.js
- Source Performance Table (collapsible)
- Source Performance toggle button
- Source Performance table columns (Source, Status, Articles Today, Last Success, Error Rate, Avg Response)
- Article Ingestion Analytics section (collapsible)
- Article Ingestion Analytics toggle button
- Scraper metrics API calls (`/api/analytics/scraper/overview`, `/api/analytics/scraper/collection-rate`, `/api/analytics/scraper/source-health`)
- Chart rendering and updates
- Chart error handling
- Table data loading and display

**Hunt Scoring Metrics Page** (`/analytics/hunt-metrics`):
- Breadcrumb navigation
- Metrics overview cards (Avg Hunt Score, High Quality Articles, Perfect Matches, LOLBAS Matches)
- Hunt Score Distribution Chart with Chart.js
- Keyword Performance Chart (Top Performing Keywords - Perfect Discriminators)
- Keyword Performance Chart help tooltip
- Keyword Performance Chart help content (scope, keyword lists, note)
- Keyword Analysis Table (collapsible)
- Keyword Analysis toggle button
- Keyword Analysis table columns (Category, Keyword, Match Count, Avg Score Impact)
- Score Trends Chart (Last 30 Days) with Chart.js
- Top Sources by Hunt Score Chart with Chart.js
- Content Quality Breakdown Chart with Chart.js
- Content Quality Breakdown help tooltip
- Content Quality Breakdown help content (Unscored, Low Quality, Medium Quality, High Quality, Very High Quality)
- Hunt metrics API calls
- Chart rendering and updates
- Table data loading and display
- Tooltip hover interactions

**Chart Interactions**:
- Chart.js initialization
- Chart responsive behavior
- Chart empty state handling
- Chart error state handling
- Chart loading state
- Chart data updates

**Why High**: Multiple analytics pages with charts, tables, and interactive elements requiring comprehensive testing.

#### 5. **Sources - Comprehensive Feature Coverage**
**Priority**: HIGH
**Missing Coverage**:

**Source List Display**:
- Source cards with metadata
- Article count badge display
- Source name links to articles
- Active/Inactive status badges
- Source URL display
- RSS feed URL display
- Collection method display (RSS/Web Scraping)
- Last check timestamp
- Articles collected count
- Check frequency display (minutes)
- Lookback window display (days)
- Min content length display
- Description display
- Quality metrics panel (when available)
- Quality metrics: Total/Rejected/Chosen/Unclassified/Avg Hunt Score
- Hunt score lookup display
- Manual source panel (separate styling)
- Empty state ("No sources configured")
- Source sorting by hunt score

**Source Actions**:
- Collect Now button
- Collect Now API call
- Collection status modal
- Collection progress display
- Collection terminal output
- Collection task monitoring
- Collection success/error handling
- Collection status close button
- Toggle Status button
- Toggle Status API call
- Toggle Status modal display
- Toggle Status success/error handling
- Toggle Status auto-refresh
- Toggle Status manual refresh button
- Database status banner display
- Configure button
- Source configuration modal
- Source stats button
- Source stats modal display
- Source stats API call
- Source stats error handling

**Source Configuration Modal**:
- Modal open/close functionality
- Lookback days input (1-365)
- Check frequency input (minutes, 1-1440)
- Min content length input
- Form validation
- Save configuration button
- Cancel button
- Configuration save API calls (3 parallel)
- Configuration save success/error handling
- Configuration modal click-away to close
- Configuration modal Escape key to close
- Configuration modal keyboard shortcuts (Enter to save)

**Adhoc URL Scraping**:
- Adhoc URL form display
- URL textarea input
- Title input
- Force scrape checkbox
- Scrape button
- Scraping status display
- Scraping progress
- Scraping success/error handling
- Form submission handling
- Enter key submission

**Result Modal**:
- Modal display
- Modal title
- Modal content
- Modal close button
- Modal click-away to close
- Modal Escape key to close
- Loading modal state
- Error modal state

**Database Status Banner**:
- Banner visibility toggle
- Banner refresh button
- Banner display logic

**PDF Upload Section**:
- PDF upload card display
- Upload PDF button/link

**Why High**: Many interactive features exist but lack comprehensive test coverage.

#### 6. **Settings - Comprehensive Feature Coverage**
**Priority**: HIGH
**Missing Coverage**:

**Backup Configuration Section**:
- Collapsible section toggle
- Chevron icon rotation
- Backup schedule inputs (daily/weekly cleanup times)
- Retention policy inputs (daily/weekly/monthly backups, max size GB)
- Backup components checkboxes (Database, ML Models, Config, Training Data, Logs, Docker Volumes)
- Backup settings (directory, type dropdown, compression checkbox, verification checkbox)
- Backup actions (Create Backup Now, List Backups, Check Status buttons)
- Backup status display panel
- Backup status content loading
- Backup API calls
- Backup success/error handling

**AI/ML Assistant Configuration**:
- AI model selection dropdown
- LMStudio model section visibility toggle
- LMStudio model dropdown (alphabetical order)
- LMStudio models API loading
- Temperature slider (0.0-1.0)
- Temperature value display
- Model description panel
- Model selection change handlers

**SIGMA Rule Configuration**:
- SIGMA author input
- Author name persistence

**Data Export**:
- Export Annotations button
- Export progress indicator
- Export CSV generation
- Export API call
- Export success/error handling
- Export file download

**API Configuration Section**:
- Section visibility toggle (based on AI model)
- OpenAI API key input (password type)
- OpenAI API key toggle visibility button
- Anthropic API key input (password type)
- Anthropic API key toggle visibility button
- Anthropic section visibility (based on model)
- Langfuse configuration section
- Langfuse Public Key input
- Langfuse Public Key toggle visibility
- Langfuse Secret Key input
- Langfuse Secret Key toggle visibility
- Langfuse Host input
- Langfuse Project ID input
- Test Langfuse Connection button
- Langfuse test status display
- Test API Key button (dynamic text based on model)
- API key test status display
- API key test API calls
- API key test success/error handling

**Settings Persistence**:
- Load settings from localStorage
- Load settings from database (Langfuse priority)
- Save settings to localStorage
- Save settings to database
- Settings save button
- Settings save API calls
- Settings save success notification
- Settings save error handling
- Settings validation

**Settings Loading**:
- Page load settings initialization
- LMStudio models async loading
- Database settings fallback to localStorage
- Default values handling

**Why High**: Complex settings management with many interdependent features requiring comprehensive testing.

#### 7. **Chat - Comprehensive Feature Coverage**
**Priority**: HIGH
**Missing Coverage**:

**Message Display**:
- User message bubbles (right-aligned, purple background)
- Assistant message bubbles (left-aligned, gray background)
- Error message styling (red background, red border)
- System message styling (green background, green border)
- Message timestamps display
- LLM model name badge display
- Message content whitespace preservation (pre-wrap)
- Message scrolling to bottom on new messages
- Loading indicator during message sending
- Loading message content ("Searching threat intelligence database...")

**Article Results Display**:
- Article results section header ("📚 X articles:")
- Article compact view (similarity %, title, expand/collapse indicator)
- Article expanded view (title link, source, similarity, summary preview)
- Article expansion toggle (click to expand/collapse)
- Article title links to article detail page (new tab)
- Article similarity percentage display
- Article source name display
- Article summary truncation (150 chars)
- Multiple article expansion state management

**SIGMA Rule Results Display**:
- SIGMA rules section header ("🛡️ X detection rules:")
- Rule compact view (similarity %, title, expand/collapse indicator)
- Rule expanded view (title, status, level, similarity, description, MITRE tags, file path)
- Rule expansion toggle
- MITRE ATT&CK tag filtering and display (attack.* tags)
- MITRE tags truncation (first 3 tags)
- Rule description truncation (150 chars)
- Rule file path display with YAML modal trigger
- Rule YAML modal open functionality

**YAML Modal**:
- Modal open/close functionality
- Modal backdrop click to close
- Modal Escape key to close
- Modal header (title, file path)
- Modal body (YAML content in code block)
- Modal footer (Copy to Clipboard button, Close button)
- Copy to Clipboard functionality
- Copy success alert
- YAML content API fetch (`/api/articles/sigma-rules-yaml/{ruleId}`)
- YAML modal error handling

**Settings Panel**:
- Max Results dropdown (3, 5, 10, 20 articles)
- Similarity Threshold dropdown (30%, 40%, 50%, 60%, 70%, 80%)
- Embedding stats display (embedded_count/total_articles, coverage %)
- Update Embeddings button
- Update Embeddings loading state
- Update Embeddings API call (`/api/embeddings/update`)
- Update Embeddings success message (task ID, batch size, estimated articles)
- Update Embeddings error handling
- Settings persistence (localStorage)
- Settings load from localStorage on mount

**Input Area**:
- Textarea input field
- Input placeholder text
- Input disabled state during loading
- Send button
- Send button disabled state (empty input or loading)
- Send button loading text ("Sending...")
- Enter key submission (Shift+Enter for newline)
- Input focus management
- Input value clearing after send
- Input suggestions text ("💡 Try asking...")

**API Integration**:
- RAG chat API call (`/api/chat/rag`)
- Request body (message, conversation_history, max_results, similarity_threshold, use_chunks, context_length, use_llm_generation, llm_provider, include_sigma_rules)
- Response handling (response, timestamp, relevant_articles, relevant_rules, total_results, total_rules, llm_provider, llm_model_name, use_llm_generation)
- Error handling and display
- Loading state management

**Model Selection**:
- AI model loading from Settings (localStorage)
- Model selection normalization (openai/gpt4o/gpt-4o/gpt-4o-mini/gpt → chatgpt)
- Default model fallback (chatgpt)
- Model selection error handling

**Embedding Stats**:
- Embedding stats API call (`/api/embeddings/stats`)
- Stats display (embedded_count, total_articles, embedding_coverage_percent)
- Stats refresh after embedding update
- Stats loading error handling

**Why High**: Complex React component with many interactive features requiring comprehensive testing.

---

### 🟢 Medium Priority (Nice to Have)

#### 8. **Dashboard - Comprehensive Feature Coverage**
**Priority**: MEDIUM
**Missing Coverage**:

**Health Metrics Card**:
- Uptime percentage display
- Total sources count display
- Average response time display
- Health indicator color coding (green/yellow/red based on uptime)
- Health indicator dynamic updates

**Volume Charts**:
- Daily volume chart initialization
- Hourly volume chart initialization
- Chart.js integration and configuration
- Chart data updates from API
- Chart responsive behavior
- Chart empty state handling
- Chart error state handling
- Chart loading state

**Failing Sources Widget**:
- Failing sources list display
- Consecutive failures count
- Last success timestamp display
- Color coding by failure severity (5+, 3+, <3)
- Empty state ("No failing sources")
- Error state handling
- Auto-refresh functionality

**High-Score Articles Widget**:
- Article cards display
- Article title links
- Classification badges (Chosen/Rejected/Unclassified)
- Hunt score display with color coding
- Source name display
- Publication date display
- Copy URLs button functionality
- Copy URLs button feedback (✓ Copied!)
- Copy URLs clipboard integration
- Empty state handling
- Article card hover effects
- Article card click navigation

**System Stats Widget**:
- Total articles count
- Active sources count
- Processing queue display
- Average score display

**Recent Activity Widget**:
- Activity timeline display
- Activity color coding (green/red/yellow/blue)
- Time ago formatting
- Activity message display
- Empty state ("No recent activity")
- Scrollable container

**Quick Actions**:
- Rescore All Articles button
- Rescore API call
- Rescore success notification
- Rescore error handling
- Rescore dashboard refresh trigger
- Run Health Check button
- Health check navigation
- Session storage flag setting
- Auto-run health checks on page load

**Data Loading**:
- Dashboard data API call
- Auto-refresh polling (60s interval)
- Last updated timestamp display
- Error handling for API failures
- Chart initialization retry logic
- CDN loading detection

**Why Medium**: Core functionality exists but many edge cases and interactions untested.

#### 9. **PDF Upload - Advanced Features**
**Priority**: MEDIUM
**Missing Coverage**:
- Multiple file upload
- Upload progress display
- Upload queue management
- Upload error recovery
- Upload history
- Upload validation (file size, type)
- Upload cancellation
- Upload retry functionality

**Why Medium**: Improves upload workflow but basic functionality tested.

#### 10. **Health Checks - Advanced Monitoring**
**Priority**: MEDIUM
**Missing Coverage**:
- Health check history
- Health check alerts
- Health check notifications
- Health check scheduling
- Health check export
- Health check comparison
- Health check trends

**Why Medium**: Monitoring enhancement, basic functionality covered.

#### 11. **Diagnostics - Advanced Features**
**Priority**: MEDIUM
**Missing Coverage**:
- Diagnostic report generation
- Diagnostic export
- Diagnostic history
- Diagnostic filtering
- Diagnostic search
- Diagnostic comparison
- Diagnostic alerts

**Why Medium**: Diagnostic tools enhancement.

#### 12. **Jobs - Advanced Monitoring**
**Priority**: MEDIUM
**Missing Coverage**:
- Job filtering and search
- Job cancellation
- Job retry
- Job priority management
- Job queue management
- Job history export
- Job performance metrics
- Job error analysis

**Why Medium**: Job management enhancement.

---

### 🔵 Low Priority (Edge Cases & Polish)

#### 13. **Cross-Page Navigation**
**Priority**: LOW
**Missing Coverage**:
- Breadcrumb navigation
- Deep linking
- Browser back/forward
- Bookmark functionality
- URL parameter handling
- Navigation state persistence

**Why Low**: Basic navigation tested, this covers edge cases.

#### 14. **Error Handling - All Pages**
**Priority**: LOW
**Missing Coverage**:
- 404 error pages
- 500 error pages
- Network error handling
- Timeout handling
- Invalid input handling
- Permission error handling
- Rate limit handling

**Why Low**: Some error handling tested, comprehensive coverage is polish.

#### 15. **Accessibility - All Pages**
**Priority**: LOW
**Missing Coverage**:
- Keyboard navigation
- Screen reader compatibility
- ARIA labels
- Focus management
- Color contrast
- Text scaling

**Why Low**: Basic accessibility tested (`test_accessibility.py`), comprehensive coverage is enhancement.

#### 16. **Performance - All Pages**
**Priority**: LOW
**Missing Coverage**:
- Page load time
- API response time
- Rendering performance
- Memory usage
- Network usage
- Caching behavior

**Why Low**: Basic performance tested (`test_performance.py`), detailed coverage is optimization.

#### 17. **Mobile Responsiveness - All Pages**
**Priority**: LOW
**Missing Coverage**:
- Mobile layout testing
- Touch interactions
- Mobile navigation
- Mobile form inputs
- Mobile modals
- Mobile tables

**Why Low**: Some mobile testing exists (`test_mobile_annotation.py`), comprehensive coverage is enhancement.

---

## Test Implementation Priority Ranking

### Phase 1: Critical (Implement First)
1. Workflow Page - Comprehensive Tests

### Phase 2: High Priority (Implement Next)
2. Articles List - Advanced Filtering
3. Article Detail - Advanced Features
4. Analytics - Interactive Features
5. Sources - Advanced Management
6. Settings - Advanced Features
7. Chat - Advanced Features

### Phase 3: Medium Priority (Implement When Time Permits)
8. Dashboard - Advanced Widgets
9. PDF Upload - Advanced Features
10. Health Checks - Advanced Monitoring
11. Diagnostics - Advanced Features
12. Jobs - Advanced Monitoring

### Phase 4: Low Priority (Polish & Edge Cases)
13. Cross-Page Navigation
14. Error Handling - All Pages
15. Accessibility - All Pages
16. Performance - All Pages
17. Mobile Responsiveness - All Pages

---

## Summary Statistics

- **Total UI Pages**: 16 (excluding excluded pages)
- **Pages with Tests**: 15 (94%)
- **Pages Fully Tested**: 15 (94%)
- **Pages Partially Tested**: 0 (0%)
- **Pages Without Tests**: 1 (6%)

### Missing Test Coverage Breakdown
- **Critical**: 1 test suite
- **High Priority**: 6 test suites
- **Medium Priority**: 5 test suites
- **Low Priority**: 5 test suites

### Existing Test Files
- **UI Tests**: 28 files
- **E2E Tests**: 18 files
- **Total Test Methods**: 380+ UI tests, 200+ E2E tests

---

## Recommendations

1. **Immediate Action**: Implement Phase 1 (Critical) tests for workflow page comprehensive functionality
2. **Short-term**: Complete Phase 2 (High Priority) to enhance existing coverage
3. **Long-term**: Add Phase 3 & 4 tests for comprehensive coverage
4. **Maintenance**: Keep test coverage updated as new features are added

