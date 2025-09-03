# 🧪 Testing Your CTI Scraper Web Server

This document describes how to test and monitor your CTI Scraper web interface.

## 🚀 Quick Start

### 1. Start the Web Server
```bash
./start_web.sh
```

### 2. Run Comprehensive Tests
```bash
python test_web_server.py
```

### 3. Monitor Server Health
```bash
python monitor_web_server.py
```

## 📋 Test Coverage

The test suite covers all major web server functionality:

### ✅ **Core Pages**
- **Dashboard** (`/`) - Main overview and statistics
- **Articles** (`/articles`) - Article listing with search/filtering
- **Article Details** (`/articles/{id}`) - Individual article with TTP analysis
- **Analysis** (`/analysis`) - TTP analysis dashboard
- **Sources** (`/sources`) - Source management

### ✅ **API Endpoints**
- **Articles API** (`/api/articles`) - JSON article data
- **Analysis API** (`/api/analysis/{id}`) - TTP analysis data

### ✅ **Functionality Testing**
- **Pagination** - Page navigation and limits
- **Search** - Article search functionality
- **Filtering** - Source and quality filtering
- **Error Handling** - 404 and 500 error responses
- **Performance** - Response time monitoring

### ✅ **Content Validation**
- **Quality Assessment** - TTP quality scoring display
- **TTP Analysis** - Hunting technique detection
- **Database Integration** - Data loading and display

## 🔧 Test Scripts

### `test_web_server.py`
Comprehensive test suite that validates all web server capabilities:

```bash
# Run all tests
python test_web_server.py

# Expected output: 100% success rate
🎉 All tests passed! Your web server is working perfectly!
```

**Test Categories:**
1. **Dashboard** - Main page loading and content
2. **Articles List** - Article browsing and filtering
3. **Article Detail** - Individual article pages
4. **Analysis Dashboard** - TTP analysis interface
5. **Sources Page** - Source management interface
6. **API Endpoints** - JSON API functionality
7. **Error Handling** - 404 and error responses
8. **Performance** - Response time validation

### `monitor_web_server.py`
Real-time server health monitoring:

```bash
# Quick health check
python monitor_web_server.py

# Expected output: Excellent health status
🏥 Overall Health: 🟢 EXCELLENT
```

**Monitoring Features:**
- Server response time
- Endpoint health status
- Database accessibility
- Overall system health rating

## 🎯 Test Results Interpretation

### **Success Indicators**
- ✅ **100% Test Pass Rate** - All functionality working
- 🟢 **Excellent Health** - Server running optimally
- **Fast Response Times** - < 100ms for most endpoints
- **All Endpoints Healthy** - No 404/500 errors

### **Warning Signs**
- ⚠️ **Fair/Poor Health** - Some endpoints failing
- **Slow Response Times** - > 1000ms responses
- **Partial Database Access** - Some data not loading
- **Endpoint Errors** - 404/500 responses

### **Critical Issues**
- 🔴 **Poor Health** - Multiple endpoints failing
- **Server Down** - No response from web server
- **Database Errors** - Cannot access data
- **High Error Rates** - Many failed requests

## 🐛 Troubleshooting

### **Common Issues & Solutions**

#### 1. **Server Not Running**
```bash
❌ Web server is not running. Please start it first:
   ./start_web.sh
```
**Solution:** Start the web server using the startup script.

#### 2. **API Endpoint Errors**
```bash
❌ /api/articles: 500 (expected: 200)
```
**Solution:** Check database models and API endpoint code.

#### 3. **404 Errors Not Working**
```bash
❌ /articles/99999: 200 (expected: 404)
```
**Solution:** Verify error handling in route handlers.

#### 4. **Slow Performance**
```bash
⚠️ Some endpoints are slow
```
**Solution:** Check database queries and TTP analysis performance.

### **Debug Mode**
For detailed debugging, check the web server logs:
```bash
# View server logs
tail -f web_server.log

# Check for errors
grep ERROR web_server.log
```

## 📊 Performance Benchmarks

### **Expected Response Times**
- **Dashboard**: < 50ms
- **Articles List**: < 100ms
- **Article Detail**: < 200ms
- **Analysis**: < 500ms (due to TTP processing)
- **Sources**: < 100ms

### **Load Testing**
For basic load testing, you can run multiple concurrent requests:
```bash
# Simple load test (10 concurrent requests)
for i in {1..10}; do
  curl -s http://localhost:8000/ > /dev/null &
done
wait
```

## 🔄 Continuous Monitoring

### **Automated Health Checks**
You can set up automated monitoring:

```bash
# Check every 5 minutes
while true; do
  python monitor_web_server.py
  sleep 300
done
```

### **Integration with Monitoring Tools**
The monitoring script can be integrated with:
- **Nagios** - Enterprise monitoring
- **Prometheus** - Metrics collection
- **Grafana** - Visualization dashboards
- **Cron** - Scheduled health checks

## 📈 Test Metrics

### **Success Rate Tracking**
Track your test success rate over time:
```bash
# Run tests and log results
python test_web_server.py 2>&1 | tee test_results_$(date +%Y%m%d).log
```

### **Performance Trends**
Monitor response time trends:
```bash
# Log performance metrics
python monitor_web_server.py | grep "Response Time" >> performance.log
```

## 🎉 Success Criteria

Your web server is considered **fully operational** when:

1. **✅ All Tests Pass** - 100% success rate
2. **🟢 Excellent Health** - All endpoints responding
3. **⚡ Fast Performance** - < 100ms response times
4. **🗄️ Database Access** - Full data accessibility
5. **🔍 TTP Analysis** - Working threat hunting features

## 🚀 Next Steps

Once testing passes:

1. **Deploy to Production** - Move to production server
2. **Set Up Monitoring** - Implement automated health checks
3. **Performance Tuning** - Optimize slow endpoints
4. **Security Testing** - Add authentication/authorization
5. **Load Testing** - Test with realistic user loads

---

**🎯 Your CTI Scraper web interface is now thoroughly tested and ready for production use!**
