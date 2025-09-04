# Manual Testing Checklist

## Overview

This comprehensive testing checklist ensures all features of the CTI Scraper platform are thoroughly tested before deployment.

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

- [ ] **Source Configuration Loading**
  - [ ] Load sources from `config/sources.yaml`
  - [ ] Verify all sources are parsed correctly
  - [ ] Check source metadata is accurate
  - [ ] Confirm RSS URLs are valid

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
  - [ ] Navigate to `http://localhost:8000`
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
  curl http://localhost:8000/health
  ```
  - [ ] Verify response format
  - [ ] Check status is "healthy"
  - [ ] Verify database connection
  - [ ] Check service information

### **Articles API**

- [ ] **List Articles**
  ```bash
  curl http://localhost:8000/api/articles
  ```
  - [ ] Verify JSON response
  - [ ] Check pagination
  - [ ] Test filtering
  - [ ] Verify article data

- [ ] **Article Detail**
  ```bash
  curl http://localhost:8000/api/articles/1
  ```
  - [ ] Verify article details
  - [ ] Check metadata
  - [ ] Test error handling
  - [ ] Verify content

### **Sources API**

- [ ] **List Sources**
  ```bash
  curl http://localhost:8000/api/sources
  ```
  - [ ] Verify source list
  - [ ] Check source data
  - [ ] Test filtering
  - [ ] Verify statistics

- [ ] **Source Operations**
  ```bash
  curl -X POST http://localhost:8000/api/sources/1/toggle
  ```
  - [ ] Test source activation
  - [ ] Verify status change
  - [ ] Check error handling
  - [ ] Test invalid IDs

## CLI Testing

### **Basic Commands**

- [ ] **Help Command**
  ```bash
  python -m src.cli.main --help
  ```
  - [ ] Verify help text
  - [ ] Check command list
  - [ ] Test subcommand help
  - [ ] Verify usage examples

- [ ] **Init Command**
  ```bash
  python -m src.cli.main init --config config/sources.yaml
  ```
  - [ ] Verify source loading
  - [ ] Check database creation
  - [ ] Test validation
  - [ ] Verify error handling

### **Collection Commands**

- [ ] **Collect Command**
  ```bash
  python -m src.cli.main collect --tier 1
  ```
  - [ ] Verify content collection
  - [ ] Check progress display
  - [ ] Test error handling
  - [ ] Verify results

- [ ] **Monitor Command**
  ```bash
  python -m src.cli.main monitor --interval 300
  ```
  - [ ] Test continuous monitoring
  - [ ] Verify interval timing
  - [ ] Check log output
  - [ ] Test graceful shutdown

### **Analysis Commands**

- [ ] **Analyze Command**
  ```bash
  python -m src.cli.main analyze --recent 10
  ```
  - [ ] Verify TTP extraction
  - [ ] Check output format
  - [ ] Test confidence scoring
  - [ ] Verify quality assessment

- [ ] **Export Command**
  ```bash
  python -m src.cli.main export --format json --days 7
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
