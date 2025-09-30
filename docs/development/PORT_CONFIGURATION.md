# 🔌 Port Configuration

Configuration guide for CTI Scraper ports and testing.

## 🎯 Default Configuration

### **Application Ports**
- **Web Application**: Port 8001 (inside container)
- **Host Mapping**: Port 8001 (mapped to container port 8001)
- **Database**: Port 5432
- **Redis**: Port 6379
- **Ollama**: Port 11434
- **Nginx**: Port 8080 (HTTP), 8443 (HTTPS)

### **Docker Compose Configuration**
```yaml
# docker-compose.yml
web:
  ports:
    - "8001:8001"  # Host:Container
  command: uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --reload
```

## 🔧 Port Configuration Options

### **1. Default Setup (Recommended)**
```yaml
# docker-compose.yml
ports:
  - "8001:8001"
```

**Access URLs:**
- Application: `http://localhost:8001`
- Health Check: `http://localhost:8001/health`
- API: `http://localhost:8001/api/articles`

### **2. Custom Host Port**
```yaml
# docker-compose.yml
ports:
  - "8002:8001"  # Use different host port
```

**Access URLs:**
- Application: `http://localhost:8001`
- Health Check: `http://localhost:8001/health`
- API: `http://localhost:8001/api/articles`

### **3. Environment Variable Configuration**
```bash
# .env
CTI_SCRAPER_URL=http://localhost:8001  # Custom port
```

**Test Configuration:**
```python
# conftest.py
import os

@pytest.fixture
async def async_client():
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    async with httpx.AsyncClient(base_url=base_url) as client:
        yield client
```

## 🧪 Testing Configuration

### **Test Environment Variables**
```bash
# .env
TESTING=true
CTI_SCRAPER_URL=http://localhost:8001  # Default
DATABASE_URL=postgresql://user:pass@postgres/test_db
REDIS_URL=redis://localhost:6379
```

### **Test Examples**
```python
# API Testing
@pytest.mark.api
async def test_articles_api(async_client):
    response = await async_client.get("/api/articles")
    assert response.status_code == 200

# UI Testing
@pytest.mark.ui
async def test_homepage_loads(page):
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    await page.goto(base_url)
    await expect(page).to_have_title("CTI Scraper")
```

### **Performance Testing**
```python
# Load Testing
class LoadTester:
    def __init__(self, base_url: str = None):
        if base_url is None:
            base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        self.base_url = base_url
```

## 🚨 Port Conflict Resolution

### **Common Issues**

#### **Port 8001 Already in Use**
```bash
# Check what's using port 8001
lsof -i :8001

# Kill process if needed
kill -9 <PID>

# Or use different port
# Update docker-compose.yml
ports:
  - "8001:8001"
```

#### **Test Failures Due to Wrong Port**
```bash
# Check current port mapping
docker ps

# Verify application is accessible
curl http://localhost:8001/health

# Update environment variable if needed
export CTI_SCRAPER_URL=http://localhost:8001
```

### **Troubleshooting Commands**
```bash
# Check Docker port mapping
docker port cti_web

# Check application health
curl http://localhost:8001/health

# Check if port is accessible
telnet localhost 8001

# List all listening ports
netstat -tlnp | grep :8001
```

## 🔄 Port Changes

### **Changing Host Port**
1. **Update docker-compose.yml:**
   ```yaml
   ports:
     - "8002:8001"  # New host port
   ```

2. **Update environment variables:**
   ```bash
   export CTI_SCRAPER_URL=http://localhost:8001
   ```

3. **Restart containers:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

4. **Verify changes:**
   ```bash
   curl http://localhost:8001/health
   ```

### **Changing Container Port**
1. **Update docker-compose.yml:**
   ```yaml
   ports:
     - "8001:8002"  # New container port
   command: uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001 --reload
   ```

2. **Update environment variables:**
   ```bash
   export CTI_SCRAPER_URL=http://localhost:8001
   ```

3. **Restart containers:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

## 📊 Port Monitoring

### **Health Check Script**
```bash
#!/bin/bash
# check_ports.sh

echo "Checking CTI Scraper ports..."

# Check web application
if curl -s http://localhost:8001/health > /dev/null; then
    echo "✅ Web application (8001): OK"
else
    echo "❌ Web application (8001): FAILED"
fi

# Check database
if docker exec cti_postgres pg_isready -U cti_user > /dev/null 2>&1; then
    echo "✅ Database (5432): OK"
else
    echo "❌ Database (5432): FAILED"
fi

# Check Redis
if docker exec cti_redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis (6379): OK"
else
    echo "❌ Redis (6379): FAILED"
fi

# Check Ollama
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "✅ Ollama (11434): OK"
else
    echo "❌ Ollama (11434): FAILED"
fi
```

### **Port Usage Monitoring**
```bash
# Monitor port usage
watch -n 5 'netstat -tlnp | grep -E ":(8001|5432|6379|11434)"'

# Check Docker port mappings
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

## 🎯 Best Practices

### **Development**
- **Use default port 8001** for consistency
- **Set environment variables** for port configuration
- **Document port changes** in team communications
- **Use health checks** to verify port accessibility

### **Testing**
- **Make ports configurable** via environment variables
- **Use consistent port mapping** across test environments
- **Verify port accessibility** before running tests
- **Handle port conflicts** gracefully

### **Production**
- **Use reverse proxy** (Nginx) for port management
- **Configure SSL/TLS** for secure connections
- **Monitor port usage** and performance
- **Document port requirements** for deployment

## 📚 Additional Resources

- [Docker Port Mapping](https://docs.docker.com/compose/networking/)
- [Environment Variables](https://docs.docker.com/compose/environment-variables/)
- [Health Checks](https://docs.docker.com/compose/compose-file/compose-file-v3/#healthcheck)
- [Network Troubleshooting](https://docs.docker.com/network/network-troubleshoot/)
