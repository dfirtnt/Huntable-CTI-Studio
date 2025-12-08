# 🚀 CI/CD Integration

Comprehensive guide for integrating testing into CI/CD pipelines.

## 🎯 Overview

This guide covers setting up automated testing in CI/CD pipelines, including GitHub Actions, test orchestration, and quality gates.

## 🔧 GitHub Actions Setup

### Basic Workflow
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:  # Manual trigger

env:
  PYTHON_VERSION: '3.11'
  NODE_VERSION: '18'

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: cti_scraper_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache Python dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          playwright install --with-deps

      - name: Set up test environment
        run: |
          cp env.example .env
          echo "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cti_scraper_test" >> .env
          echo "REDIS_URL=redis://localhost:6379" >> .env
          echo "TESTING=true" >> .env

      - name: Run smoke tests
        run: |
          python run_tests.py --smoke

      - name: Run API tests
        run: |
          python run_tests.py --api

      - name: Run UI tests
        run: |
          python run_tests.py --ui

      - name: Run integration tests
        run: |
          python run_tests.py --integration

      - name: Run coverage tests
        run: |
          python run_tests.py --coverage

      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: test-results
          path: |
            test-results/
            htmlcov/
            playwright-report/

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./htmlcov/coverage.xml
          flags: unittests
          name: codecov-umbrella
```

### Advanced Workflow with Matrix
```yaml
# .github/workflows/ci-matrix.yml
name: CI/CD Matrix Testing

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test-matrix:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11']
        browser: [chromium, firefox, webkit]
        test-category: [smoke, api, ui, integration]
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: cti_scraper_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          playwright install --with-deps ${{ matrix.browser }}

      - name: Set up test environment
        run: |
          cp env.example .env
          echo "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cti_scraper_test" >> .env
          echo "TESTING=true" >> .env

      - name: Run ${{ matrix.test-category }} tests
        run: |
          python run_tests.py --${{ matrix.test-category }}

      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: test-results-${{ matrix.python-version }}-${{ matrix.browser }}-${{ matrix.test-category }}
          path: test-results/
```

## 🐳 Docker Integration

### Docker Compose for Testing

**Note:** Tests run against production containers (`cti_web`, `cti_postgres`, `cti_worker`) on standard ports (8001, 5432, 6379). No separate test infrastructure is used.

Tests are executed within the production Docker containers using:
```bash
docker exec cti_web pytest tests/...
```

### Docker-based Testing
```yaml
# .github/workflows/docker-ci.yml
name: Docker CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  docker-test:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build test image
        run: |
          docker build -t cti-scraper-test .

      - name: Start test services
        run: |
          docker-compose -f docker-compose.test.yml up -d
          sleep 30

      - name: Run tests in container
        run: |
          docker exec cti_web_test python run_tests.py --all

      - name: Copy test results
        run: |
          docker cp cti_web_test:/app/test-results ./test-results
          docker cp cti_web_test:/app/htmlcov ./htmlcov

      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: docker-test-results
          path: |
            test-results/
            htmlcov/

      - name: Cleanup
        if: always()
        run: |
          docker-compose -f docker-compose.test.yml down -v
```

## 📊 Quality Gates

### Coverage Requirements
```yaml
# .github/workflows/quality-gates.yml
name: Quality Gates

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  quality-gates:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          pip install coverage

      - name: Run tests with coverage
        run: |
          coverage run -m pytest tests/
          coverage report --fail-under=80
          coverage xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests
          name: codecov-umbrella

      - name: Check code quality
        run: |
          pip install flake8 black isort
          flake8 src/ tests/ --max-line-length=100 --exclude=__pycache__
          black --check src/ tests/
          isort --check-only src/ tests/

      - name: Security scan
        run: |
          pip install bandit safety
          bandit -r src/ -f json -o bandit-report.json
          safety check --json --output safety-report.json

      - name: Upload security reports
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json
```

### Performance Gates
```yaml
# .github/workflows/performance-gates.yml
name: Performance Gates

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  performance-gates:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          playwright install --with-deps

      - name: Start application
        run: |
          docker-compose up -d
          sleep 30

      - name: Run performance tests
        run: |
          python run_tests.py --performance

      - name: Check performance metrics
        run: |
          python scripts/check_performance.py \
            --max-page-load=5.0 \
            --max-api-response=2.0 \
            --max-db-query=1.0

      - name: Upload performance results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: performance-results
          path: performance-results/
```

## 🔄 Test Orchestration

### MCP Orchestrator
```python
# tests/e2e/mcp_orchestrator.py
import asyncio
import subprocess
import time
import os
from typing import Dict, List, Optional

class PlaywrightMCPOrchestrator:
    """MCP-based test orchestration for CI/CD."""
    
    def __init__(self):
        self.base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        self.timeout = 300  # 5 minutes
        
    async def health_check(self) -> bool:
        """Check if application is healthy."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", timeout=10)
                return response.status_code == 200
        except Exception:
            return False
    
    async def wait_for_application(self) -> bool:
        """Wait for application to be ready."""
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if await self.health_check():
                return True
            await asyncio.sleep(5)
        return False
    
    async def run_tests(self, test_category: str) -> Dict:
        """Run tests with MCP orchestration."""
        if not await self.wait_for_application():
            return {"success": False, "error": "Application not ready"}
        
        try:
            # Run tests
            result = subprocess.run(
                ["python", "run_tests.py", f"--{test_category}"],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Test timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def collect_artifacts(self) -> List[str]:
        """Collect test artifacts."""
        artifacts = []
        
        # Collect test results
        if os.path.exists("test-results/"):
            artifacts.append("test-results/")
        
        # Collect coverage reports
        if os.path.exists("htmlcov/"):
            artifacts.append("htmlcov/")
        
        # Collect Playwright reports
        if os.path.exists("playwright-report/"):
            artifacts.append("playwright-report/")
        
        return artifacts
```

### CI/CD Integration
```yaml
# .github/workflows/mcp-orchestration.yml
name: MCP Orchestration

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  mcp-orchestration:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          playwright install --with-deps

      - name: Start application
        run: |
          docker-compose up -d
          sleep 30

      - name: Run MCP orchestration
        run: |
          python tests/e2e/mcp_orchestrator.py

      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: mcp-test-results
          path: |
            test-results/
            htmlcov/
            playwright-report/
```

## 📈 Test Reporting

### HTML Reports
```yaml
# .github/workflows/reporting.yml
name: Test Reporting

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test-reporting:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          playwright install --with-deps

      - name: Run tests
        run: |
          python run_tests.py --all

      - name: Generate HTML report
        run: |
          python scripts/generate_html_report.py

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        if: github.ref == 'refs/heads/main'
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./test-results
```

### Slack Notifications
```yaml
# .github/workflows/slack-notifications.yml
name: Slack Notifications

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  slack-notifications:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt
          playwright install --with-deps

      - name: Run tests
        run: |
          python run_tests.py --all

      - name: Send Slack notification
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          channel: '#ci-cd'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
          fields: repo,message,commit,author,action,eventName,ref,workflow
```

## 🔒 Security Testing

### Security Scanning
```yaml
# .github/workflows/security.yml
name: Security Testing

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  security-scanning:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-test.txt

      - name: Run security tests
        run: |
          python run_tests.py --security

      - name: Bandit security scan
        run: |
          pip install bandit
          bandit -r src/ -f json -o bandit-report.json

      - name: Safety dependency scan
        run: |
          pip install safety
          safety check --json --output safety-report.json

      - name: Upload security reports
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json
```

## 🚀 Deployment Testing

### Staging Deployment
```yaml
# .github/workflows/staging-deploy.yml
name: Staging Deployment

on:
  push:
    branches: [develop]

jobs:
  staging-deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy to staging
        run: |
          # Deploy to staging environment
          echo "Deploying to staging..."

      - name: Run staging tests
        run: |
          # Run tests against staging
          python run_tests.py --staging

      - name: Health check
        run: |
          # Verify staging deployment
          curl -f https://staging.ctiscraper.com/health
```

### Production Deployment
```yaml
# .github/workflows/production-deploy.yml
name: Production Deployment

on:
  push:
    branches: [main]

jobs:
  production-deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy to production
        run: |
          # Deploy to production environment
          echo "Deploying to production..."

      - name: Run production smoke tests
        run: |
          # Run smoke tests against production
          python run_tests.py --smoke --production

      - name: Health check
        run: |
          # Verify production deployment
          curl -f https://ctiscraper.com/health
```

## 📊 Monitoring and Alerting

### Test Metrics
```python
# scripts/test_metrics.py
import json
import time
from datetime import datetime
from typing import Dict, List

class TestMetrics:
    """Collect and report test metrics."""
    
    def __init__(self):
        self.metrics = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "performance": {},
            "coverage": {}
        }
    
    def collect_test_metrics(self, test_results: Dict) -> None:
        """Collect test execution metrics."""
        self.metrics["tests"] = {
            "total": test_results.get("total", 0),
            "passed": test_results.get("passed", 0),
            "failed": test_results.get("failed", 0),
            "skipped": test_results.get("skipped", 0),
            "duration": test_results.get("duration", 0)
        }
    
    def collect_performance_metrics(self, performance_data: Dict) -> None:
        """Collect performance metrics."""
        self.metrics["performance"] = {
            "page_load_time": performance_data.get("page_load_time", 0),
            "api_response_time": performance_data.get("api_response_time", 0),
            "database_query_time": performance_data.get("database_query_time", 0)
        }
    
    def collect_coverage_metrics(self, coverage_data: Dict) -> None:
        """Collect coverage metrics."""
        self.metrics["coverage"] = {
            "total_coverage": coverage_data.get("total_coverage", 0),
            "line_coverage": coverage_data.get("line_coverage", 0),
            "branch_coverage": coverage_data.get("branch_coverage", 0)
        }
    
    def save_metrics(self, filename: str) -> None:
        """Save metrics to file."""
        with open(filename, 'w') as f:
            json.dump(self.metrics, f, indent=2)
    
    def get_summary(self) -> str:
        """Get metrics summary."""
        tests = self.metrics["tests"]
        performance = self.metrics["performance"]
        coverage = self.metrics["coverage"]
        
        return f"""
Test Summary:
- Total: {tests['total']}
- Passed: {tests['passed']}
- Failed: {tests['failed']}
- Duration: {tests['duration']}s

Performance:
- Page Load: {performance['page_load_time']}s
- API Response: {performance['api_response_time']}s
- DB Query: {performance['database_query_time']}s

Coverage:
- Total: {coverage['total_coverage']}%
- Line: {coverage['line_coverage']}%
- Branch: {coverage['branch_coverage']}%
        """
```

## 🎯 Best Practices

### CI/CD Design
- **Fast feedback** with smoke tests
- **Comprehensive validation** with full test suite
- **Quality gates** to prevent regressions
- **Artifact collection** for debugging

### Test Strategy
- **Parallel execution** for speed
- **Selective testing** based on changes
- **Environment-specific** test configurations
- **Performance monitoring** and alerting

### Maintenance
- **Regular updates** of dependencies
- **Test data management** and cleanup
- **Monitoring** of test execution time
- **Documentation** of CI/CD processes

## 📚 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Test API endpoints** → [API Testing](API_TESTING.md)
- **Debug and maintain** → [Test Maintenance](TEST_MAINTENANCE.md)

## 🔍 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Compose Testing](https://docs.docker.com/compose/test-integration/)
- [Playwright CI/CD](https://playwright.dev/docs/ci)
- [Test Automation Best Practices](https://martinfowler.com/articles/practical-test-pyramid.html)
