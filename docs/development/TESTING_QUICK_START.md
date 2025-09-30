# 🚀 Testing Quick Start

Get up and running with CTI Scraper testing in 5 minutes.

## ⚡ Prerequisites

- Docker and Docker Compose installed
- Python 3.8+ (for local testing)
- Git
- Port 8001 available (or configure `CTI_SCRAPER_URL` environment variable)

## 🎯 5-Minute Setup

### 1. Start CTI Scraper (2 minutes)

```bash
# Clone and start the application
git clone <repository-url>
cd CTIScraper
docker-compose up -d

# Verify it's running
curl http://localhost:8001/health
```

### 2. Install Test Dependencies (1 minute)

```bash
# Install Python test dependencies
pip install -r requirements-test.txt

# Install Playwright browsers
playwright install chromium
```

### 3. Run Your First Test (2 minutes)

```bash
# Quick health check
python run_tests.py --smoke

# Expected output: ✅ All smoke tests passed
```

## 🧪 Test Categories Overview

| Category | Command | Purpose | Duration |
|----------|---------|---------|----------|
| **Smoke** | `--smoke` | Quick health check | ~30s |
| **API** | `--api` | API endpoints | ~1-2m |
| **UI** | `--ui` | Web interface | ~3-5m |
| **Integration** | `--integration` | System integration | ~2-3m |
| **Coverage** | `--coverage` | Full test suite | ~5-8m |

## 🎯 Common Commands

```bash
# Run all tests
python run_tests.py --all

# Run specific category
python run_tests.py --api

# Run with coverage
python run_tests.py --coverage

# Run single test file
pytest tests/test_basic.py -v

# Run with browser visible
pytest tests/e2e/ -v --headed=true
```

## 🔍 Verify Everything Works

```bash
# 1. Check application health
curl http://localhost:8001/health

# 2. Run smoke tests
python run_tests.py --smoke

# 3. Check test results
open test-results/report.html
```

## 🚨 Troubleshooting

### **Application Not Running**
```bash
# Check Docker containers
docker ps

# Restart if needed
docker-compose restart

# Check port configuration
curl http://localhost:8001/health
# If port 8001 is in use, check docker-compose.yml port mapping
```

### **Test Dependencies Missing**
```bash
# Reinstall dependencies
pip install -r requirements-test.txt
playwright install --force
```

### **Database Issues**
```bash
# Check database
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "SELECT 1;"
```

## 📚 Next Steps

- **Learn pytest basics** → [Pytest Fundamentals](PYTEST_FUNDAMENTALS.md)
- **Understand test types** → [Test Categories](TEST_CATEGORIES.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)

## 🎉 Success Criteria

You're ready when:
- ✅ `docker-compose up -d` starts successfully
- ✅ `curl http://localhost:8001/health` returns 200
- ✅ `python run_tests.py --smoke` passes
- ✅ Test report opens in browser

**Ready to dive deeper?** Check out [Pytest Fundamentals](PYTEST_FUNDAMENTALS.md) for core concepts.
