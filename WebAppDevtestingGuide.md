# CTI Scraper – Web App Testing Guide

Efficient, consolidated reference for testing and validating the CTI Scraper web application across UI, API, ML, and infrastructure components.

---

## 1. Purpose

Provide a unified, reproducible testing framework for the CTI Scraper application.
Covers: end-to-end browser testing, API and database validation, ML regression, and CI/CD automation.

---

## 2. Test Stack Overview

| Layer     | Tool                              | Purpose                               |
| --------- | --------------------------------- | ------------------------------------- |
| UI        | **Playwright (Docker)**           | End-to-end workflow verification      |
| API       | **FastAPI TestClient**            | REST endpoint validation              |
| Database  | **PostgreSQL**                    | Schema and integrity tests            |
| ML        | **Pytest**                        | Regression testing for feedback loops |
| CI        | **GitHub Actions**                | Automated pipeline execution          |
| Local Dev | **Cursor IDE / Browser DevTools** | Debugging and manual testing          |

---

## 3. Environment Setup

### Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### Docker Environment

```bash
./start.sh
docker-compose ps
curl http://localhost:8001/health
```

---

## 4. Test Execution Summary

| Type            | Command                                      | Description                            |
| --------------- | -------------------------------------------- | -------------------------------------- |
| **Smoke**       | `python run_tests.py --smoke`                | Quick health check (~30s)              |
| **E2E**         | `docker-compose run web pytest tests/e2e -v` | Browser automation via Playwright      |
| **API**         | `pytest tests/api -v`                        | FastAPI endpoint validation            |
| **Database**    | `pytest tests/database -v`                   | Schema and data validation             |
| **ML Feedback** | `./scripts/run_ml_feedback_tests.sh`         | Regression and feedback loop stability |
| **Security**    | `pytest tests/security -v`                   | Bandit, safety, and dependency checks  |
| **Performance** | `pytest tests/performance -v`                | Load and profiling tests               |
| **Allure Reports** | `python run_tests.py --all`                | Generate comprehensive test reports     |
| **CI/CD**       | *GitHub Actions*                             | Auto-tests on push/pull requests       |

---

## 5. Core Test Scenarios

### Application Features

* **Smoke Tests:** Critical health checks (API endpoints, database connectivity, service status)
* **Dashboard:** load, stats, and source health
* **Articles:** listing, details, classification, and search
* **Sources:** CRUD operations, health checks, manual collection
* **AI Functions:** SIGMA rule generation, IOC extraction, RAG chat
* **ML Feedback:** probability consistency and retraining validation

### Manual UI Testing

* Navigation through all views
* Responsive layout and theme switching
* Accessibility: keyboard navigation and screen reader validation

---

## 6. Debugging

```bash
docker-compose logs -f web
docker-compose exec web bash
export LOG_LEVEL=DEBUG
```

**Browser DevTools:**

* **Console:** JavaScript errors
* **Network:** API requests and responses
* **Elements:** DOM structure
* **Sources:** Breakpoints for frontend debugging

---

## 7. Continuous Integration (GitHub Actions)

**Workflow File:** `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Tests
        run: |
          docker-compose up -d
          docker-compose run --rm web pytest -v
```

**Includes:**

* Automated testing on PRs
* Security scanning (Bandit, Safety)
* Coverage and test artifact uploads

---

## 8. Troubleshooting

| Issue                    | Resolution                                        |
| ------------------------ | ------------------------------------------------- |
| **Port conflicts**       | Check ports 8001 / 5432 / 6379                    |
| **Database not ready**   | Confirm PostgreSQL container and `.env` variables |
| **Network/API failures** | Review browser console, Docker logs               |
| **Docker errors**        | Restart Docker daemon and containers              |

---

## 9. Test Reporting

```bash
# Generate Allure reports (recommended)
python run_tests.py --all
./manage_allure.sh start
# Access at: http://localhost:8080

# Generate HTML test report
pytest --html=report.html --self-contained-html

# Generate coverage report
pytest --cov --cov-report=html
open htmlcov/index.html
```

**Allure Features:**
* Interactive dashboards with charts and trends
* Step-by-step test execution visualization
* ML/AI performance monitoring
* Historical tracking and trend analysis

Reports are saved locally or attached to GitHub Actions artifacts.

---

## 10. Best Practices

### Writing Tests

* Follow **TDD**: write tests before code changes
* Ensure **test isolation** using fixtures
* **Mock** external dependencies
* Focus on **integration and critical workflows**

### Maintenance

* Update tests with feature changes
* Track coverage and performance metrics
* Remove redundant or flaky tests
* Keep this guide aligned with repository structure

---

## 11. References

* [Docker Architecture Guide](docs/deployment/DOCKER_ARCHITECTURE.md)
* [API Endpoints Reference](docs/API_ENDPOINTS.md)
* [Testing Guide](docs/development/TESTING_GUIDE.md)

---

**Note:**
This guide mirrors the active CI/CD configuration.
Verify current scripts and paths before execution.
