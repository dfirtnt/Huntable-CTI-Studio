# 🔧 Test Maintenance

Comprehensive guide for maintaining and debugging tests in the CTI Scraper system.

## 🎯 Overview

This guide covers test maintenance strategies, debugging techniques, and best practices for keeping the test suite healthy and reliable.

## 🐛 Debugging Failed Tests

### Common Test Failures

#### 1. Application Not Running
```bash
# Check if application is running
curl http://localhost:8000/health

# Check Docker containers
docker ps

# Restart if needed
docker-compose restart
```

#### 2. Database Issues
```bash
# Check database connectivity
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "SELECT 1;"

# Check database logs
docker logs cti_postgres

# Reset test database
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

#### 3. Test Dependencies Missing
```bash
# Reinstall dependencies
pip install -r requirements-test.txt
playwright install --force

# Check Python environment
python --version
pip list
```

#### 4. Browser Issues
```bash
# Reinstall Playwright browsers
playwright install --force

# Check browser installation
playwright --version

# Run with visible browser
pytest -m ui --headed=true
```

### Debug Commands

#### Basic Debugging
```bash
# Run with verbose output
pytest -v -s

# Run with debug logging
pytest --log-cli-level=DEBUG

# Run single test with debug
pytest tests/test_basic.py::test_article_creation -v -s

# Run with traceback
pytest --tb=long
```

#### Advanced Debugging
```bash
# Run with pdb debugger
pytest --pdb

# Run with pdb on failure
pytest --pdbcls=IPython.terminal.debugger:Pdb

# Run with coverage and debug
pytest --cov=src --cov-report=html --pdb

# Run with memory profiling
pytest --memray
```

### Debug Mode Examples

#### Python Debugger
```python
import pdb

def test_debug_example():
    """Example of using pdb for debugging."""
    result = some_function()
    
    # Set breakpoint
    pdb.set_trace()
    
    # Inspect variables
    print(f"Result: {result}")
    
    assert result is not None
```

#### Playwright Debug Mode
```python
@pytest.mark.ui
async def test_debug_ui(page: Page):
    """Example of debugging UI tests."""
    await page.goto("http://localhost:8000/")
    
    # Pause for manual inspection
    await page.pause()
    
    # Check element state
    element = page.locator("h1")
    print(f"Element visible: {await element.is_visible()}")
    print(f"Element text: {await element.text_content()}")
    
    await expect(element).to_be_visible()
```

#### Async Debug Mode
```python
import asyncio

@pytest.mark.asyncio
async def test_debug_async():
    """Example of debugging async tests."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/articles")
        
        # Debug response
        print(f"Status: {response.status_code}")
        print(f"Headers: {response.headers}")
        print(f"Content: {response.text}")
        
        assert response.status_code == 200
```

## 🔍 Test Analysis

### Test Execution Analysis
```python
# scripts/analyze_tests.py
import json
import subprocess
from typing import Dict, List

class TestAnalyzer:
    """Analyze test execution and identify issues."""
    
    def __init__(self):
        self.results = {}
    
    def run_test_analysis(self) -> Dict:
        """Run comprehensive test analysis."""
        # Run tests with JSON output
        result = subprocess.run([
            "pytest", 
            "--json-report", 
            "--json-report-file=test-results.json",
            "-v"
        ], capture_output=True, text=True)
        
        # Load results
        with open("test-results.json", "r") as f:
            self.results = json.load(f)
        
        return self.analyze_results()
    
    def analyze_results(self) -> Dict:
        """Analyze test results for issues."""
        analysis = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "slow_tests": [],
            "flaky_tests": [],
            "error_patterns": {},
            "recommendations": []
        }
        
        for test in self.results.get("tests", []):
            analysis["total_tests"] += 1
            
            if test["outcome"] == "passed":
                analysis["passed"] += 1
            elif test["outcome"] == "failed":
                analysis["failed"] += 1
            elif test["outcome"] == "skipped":
                analysis["skipped"] += 1
            
            # Identify slow tests
            if test.get("duration", 0) > 10:  # 10 seconds
                analysis["slow_tests"].append({
                    "name": test["nodeid"],
                    "duration": test["duration"]
                })
            
            # Identify error patterns
            if test["outcome"] == "failed":
                error = test.get("call", {}).get("longrepr", "")
                if "timeout" in error.lower():
                    analysis["error_patterns"]["timeout"] = analysis["error_patterns"].get("timeout", 0) + 1
                elif "connection" in error.lower():
                    analysis["error_patterns"]["connection"] = analysis["error_patterns"].get("connection", 0) + 1
                elif "assertion" in error.lower():
                    analysis["error_patterns"]["assertion"] = analysis["error_patterns"].get("assertion", 0) + 1
        
        # Generate recommendations
        if analysis["failed"] > 0:
            analysis["recommendations"].append("Investigate failed tests")
        
        if len(analysis["slow_tests"]) > 0:
            analysis["recommendations"].append("Optimize slow tests")
        
        if analysis["error_patterns"].get("timeout", 0) > 0:
            analysis["recommendations"].append("Increase timeouts or fix performance issues")
        
        return analysis

# Usage
if __name__ == "__main__":
    analyzer = TestAnalyzer()
    analysis = analyzer.run_test_analysis()
    
    print("Test Analysis Results:")
    print(f"Total Tests: {analysis['total_tests']}")
    print(f"Passed: {analysis['passed']}")
    print(f"Failed: {analysis['failed']}")
    print(f"Skipped: {analysis['skipped']}")
    
    if analysis["slow_tests"]:
        print("\nSlow Tests:")
        for test in analysis["slow_tests"]:
            print(f"  {test['name']}: {test['duration']}s")
    
    if analysis["recommendations"]:
        print("\nRecommendations:")
        for rec in analysis["recommendations"]:
            print(f"  - {rec}")
```

### Flaky Test Detection
```python
# scripts/detect_flaky_tests.py
import subprocess
import json
from typing import Dict, List

class FlakyTestDetector:
    """Detect flaky tests by running them multiple times."""
    
    def __init__(self, runs: int = 5):
        self.runs = runs
        self.results = {}
    
    def detect_flaky_tests(self, test_pattern: str = None) -> Dict:
        """Detect flaky tests by running them multiple times."""
        if test_pattern:
            test_cmd = ["pytest", "-k", test_pattern, "--json-report", "--json-report-file=flaky-results.json"]
        else:
            test_cmd = ["pytest", "--json-report", "--json-report-file=flaky-results.json"]
        
        results = []
        
        for run in range(self.runs):
            print(f"Run {run + 1}/{self.runs}")
            result = subprocess.run(test_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                with open("flaky-results.json", "r") as f:
                    run_results = json.load(f)
                    results.append(run_results)
        
        return self.analyze_flakiness(results)
    
    def analyze_flakiness(self, results: List[Dict]) -> Dict:
        """Analyze test results for flakiness."""
        test_outcomes = {}
        
        # Collect outcomes for each test
        for run_result in results:
            for test in run_result.get("tests", []):
                test_name = test["nodeid"]
                if test_name not in test_outcomes:
                    test_outcomes[test_name] = []
                test_outcomes[test_name].append(test["outcome"])
        
        # Identify flaky tests
        flaky_tests = []
        for test_name, outcomes in test_outcomes.items():
            if len(outcomes) < self.runs:
                continue
            
            # Check if outcomes are inconsistent
            unique_outcomes = set(outcomes)
            if len(unique_outcomes) > 1:
                flaky_tests.append({
                    "name": test_name,
                    "outcomes": outcomes,
                    "flakiness_score": len(unique_outcomes) / len(outcomes)
                })
        
        return {
            "total_tests": len(test_outcomes),
            "flaky_tests": flaky_tests,
            "flakiness_rate": len(flaky_tests) / len(test_outcomes) if test_outcomes else 0
        }

# Usage
if __name__ == "__main__":
    detector = FlakyTestDetector(runs=5)
    flakiness_report = detector.detect_flaky_tests()
    
    print("Flaky Test Detection Results:")
    print(f"Total Tests: {flakiness_report['total_tests']}")
    print(f"Flaky Tests: {len(flakiness_report['flaky_tests'])}")
    print(f"Flakiness Rate: {flakiness_report['flakiness_rate']:.2%}")
    
    if flakiness_report["flaky_tests"]:
        print("\nFlaky Tests:")
        for test in flakiness_report["flaky_tests"]:
            print(f"  {test['name']}: {test['outcomes']} (score: {test['flakiness_score']:.2f})")
```

## 🔄 Test Maintenance Strategies

### Regular Maintenance Tasks

#### 1. Test Data Cleanup
```python
# scripts/cleanup_test_data.py
import os
import shutil
from pathlib import Path

def cleanup_test_data():
    """Clean up test data and artifacts."""
    cleanup_paths = [
        "test-results/",
        "htmlcov/",
        "playwright-report/",
        "coverage.xml",
        "test-results.json",
        "flaky-results.json"
    ]
    
    for path in cleanup_paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
                print(f"Removed directory: {path}")
            else:
                os.remove(path)
                print(f"Removed file: {path}")

if __name__ == "__main__":
    cleanup_test_data()
```

#### 2. Dependency Updates
```bash
# Update test dependencies
pip install --upgrade -r requirements-test.txt

# Update Playwright browsers
playwright install --force

# Check for security vulnerabilities
pip install safety
safety check

# Check for outdated packages
pip install pip-review
pip-review --local --auto
```

#### 3. Test Environment Reset
```bash
# Reset test environment
docker-compose down
docker-compose up -d
sleep 30

# Reset test database
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Reinstall dependencies
pip install -r requirements-test.txt
playwright install --force
```

### Test Health Monitoring
```python
# scripts/test_health_monitor.py
import json
import subprocess
from datetime import datetime
from typing import Dict

class TestHealthMonitor:
    """Monitor test suite health over time."""
    
    def __init__(self):
        self.health_data = []
    
    def run_health_check(self) -> Dict:
        """Run comprehensive health check."""
        start_time = datetime.now()
        
        # Run smoke tests
        smoke_result = subprocess.run([
            "python", "run_tests.py", "--smoke"
        ], capture_output=True, text=True)
        
        # Run API tests
        api_result = subprocess.run([
            "python", "run_tests.py", "--api"
        ], capture_output=True, text=True)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        health_status = {
            "timestamp": start_time.isoformat(),
            "duration": duration,
            "smoke_tests": {
                "passed": smoke_result.returncode == 0,
                "output": smoke_result.stdout,
                "errors": smoke_result.stderr
            },
            "api_tests": {
                "passed": api_result.returncode == 0,
                "output": api_result.stdout,
                "errors": api_result.stderr
            },
            "overall_health": smoke_result.returncode == 0 and api_result.returncode == 0
        }
        
        self.health_data.append(health_status)
        return health_status
    
    def get_health_trends(self) -> Dict:
        """Analyze health trends over time."""
        if len(self.health_data) < 2:
            return {"message": "Insufficient data for trend analysis"}
        
        recent_data = self.health_data[-10:]  # Last 10 checks
        
        trends = {
            "total_checks": len(recent_data),
            "success_rate": sum(1 for d in recent_data if d["overall_health"]) / len(recent_data),
            "avg_duration": sum(d["duration"] for d in recent_data) / len(recent_data),
            "smoke_success_rate": sum(1 for d in recent_data if d["smoke_tests"]["passed"]) / len(recent_data),
            "api_success_rate": sum(1 for d in recent_data if d["api_tests"]["passed"]) / len(recent_data)
        }
        
        return trends
    
    def save_health_data(self, filename: str = "test-health.json"):
        """Save health data to file."""
        with open(filename, "w") as f:
            json.dump(self.health_data, f, indent=2)

# Usage
if __name__ == "__main__":
    monitor = TestHealthMonitor()
    health_status = monitor.run_health_check()
    
    print("Test Health Check Results:")
    print(f"Overall Health: {'PASS' if health_status['overall_health'] else 'FAIL'}")
    print(f"Duration: {health_status['duration']:.2f}s")
    print(f"Smoke Tests: {'PASS' if health_status['smoke_tests']['passed'] else 'FAIL'}")
    print(f"API Tests: {'PASS' if health_status['api_tests']['passed'] else 'FAIL'}")
    
    # Save data
    monitor.save_health_data()
    
    # Show trends
    trends = monitor.get_health_trends()
    if "success_rate" in trends:
        print(f"\nHealth Trends:")
        print(f"Success Rate: {trends['success_rate']:.2%}")
        print(f"Average Duration: {trends['avg_duration']:.2f}s")
```

## 🚀 Test Optimization

### Performance Optimization
```python
# scripts/optimize_tests.py
import time
import subprocess
from typing import Dict, List

class TestOptimizer:
    """Optimize test execution performance."""
    
    def __init__(self):
        self.benchmarks = {}
    
    def benchmark_tests(self) -> Dict:
        """Benchmark test execution times."""
        test_categories = ["smoke", "api", "ui", "integration"]
        benchmarks = {}
        
        for category in test_categories:
            start_time = time.time()
            
            result = subprocess.run([
                "python", "run_tests.py", f"--{category}"
            ], capture_output=True, text=True)
            
            end_time = time.time()
            duration = end_time - start_time
            
            benchmarks[category] = {
                "duration": duration,
                "success": result.returncode == 0,
                "output": result.stdout,
                "errors": result.stderr
            }
        
        self.benchmarks = benchmarks
        return benchmarks
    
    def identify_slow_tests(self) -> List[Dict]:
        """Identify slow tests for optimization."""
        # Run tests with timing
        result = subprocess.run([
            "pytest", "--durations=10", "--json-report", "--json-report-file=timing-results.json"
        ], capture_output=True, text=True)
        
        # Load results
        import json
        with open("timing-results.json", "r") as f:
            results = json.load(f)
        
        slow_tests = []
        for test in results.get("tests", []):
            if test.get("duration", 0) > 5:  # 5 seconds
                slow_tests.append({
                    "name": test["nodeid"],
                    "duration": test["duration"],
                    "outcome": test["outcome"]
                })
        
        return sorted(slow_tests, key=lambda x: x["duration"], reverse=True)
    
    def generate_optimization_recommendations(self) -> List[str]:
        """Generate optimization recommendations."""
        recommendations = []
        
        # Check benchmarks
        if self.benchmarks:
            for category, data in self.benchmarks.items():
                if data["duration"] > 300:  # 5 minutes
                    recommendations.append(f"Optimize {category} tests - duration {data['duration']:.2f}s exceeds 5 minutes")
        
        # Check slow tests
        slow_tests = self.identify_slow_tests()
        if slow_tests:
            recommendations.append(f"Optimize {len(slow_tests)} slow tests (>{slow_tests[0]['duration']:.2f}s)")
        
        # General recommendations
        recommendations.extend([
            "Use parallel test execution (pytest -n auto)",
            "Implement test data caching",
            "Use fixtures for common setup",
            "Mock external dependencies",
            "Optimize database queries in tests"
        ])
        
        return recommendations

# Usage
if __name__ == "__main__":
    optimizer = TestOptimizer()
    
    # Benchmark tests
    benchmarks = optimizer.benchmark_tests()
    
    print("Test Performance Benchmarks:")
    for category, data in benchmarks.items():
        status = "PASS" if data["success"] else "FAIL"
        print(f"{category}: {data['duration']:.2f}s ({status})")
    
    # Get optimization recommendations
    recommendations = optimizer.generate_optimization_recommendations()
    
    print("\nOptimization Recommendations:")
    for rec in recommendations:
        print(f"  - {rec}")
```

### Test Data Management
```python
# scripts/manage_test_data.py
import os
import json
from pathlib import Path
from typing import Dict, List

class TestDataManager:
    """Manage test data and fixtures."""
    
    def __init__(self):
        self.test_data_dir = Path("tests/data")
        self.fixtures_dir = Path("tests/fixtures")
    
    def create_test_data(self, data_type: str, count: int = 10) -> List[Dict]:
        """Create test data for testing."""
        from faker import Faker
        fake = Faker()
        
        if data_type == "articles":
            return [
                {
                    "title": fake.sentence(),
                    "content": fake.text(),
                    "url": fake.url(),
                    "author": fake.name(),
                    "published_date": fake.date_time().isoformat(),
                    "threat_score": fake.random_int(min=0, max=100)
                }
                for _ in range(count)
            ]
        elif data_type == "sources":
            return [
                {
                    "name": fake.company(),
                    "url": fake.url(),
                    "type": fake.random_element(elements=("rss", "atom", "json")),
                    "active": fake.boolean()
                }
                for _ in range(count)
            ]
        
        return []
    
    def save_test_data(self, data: List[Dict], filename: str):
        """Save test data to file."""
        self.test_data_dir.mkdir(exist_ok=True)
        
        filepath = self.test_data_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"Saved test data to {filepath}")
    
    def load_test_data(self, filename: str) -> List[Dict]:
        """Load test data from file."""
        filepath = self.test_data_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"Test data file not found: {filepath}")
        
        with open(filepath, "r") as f:
            return json.load(f)
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old test data files."""
        import time
        
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        
        cleaned_files = []
        for filepath in self.test_data_dir.glob("*.json"):
            if filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                cleaned_files.append(str(filepath))
        
        if cleaned_files:
            print(f"Cleaned up {len(cleaned_files)} old test data files")
        else:
            print("No old test data files to clean up")

# Usage
if __name__ == "__main__":
    manager = TestDataManager()
    
    # Create and save test data
    articles_data = manager.create_test_data("articles", 20)
    manager.save_test_data(articles_data, "sample_articles.json")
    
    sources_data = manager.create_test_data("sources", 10)
    manager.save_test_data(sources_data, "sample_sources.json")
    
    # Clean up old data
    manager.cleanup_old_data(30)
```

## 🎯 Best Practices

### Test Maintenance
- **Regular cleanup** of test data and artifacts
- **Dependency updates** for security and performance
- **Health monitoring** to catch issues early
- **Performance optimization** for faster feedback

### Debugging
- **Use appropriate tools** for different types of issues
- **Isolate problems** by running specific tests
- **Check system state** before debugging tests
- **Document solutions** for future reference

### Optimization
- **Profile slow tests** and optimize bottlenecks
- **Use parallel execution** where possible
- **Cache test data** to reduce setup time
- **Mock external dependencies** for faster tests

## 📚 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Test API endpoints** → [API Testing](API_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)

## 🔍 Additional Resources

- [pytest Debugging](https://docs.pytest.org/en/stable/usage.html#debugging)
- [Playwright Debugging](https://playwright.dev/docs/debug)
- [Test Maintenance Best Practices](https://martinfowler.com/articles/practical-test-pyramid.html)
- [Flaky Test Management](https://docs.pytest.org/en/stable/flaky.html)
