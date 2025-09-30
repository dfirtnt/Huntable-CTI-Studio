# ⚡ Performance Testing

Comprehensive guide for performance testing of the CTI Scraper system.

## 🎯 Overview

This guide covers performance testing strategies, tools, and best practices for ensuring CTI Scraper meets performance requirements under various load conditions.

## 🏗️ Performance Testing Strategy

### Test Categories
- **Load Testing**: Normal expected load
- **Stress Testing**: Beyond normal capacity
- **Volume Testing**: Large amounts of data
- **Spike Testing**: Sudden load increases
- **Endurance Testing**: Extended periods
- **Scalability Testing**: Resource scaling

### Performance Metrics
- **Response Time**: API and page load times
- **Throughput**: Requests per second
- **Resource Utilization**: CPU, memory, disk
- **Error Rate**: Failed requests percentage
- **Concurrent Users**: Simultaneous users supported

## 🛠️ Tools and Setup

### Required Dependencies
```bash
# Install performance testing dependencies
pip install locust pytest-benchmark memory-profiler psutil
```

### Configuration
```python
# conftest.py
import pytest
import time
import psutil
from typing import Dict, List

@pytest.fixture
def performance_metrics():
    """Performance metrics collection fixture."""
    return {
        "response_times": [],
        "memory_usage": [],
        "cpu_usage": [],
        "error_count": 0
    }

@pytest.fixture
def system_monitor():
    """System resource monitoring fixture."""
    return {
        "process": psutil.Process(),
        "start_time": time.time()
    }
```

## 📊 Load Testing

### Basic Load Test
```python
import asyncio
import time
import httpx
from typing import List, Dict

class LoadTester:
    """Basic load testing implementation."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results = []
    
    async def single_request(self, endpoint: str) -> Dict:
        """Make a single request and measure performance."""
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}{endpoint}")
                end_time = time.time()
                
                return {
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "response_time": end_time - start_time,
                    "success": response.status_code == 200,
                    "error": None
                }
        except Exception as e:
            end_time = time.time()
            return {
                "endpoint": endpoint,
                "status_code": None,
                "response_time": end_time - start_time,
                "success": False,
                "error": str(e)
            }
    
    async def concurrent_requests(self, endpoint: str, concurrency: int = 10) -> List[Dict]:
        """Make concurrent requests to test load handling."""
        tasks = [self.single_request(endpoint) for _ in range(concurrency)]
        results = await asyncio.gather(*tasks)
        return results
    
    def analyze_results(self, results: List[Dict]) -> Dict:
        """Analyze load test results."""
        if not results:
            return {}
        
        response_times = [r["response_time"] for r in results if r["success"]]
        success_count = sum(1 for r in results if r["success"])
        error_count = len(results) - success_count
        
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0
        
        return {
            "total_requests": len(results),
            "successful_requests": success_count,
            "failed_requests": error_count,
            "success_rate": (success_count / len(results)) * 100,
            "avg_response_time": avg_response_time,
            "min_response_time": min_response_time,
            "max_response_time": max_response_time,
            "requests_per_second": len(results) / sum(r["response_time"] for r in results)
        }

# Test implementation
@pytest.mark.performance
async def test_api_load_performance():
    """Test API performance under load."""
    load_tester = LoadTester()
    
    # Test articles endpoint
    results = await load_tester.concurrent_requests("/api/articles", concurrency=20)
    analysis = load_tester.analyze_results(results)
    
    # Assertions
    assert analysis["success_rate"] >= 95, f"Success rate {analysis['success_rate']}% below 95%"
    assert analysis["avg_response_time"] < 2.0, f"Avg response time {analysis['avg_response_time']}s exceeds 2s"
    assert analysis["max_response_time"] < 5.0, f"Max response time {analysis['max_response_time']}s exceeds 5s"
```

### Locust Load Testing
```python
# locustfile.py
from locust import HttpUser, task, between
import random

class CTIScraperUser(HttpUser):
    """Locust user for CTI Scraper load testing."""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts."""
        self.client.verify = False
    
    @task(3)
    def view_homepage(self):
        """View homepage - most common task."""
        self.client.get("/")
    
    @task(2)
    def view_articles(self):
        """View articles page."""
        self.client.get("/articles")
    
    @task(2)
    def view_sources(self):
        """View sources page."""
        self.client.get("/sources")
    
    @task(1)
    def view_analysis(self):
        """View analysis page."""
        self.client.get("/analysis")
    
    @task(1)
    def api_articles(self):
        """Call articles API."""
        self.client.get("/api/articles")
    
    @task(1)
    def api_sources(self):
        """Call sources API."""
        self.client.get("/api/sources")
    
    @task(1)
    def search_articles(self):
        """Search articles."""
        search_terms = ["malware", "threat", "attack", "security", "vulnerability"]
        term = random.choice(search_terms)
        self.client.get(f"/api/articles?search={term}")
    
    @task(1)
    def filter_articles(self):
        """Filter articles by threat score."""
        min_score = random.randint(0, 100)
        self.client.get(f"/api/articles?min_threat_score={min_score}")

# Run with: locust -f locustfile.py --host=http://localhost:8000
```

## 🚀 Stress Testing

### Stress Test Implementation
```python
@pytest.mark.performance
async def test_stress_performance():
    """Test system behavior under stress conditions."""
    load_tester = LoadTester()
    
    # Gradually increase load
    concurrency_levels = [10, 25, 50, 100, 200]
    results = {}
    
    for concurrency in concurrency_levels:
        print(f"Testing with {concurrency} concurrent requests...")
        
        # Test multiple endpoints
        endpoints = ["/", "/articles", "/sources", "/api/articles", "/api/sources"]
        all_results = []
        
        for endpoint in endpoints:
            endpoint_results = await load_tester.concurrent_requests(endpoint, concurrency)
            all_results.extend(endpoint_results)
        
        analysis = load_tester.analyze_results(all_results)
        results[concurrency] = analysis
        
        # Check if system is still responsive
        if analysis["success_rate"] < 90:
            print(f"System degraded at {concurrency} concurrent requests")
            break
    
    # Find breaking point
    breaking_point = None
    for concurrency, analysis in results.items():
        if analysis["success_rate"] < 90:
            breaking_point = concurrency
            break
    
    # Assertions
    assert breaking_point is None or breaking_point >= 100, f"System breaks at {breaking_point} concurrent requests"
    
    # Verify performance under normal load
    normal_load = results.get(25, {})
    assert normal_load["success_rate"] >= 95, "Normal load performance degraded"
    assert normal_load["avg_response_time"] < 3.0, "Normal load response time too high"
```

## 📈 Volume Testing

### Large Dataset Testing
```python
@pytest.mark.performance
async def test_volume_performance():
    """Test performance with large datasets."""
    load_tester = LoadTester()
    
    # Test with large number of articles
    results = await load_tester.concurrent_requests("/api/articles?limit=1000", concurrency=10)
    analysis = load_tester.analyze_results(results)
    
    # Assertions for volume testing
    assert analysis["success_rate"] >= 95, "Volume test success rate too low"
    assert analysis["avg_response_time"] < 5.0, "Volume test response time too high"
    
    # Test pagination performance
    pagination_results = await load_tester.concurrent_requests("/api/articles?page=100&limit=50", concurrency=5)
    pagination_analysis = load_tester.analyze_results(pagination_results)
    
    assert pagination_analysis["success_rate"] >= 95, "Pagination performance degraded"
    assert pagination_analysis["avg_response_time"] < 3.0, "Pagination response time too high"
```

## ⚡ Spike Testing

### Sudden Load Increase
```python
@pytest.mark.performance
async def test_spike_performance():
    """Test system behavior under sudden load spikes."""
    load_tester = LoadTester()
    
    # Normal load baseline
    baseline_results = await load_tester.concurrent_requests("/api/articles", concurrency=10)
    baseline_analysis = load_tester.analyze_results(baseline_results)
    
    # Sudden spike
    spike_results = await load_tester.concurrent_requests("/api/articles", concurrency=100)
    spike_analysis = load_tester.analyze_results(spike_results)
    
    # Recovery test
    await asyncio.sleep(5)  # Wait for system to recover
    recovery_results = await load_tester.concurrent_requests("/api/articles", concurrency=10)
    recovery_analysis = load_tester.analyze_results(recovery_results)
    
    # Assertions
    assert baseline_analysis["success_rate"] >= 95, "Baseline performance degraded"
    assert spike_analysis["success_rate"] >= 80, "Spike handling performance too low"
    assert recovery_analysis["success_rate"] >= 95, "Recovery performance degraded"
    
    # Response time should not degrade too much during spike
    spike_response_ratio = spike_analysis["avg_response_time"] / baseline_analysis["avg_response_time"]
    assert spike_response_ratio < 3.0, f"Spike response time ratio {spike_response_ratio} too high"
```

## 🔄 Endurance Testing

### Extended Period Testing
```python
@pytest.mark.performance
async def test_endurance_performance():
    """Test system performance over extended periods."""
    load_tester = LoadTester()
    
    # Run for 5 minutes with steady load
    duration = 300  # 5 minutes
    start_time = time.time()
    all_results = []
    
    while time.time() - start_time < duration:
        # Make requests every 10 seconds
        results = await load_tester.concurrent_requests("/api/articles", concurrency=20)
        all_results.extend(results)
        await asyncio.sleep(10)
    
    # Analyze endurance results
    analysis = load_tester.analyze_results(all_results)
    
    # Assertions
    assert analysis["success_rate"] >= 95, "Endurance test success rate too low"
    assert analysis["avg_response_time"] < 3.0, "Endurance test response time too high"
    
    # Check for memory leaks (basic check)
    import psutil
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024  # MB
    assert memory_usage < 1000, f"Memory usage {memory_usage}MB too high"
```

## 📊 System Resource Monitoring

### Resource Usage Testing
```python
import psutil
import time
from typing import Dict, List

class SystemMonitor:
    """Monitor system resources during testing."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.metrics = []
    
    def start_monitoring(self):
        """Start resource monitoring."""
        self.metrics = []
        self.start_time = time.time()
    
    def collect_metrics(self) -> Dict:
        """Collect current system metrics."""
        cpu_percent = self.process.cpu_percent()
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # System-wide metrics
        system_cpu = psutil.cpu_percent()
        system_memory = psutil.virtual_memory()
        
        metrics = {
            "timestamp": time.time(),
            "process_cpu": cpu_percent,
            "process_memory_mb": memory_mb,
            "system_cpu": system_cpu,
            "system_memory_percent": system_memory.percent,
            "system_memory_available_gb": system_memory.available / 1024 / 1024 / 1024
        }
        
        self.metrics.append(metrics)
        return metrics
    
    def get_summary(self) -> Dict:
        """Get monitoring summary."""
        if not self.metrics:
            return {}
        
        process_cpu_values = [m["process_cpu"] for m in self.metrics]
        process_memory_values = [m["process_memory_mb"] for m in self.metrics]
        system_cpu_values = [m["system_cpu"] for m in self.metrics]
        
        return {
            "duration": time.time() - self.start_time,
            "avg_process_cpu": sum(process_cpu_values) / len(process_cpu_values),
            "max_process_cpu": max(process_cpu_values),
            "avg_process_memory_mb": sum(process_memory_values) / len(process_memory_values),
            "max_process_memory_mb": max(process_memory_values),
            "avg_system_cpu": sum(system_cpu_values) / len(system_cpu_values),
            "max_system_cpu": max(system_cpu_values)
        }

# Test implementation
@pytest.mark.performance
async def test_resource_usage():
    """Test system resource usage under load."""
    monitor = SystemMonitor()
    load_tester = LoadTester()
    
    # Start monitoring
    monitor.start_monitoring()
    
    # Run load test while monitoring
    async def monitor_and_test():
        tasks = []
        
        # Monitoring task
        async def monitor_task():
            while True:
                monitor.collect_metrics()
                await asyncio.sleep(1)
        
        # Load test task
        async def load_task():
            return await load_tester.concurrent_requests("/api/articles", concurrency=50)
        
        tasks.append(asyncio.create_task(monitor_task()))
        tasks.append(asyncio.create_task(load_task()))
        
        # Wait for load test to complete
        results = await tasks[1]
        
        # Stop monitoring
        tasks[0].cancel()
        
        return results
    
    # Run test
    results = await monitor_and_test()
    analysis = load_tester.analyze_results(results)
    summary = monitor.get_summary()
    
    # Assertions
    assert analysis["success_rate"] >= 95, "Load test success rate too low"
    assert summary["max_process_cpu"] < 80, f"Max CPU usage {summary['max_process_cpu']}% too high"
    assert summary["max_process_memory_mb"] < 500, f"Max memory usage {summary['max_process_memory_mb']}MB too high"
```

## 🎯 Performance Benchmarks

### Benchmark Testing
```python
import pytest
import time
from typing import Dict

class PerformanceBenchmarks:
    """Performance benchmark definitions."""
    
    BENCHMARKS = {
        "homepage_load": {"max_time": 2.0, "description": "Homepage load time"},
        "articles_page": {"max_time": 3.0, "description": "Articles page load time"},
        "api_articles": {"max_time": 1.0, "description": "Articles API response time"},
        "api_sources": {"max_time": 1.0, "description": "Sources API response time"},
        "search_articles": {"max_time": 2.0, "description": "Article search response time"},
        "concurrent_users": {"min_users": 50, "description": "Concurrent users supported"},
        "throughput": {"min_rps": 100, "description": "Requests per second"}
    }
    
    @classmethod
    def validate_benchmark(cls, test_name: str, value: float) -> bool:
        """Validate if value meets benchmark requirements."""
        benchmark = cls.BENCHMARKS.get(test_name)
        if not benchmark:
            return True
        
        if "max_time" in benchmark:
            return value <= benchmark["max_time"]
        elif "min_users" in benchmark:
            return value >= benchmark["min_users"]
        elif "min_rps" in benchmark:
            return value >= benchmark["min_rps"]
        
        return True

# Test implementations
@pytest.mark.performance
async def test_homepage_benchmark():
    """Test homepage load time benchmark."""
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/")
        assert response.status_code == 200
    
    load_time = time.time() - start_time
    
    assert PerformanceBenchmarks.validate_benchmark("homepage_load", load_time), \
        f"Homepage load time {load_time}s exceeds benchmark"

@pytest.mark.performance
async def test_api_benchmark():
    """Test API response time benchmark."""
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/articles")
        assert response.status_code == 200
    
    response_time = time.time() - start_time
    
    assert PerformanceBenchmarks.validate_benchmark("api_articles", response_time), \
        f"API response time {response_time}s exceeds benchmark"

@pytest.mark.performance
async def test_concurrent_users_benchmark():
    """Test concurrent users benchmark."""
    load_tester = LoadTester()
    
    # Test with benchmark concurrent users
    results = await load_tester.concurrent_requests("/api/articles", concurrency=50)
    analysis = load_tester.analyze_results(results)
    
    assert PerformanceBenchmarks.validate_benchmark("concurrent_users", 50), \
        "Concurrent users benchmark not met"
    assert analysis["success_rate"] >= 95, "Concurrent users test success rate too low"
```

## 🚀 Running Performance Tests

### Basic Commands
```bash
# Run all performance tests
pytest -m performance

# Run specific performance test
pytest tests/performance/test_load.py -v

# Run with benchmark mode
pytest --benchmark-only -m performance

# Run Locust load tests
locust -f locustfile.py --host=http://localhost:8000
```

### Advanced Commands
```bash
# Run with performance profiling
pytest -m performance --profile

# Run with memory profiling
pytest -m performance --memray

# Run with custom timeout
pytest -m performance --timeout=300

# Run in parallel
pytest -m performance -n auto
```

## 📊 Performance Reports

### HTML Reports
```python
# scripts/generate_performance_report.py
import json
import time
from datetime import datetime
from typing import Dict, List

def generate_performance_report(test_results: Dict) -> str:
    """Generate HTML performance report."""
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Performance Test Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .header { background-color: #f0f0f0; padding: 20px; border-radius: 5px; }
            .metric { margin: 10px 0; padding: 10px; border-left: 4px solid #007acc; }
            .pass { border-left-color: #28a745; }
            .fail { border-left-color: #dc3545; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Performance Test Report</h1>
            <p>Generated: {timestamp}</p>
        </div>
        
        <h2>Test Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th><th>Status</th></tr>
            {summary_rows}
        </table>
        
        <h2>Detailed Results</h2>
        {detailed_results}
    </body>
    </html>
    """
    
    # Generate summary rows
    summary_rows = ""
    for metric, value in test_results.get("summary", {}).items():
        status = "PASS" if value.get("pass", False) else "FAIL"
        status_class = "pass" if value.get("pass", False) else "fail"
        summary_rows += f'<tr><td>{metric}</td><td>{value.get("value", "N/A")}</td><td class="{status_class}">{status}</td></tr>'
    
    # Generate detailed results
    detailed_results = ""
    for test_name, results in test_results.get("details", {}).items():
        detailed_results += f"<h3>{test_name}</h3>"
        detailed_results += f"<p>Success Rate: {results.get('success_rate', 0)}%</p>"
        detailed_results += f"<p>Average Response Time: {results.get('avg_response_time', 0)}s</p>"
        detailed_results += f"<p>Max Response Time: {results.get('max_response_time', 0)}s</p>"
    
    return html_template.format(
        timestamp=datetime.now().isoformat(),
        summary_rows=summary_rows,
        detailed_results=detailed_results
    )

# Usage
if __name__ == "__main__":
    # Load test results
    with open("performance-results.json", "r") as f:
        results = json.load(f)
    
    # Generate report
    report_html = generate_performance_report(results)
    
    # Save report
    with open("performance-report.html", "w") as f:
        f.write(report_html)
    
    print("Performance report generated: performance-report.html")
```

## 🎯 Best Practices

### Test Design
- **Realistic scenarios** with real data
- **Gradual load increase** to find breaking points
- **Multiple test types** for comprehensive coverage
- **Baseline establishment** for comparison

### Performance Monitoring
- **Continuous monitoring** during tests
- **Resource usage tracking** for optimization
- **Error rate monitoring** for reliability
- **Response time distribution** analysis

### Test Execution
- **Isolated environment** for consistent results
- **Repeatable tests** for reliable comparisons
- **Automated execution** in CI/CD
- **Regular performance reviews** and updates

## 📚 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)
- **Debug and maintain** → [Test Maintenance](TEST_MAINTENANCE.md)

## 🔍 Additional Resources

- [Locust Documentation](https://docs.locust.io/)
- [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
- [Performance Testing Best Practices](https://martinfowler.com/articles/practical-test-pyramid.html)
- [Load Testing Strategies](https://k6.io/docs/testing-guides/)
