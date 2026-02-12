# Manual Testing

<!-- MERGED FROM: development/MANUAL_TEST_CHECKLIST.md, development/MANUAL_CHECKLIST_30MIN.md -->

# Manual Testing Checklist

## Overview

This comprehensive testing checklist ensures all features of the Huntable CTI Studio platform are thoroughly tested before deployment.

## Pre-Testing Setup

### **Environment Preparation**
- [ ] **Docker Environment**
  - [ ] Docker and Docker Compose are installed
  - [ ] All containers can be started successfully
  - [ ] No port conflicts exist
  - [ ] Sufficient disk space available

- [ ] **Database Setup**
  - [ ] PostgreSQL container is running
  - [ ] Database tables are created
  - [ ] Connection string is correct
  - [ ] No migration errors

- [ ] **Redis Setup**
  - [ ] Redis container is running
  - [ ] Celery can connect to Redis
  - [ ] No connection errors in logs

- [ ] **Application Setup**
  - [ ] All Python dependencies are installed
  - [ ] Environment variables are set correctly
  - [ ] Configuration files are in place
  - [ ] Log files are writable

## Core Functionality Testing

### **Source Management**

- [ ] **Source Configuration Bootstrap**
  - [ ] When database is empty, seed via `config/sources.yaml`
  - [ ] Verify all seeded sources are parsed correctly
  - [ ] Confirm identifiers, RSS URLs, and metadata populated as expected

- [ ] **Source Config UI**
  - [ ] Create/update a source via the web tab and ensure values persist after restart
  - [ ] Test regex helper with matching/non-matching URLs
  - [ ] Validate tooltip guidance covers key fields
  - [ ] Export updated row back to YAML when repository snapshot needs refresh

- [ ] **Source Database Operations**
  - [ ] Create new sources via CLI
  - [ ] Update existing sources
  - [ ] Disable/enable sources
  - [ ] Delete sources (if applicable)

- [ ] **Source Health Monitoring**
  - [ ] Check source health status
  - [ ] Verify last check timestamps
  - [ ] Test source validation
  - [ ] Monitor error rates

### **Content Collection**

- [ ] **RSS Feed Processing**
  - [ ] Test RSS feed parsing
  - [ ] Verify article extraction
  - [ ] Check metadata extraction
  - [ ] Test feed validation

- [ ] **Web Scraping**
  - [ ] Test modern scraping (JSON-LD, OpenGraph)
  - [ ] Verify CSS selector fallbacks
  - [ ] Check content extraction accuracy
  - [ ] Test rate limiting

- [ ] **Content Processing**
  - [ ] Test content normalization
  - [ ] Verify deduplication
  - [ ] Check quality scoring
  - [ ] Test content hashing

### **Database Operations**

- [ ] **Article Storage**
  - [ ] Save articles to database
  - [ ] Verify data integrity
  - [ ] Test bulk operations
  - [ ] Check indexing

- [ ] **Query Performance**
  - [ ] Test article retrieval
  - [ ] Verify search functionality
  - [ ] Check filtering
  - [ ] Test pagination

- [ ] **Data Export**
  - [ ] Export articles to JSON
  - [ ] Export articles to CSV
  - [ ] Verify export format
  - [ ] Check data completeness

## Web Interface Testing

### **Dashboard**

- [ ] **Main Dashboard**
  - [ ] Navigate to `http://localhost:8001`
  - [ ] Verify statistics are displayed
  - [ ] Check recent articles list
  - [ ] Test navigation links

- [ ] **Statistics Display**
  - [ ] Verify source count
  - [ ] Check article count
  - [ ] Test date range filtering
  - [ ] Verify real-time updates

### **Articles Page**

- [ ] **Article Listing**
  - [ ] Navigate to `/articles`
  - [ ] Verify articles are displayed
  - [ ] Test search functionality
  - [ ] Check filtering options

- [ ] **Article Details**
  - [ ] Click on article to view details
  - [ ] Verify content is displayed
  - [ ] Check metadata is shown
  - [ ] Test source attribution

- [ ] **Pagination**
  - [ ] Test page navigation
  - [ ] Verify page size options
  - [ ] Check total count display
  - [ ] Test URL parameters

### **Analysis Page**

- [ ] **TTP Analysis**
  - [ ] Navigate to `/analysis`
  - [ ] Verify analysis results
  - [ ] Check technique detection
  - [ ] Test confidence scores

- [ ] **Quality Assessment**
  - [ ] Verify quality scores
  - [ ] Check quality distribution
  - [ ] Test quality filters
  - [ ] Validate scoring logic

### **Sources Page**

- [ ] **Source Management**
  - [ ] Navigate to `/sources`
  - [ ] Verify source list
  - [ ] Test source details
  - [ ] Check source statistics

- [ ] **Source Operations**
  - [ ] Test source activation/deactivation
  - [ ] Verify source health status
  - [ ] Check source configuration
  - [ ] Test source editing

## API Testing

### **Health Check**

- [ ] **Health Endpoint**
  ```bash
  curl http://localhost:8001/health
  ```
  - [ ] Verify response format
  - [ ] Check status is "healthy"
  - [ ] Verify database connection
  - [ ] Check service information

### **Articles API**

- [ ] **List Articles**
  ```bash
  curl http://localhost:8001/api/articles
  ```
  - [ ] Verify JSON response
  - [ ] Check pagination
  - [ ] Test filtering
  - [ ] Verify article data

- [ ] **Article Detail**
  ```bash
  curl http://localhost:8001/api/articles/1
  ```
  - [ ] Verify article details
  - [ ] Check metadata
  - [ ] Test error handling
  - [ ] Verify content

### **Sources API**

- [ ] **List Sources**
  ```bash
  curl http://localhost:8001/api/sources
  ```
  - [ ] Verify source list
  - [ ] Check source data
  - [ ] Test filtering
  - [ ] Verify statistics

- [ ] **Source Operations**
  ```bash
  curl -X POST http://localhost:8001/api/sources/1/toggle
  ```
  - [ ] Test source activation
  - [ ] Verify status change
  - [ ] Check error handling
  - [ ] Test invalid IDs

## CLI Testing

### **Basic Commands**

- [ ] **Help Command**
  ```bash
  ./run_cli.sh --help
  ```
  - [ ] Verify help text
  - [ ] Check command list
  - [ ] Test subcommand help
  - [ ] Verify usage examples

- [ ] **Init Command**
  ```bash
  ./run_cli.sh init --config config/sources.yaml
  ```
  - [ ] Verify source loading
  - [ ] Check database creation
  - [ ] Test validation
  - [ ] Verify error handling

### **Collection Commands**

- [ ] **Collect Command**
  ```bash
  ./run_cli.sh collect
  ```
  - [ ] Verify content collection
  - [ ] Check progress display
  - [ ] Test error handling
  - [ ] Verify results

- [ ] **Stats Command** (overview of sources and articles)
  ```bash
  ./run_cli.sh stats
  ```
  - [ ] Verify source and article counts
  - [ ] Check recent activity display

### **Search and Export**

- [ ] **Export Command**
  ```bash
  ./run_cli.sh export --format json --days 7
  ```
  - [ ] Test data export
  - [ ] Verify file format
  - [ ] Check data completeness
  - [ ] Test date filtering

## Background Tasks Testing

### **Celery Workers**

- [ ] **Worker Startup**
  - [ ] Start Celery worker
  - [ ] Verify worker registration
  - [ ] Check task queue
  - [ ] Test task execution

- [ ] **Scheduled Tasks**
  - [ ] Test source checking task
  - [ ] Verify content collection task
  - [ ] Check cleanup tasks
  - [ ] Test error handling

### **Task Monitoring**

- [ ] **Task Status**
  - [ ] Monitor task execution
  - [ ] Check task results
  - [ ] Verify error reporting
  - [ ] Test task retry

- [ ] **Performance**
  - [ ] Monitor task performance
  - [ ] Check memory usage
  - [ ] Test concurrent tasks
  - [ ] Verify resource limits

## Error Handling Testing

### **Network Errors**

- [ ] **Connection Timeouts**
  - [ ] Test slow network conditions
  - [ ] Verify timeout handling
  - [ ] Check retry logic
  - [ ] Test fallback behavior

- [ ] **Invalid URLs**
  - [ ] Test broken links
  - [ ] Verify error reporting
  - [ ] Check graceful degradation
  - [ ] Test recovery

### **Data Errors**

- [ ] **Invalid Content**
  - [ ] Test malformed RSS feeds
  - [ ] Verify HTML parsing errors
  - [ ] Check content validation
  - [ ] Test error logging

- [ ] **Database Errors**
  - [ ] Test connection failures
  - [ ] Verify transaction rollback
  - [ ] Check data integrity
  - [ ] Test recovery procedures

## Performance Testing

### **Load Testing**

- [ ] **Concurrent Users**
  - [ ] Test multiple simultaneous users
  - [ ] Verify response times
  - [ ] Check resource usage
  - [ ] Test scalability

- [ ] **Large Datasets**
  - [ ] Test with many articles
  - [ ] Verify search performance
  - [ ] Check memory usage
  - [ ] Test database performance

### **Resource Monitoring**

- [ ] **Memory Usage**
  - [ ] Monitor memory consumption
  - [ ] Check for memory leaks
  - [ ] Test garbage collection
  - [ ] Verify memory limits

- [ ] **CPU Usage**
  - [ ] Monitor CPU utilization
  - [ ] Check processing efficiency
  - [ ] Test concurrent operations
  - [ ] Verify resource sharing

## Security Testing

### **Input Validation**

- [ ] **SQL Injection**
  - [ ] Test malicious input
  - [ ] Verify parameter sanitization
  - [ ] Check query safety
  - [ ] Test error handling

- [ ] **XSS Protection**
  - [ ] Test script injection
  - [ ] Verify output encoding
  - [ ] Check content filtering
  - [ ] Test sanitization

### **Access Control**

- [ ] **URL Access**
  - [ ] Test direct URL access
  - [ ] Verify authentication (if applicable)
  - [ ] Check authorization
  - [ ] Test access restrictions

- [ ] **API Security**
  - [ ] Test API endpoint security
  - [ ] Verify input validation
  - [ ] Check rate limiting
  - [ ] Test error handling

## Integration Testing

### **End-to-End Workflow**

- [ ] **Complete Pipeline**
  - [ ] Initialize sources
  - [ ] Collect content
  - [ ] Process articles
  - [ ] Analyze content
  - [ ] Verify results

- [ ] **Data Flow**
  - [ ] Test data consistency
  - [ ] Verify transformations
  - [ ] Check data integrity
  - [ ] Test error propagation

### **Component Integration**

- [ ] **Service Communication**
  - [ ] Test inter-service communication
  - [ ] Verify message passing
  - [ ] Check error handling
  - [ ] Test recovery

- [ ] **Data Synchronization**
  - [ ] Test data consistency
  - [ ] Verify synchronization
  - [ ] Check conflict resolution
  - [ ] Test data migration

## Documentation Testing

### **User Documentation**

- [ ] **README Verification**
  - [ ] Test installation instructions
  - [ ] Verify configuration examples
  - [ ] Check usage examples
  - [ ] Test troubleshooting guides

- [ ] **API Documentation**
  - [ ] Verify endpoint descriptions
  - [ ] Test request/response examples
  - [ ] Check parameter documentation
  - [ ] Test error documentation

### **Code Documentation**

- [ ] **Code Comments**
  - [ ] Verify inline comments
  - [ ] Check function documentation
  - [ ] Test class documentation
  - [ ] Verify module documentation

- [ ] **Configuration Files**
  - [ ] Test configuration examples
  - [ ] Verify parameter descriptions
  - [ ] Check validation rules
  - [ ] Test default values

## Final Verification

### **System Health**

- [ ] **Service Status**
  - [ ] Verify all services are running
  - [ ] Check service health
  - [ ] Test service dependencies
  - [ ] Verify service communication

- [ ] **Data Integrity**
  - [ ] Verify database integrity
  - [ ] Check data consistency
  - [ ] Test backup/restore
  - [ ] Verify data retention

### **Performance Baseline**

- [ ] **Response Times**
  - [ ] Measure typical response times
  - [ ] Check performance under load
  - [ ] Test resource utilization
  - [ ] Verify scalability

- [ ] **Resource Usage**
  - [ ] Monitor memory usage
  - [ ] Check CPU utilization
  - [ ] Test disk I/O
  - [ ] Verify network usage

## Troubleshooting

### **Common Issues**

- [ ] **Service Failures**
  1. **Check the application logs** for error messages
  2. **Verify all services are running** (PostgreSQL, Redis, Celery)
  3. **Check browser console** for JavaScript errors
  4. **Review the test documentation** for known issues
  5. **Report bugs** with detailed reproduction steps

---

**Happy Testing! 🧪✨**

## Test Results Summary

### **Passed Tests**
- [ ] List all tests that passed

### **Failed Tests**
- [ ] List any tests that failed with details

### **Issues Found**
- [ ] Document any issues discovered during testing

### **Recommendations**
- [ ] Suggest improvements based on testing results

### **Next Steps**
- [ ] Plan follow-up testing if needed
- [ ] Schedule retesting for failed items
- [ ] Update documentation based on findings


---

# Manual Software Checks — 30‑Minute Procedure

Checks that are **not** covered by existing (non-skipped) automated tests. Target: **≤30 minutes** total.

**Reference:** gaps derived from test layout (`tests/api`, `tests/ui`, `tests/cli`, `tests/integration`, `tests/playwright`), skipped-test inventory (`tests/SKIPPED_TESTS.md`, `@pytest.mark.skip`), and app surface (`src/web/routes`, `src/cli/commands`).

---

## 1. CLI help (automated)

**Covered by:** `tests/cli/test_cli_help.py` (run: `python3 run_tests.py unit --paths tests/cli/test_cli_help.py`).

Main `--help`, `collect --help`, `backup --help`, `rescore --help`, and `stats` (with mocked DB) are asserted there. No manual steps.

---

## 2. Backup API and UI (API not tested; create/restore not exercised in UI tests)

**Time: ~5 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 2.1 | Open **Settings** → Backup Configuration, expand section | Section visible; “Create Backup Now”, “List Backups”, “Check Status” present |
| 2.2 | Click **Check Status** | Status area updates (or shows “idle”/empty without error) |
| 2.3 | Click **List Backups** | List loads or “no backups”/empty state; no 5xx |
| 2.4 | Click **Create Backup Now** | Request starts; after completion, list or status reflects new backup or progress |
| 2.5 | (Optional) If a backup exists, trigger **Restore** | Restore starts or returns structured error; no unchecked exception |

---

## 3. Diags — “Run all health checks” and summary

**Time: ~3 min**

Individual diags checks (`#runDatabaseCheck`, `#runDeduplicationCheck`, etc.) are not asserted in current tests (many tests skipped for missing selectors). Manual check focuses on the single control that exists.

| Step | Action | Pass condition |
|------|--------|----------------|
| 3.1 | Go to **Diags** (`/diags`) | Page loads |
| 3.2 | Use the **single “Run all health checks”** (or equivalent) control | One or more checks run; spinner/state changes |
| 3.3 | Wait for completion | Summary or per-check result visible; no infinite loading or raw traceback in UI |

---

## 4. Articles — bulk delete (skipped in tests)

**Time: ~3 min**

(Chosen/rejected classification and related filters/bulk actions have been deprecated and removed. Bulk toolbar supports Delete only.)

| Step | Action | Pass condition |
|------|--------|----------------|
| 4.1 | Open **Articles** | List loads |
| 4.2 | Select one or more articles; open **bulk toolbar** | “Delete” action visible; no Chosen/Reject/Unclassify controls |
| 4.3 | Perform **bulk delete** on selected articles | Request completes; list updates or shows expected error |

---

## 5. RAG / Chat (send disabled when config missing — test skips)

**Time: ~2 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 5.1 | Open **Chat** (`/chat`) | Page loads |
| 5.2 | If “Send” is disabled, confirm reason (e.g. “Missing chat configuration”) | No generic crash; state is understandable |
| 5.3 | If config exists, send one short message | Reply or “no results”/error; no crash |

---

## 6. Workflow — trigger and execution list (happy path only)

**Time: ~4 min**

API/Playwright cover config and trigger endpoint; manual check stresses “see execution and list” without full E2E run.

| Step | Action | Pass condition |
|------|--------|----------------|
| 6.1 | Open **Workflow** or **Workflow Executions** | Page loads |
| 6.2 | Open **Executions** list (or equivalent) | List loads (empty or with rows) |
| 6.3 | From **Articles**, open an article and use **“Run workflow”** / trigger | Trigger succeeds (202 or success indicator); execution appears in list or “running” state visible |
| 6.4 | Open one execution (stream or detail) | Detail/stream loads or shows “completed”/“failed”; no 5xx |

---

## 7. Agent evals — load and run (skipped when “Load Eval Articles” fails)

**Time: ~3 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 7.1 | Go to **MLOps → Agent evals** (`/mlops/agent-evals` or equivalent) | Page loads |
| 7.2 | Use **“Load Eval Articles”** (or equivalent) | Table or list populates, or clear “no articles”/error; no 5xx |
| 7.3 | If articles exist, start one **subagent eval** (e.g. Hunt Query) | Run starts; status/result area updates or shows error message |

---

## 8. Sigma queue — no rules (tests skip when “No rules in queue”)

**Time: ~3 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 8.1 | Open **Sigma Queue** (or Sigma Enrich) | Page loads |
| 8.2 | With **empty queue**: open enrich/approve/reject UI | Buttons or states reflect “no rules” / disabled where expected; no crash |
| 8.3 | (If possible) **Add** one rule (e.g. YAML or “Add to queue”) | Rule appears in list or clear error shown |

---

## 9. PDF upload and ML hunt comparison (light smoke)

**Time: ~2 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 9.1 | Open **PDF Upload** (`/pdf-upload`) | Page and upload control visible |
| 9.2 | Open **ML Hunt Comparison** (`/ml-hunt-comparison`) | Page loads; key controls or “no data” state visible |

---

## Summary by area

| Area | Reason not covered by (non-skipped) tests | Manual time |
|------|------------------------------------------|-------------|
| CLI help | Covered by `tests/cli/test_cli_help.py` | 0 |
| Backup API/UI | No API tests for backup; UI doesn’t drive create/restore | ~5 min |
| Diags | Per-check selectors missing; tests skipped | ~3 min |
| Articles bulk delete | Manual check that bulk delete works | ~3 min |
| RAG send disabled | Test skips when Send disabled | ~2 min |
| Workflow trigger + list | Happy-path “trigger and see execution” | ~4 min |
| Agent evals load/run | Test skips when Load Eval Articles fails | ~3 min |
| Sigma queue empty/add | Tests skip when no rules in queue | ~3 min |
| PDF + ML hunt pages | Smoke only | ~2 min |

**Total: ~26 min** (CLI help automated)

---

## How to use

- Run in order, or pick sections by risk (e.g. Backup + CLI first).
- Record: **Pass / Fail / Blocked (reason)** per step.
- Blocked: note env/config (e.g. “no DB”, “no eval articles”) so the step can be re-run when available.


---

_Last updated: February 2025_
