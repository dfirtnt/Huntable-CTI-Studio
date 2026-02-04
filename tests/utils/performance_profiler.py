"""
Performance profiling utilities for test optimization.

This module provides comprehensive performance monitoring and profiling
capabilities for identifying slow tests and performance bottlenecks.
"""

import asyncio
import cProfile
import json
import logging
import pstats
import sys
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a test or operation."""

    test_name: str
    start_time: float
    end_time: float
    duration: float
    cpu_percent: float
    memory_usage: float
    memory_peak: float
    function_calls: int
    line_count: int
    slow_operations: list[dict[str, Any]] = field(default_factory=list)
    bottlenecks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ProfilingConfig:
    """Configuration for performance profiling."""

    enable_cpu_profiling: bool = True
    enable_memory_profiling: bool = True
    enable_line_profiling: bool = False
    slow_test_threshold: float = 1.0  # seconds
    memory_threshold: float = 100.0  # MB
    cpu_threshold: float = 80.0  # percent
    profile_output_dir: str = "test-results/profiling"
    save_profiles: bool = True
    generate_reports: bool = True


class PerformanceProfiler:
    """Main performance profiler for tests."""

    def __init__(self, config: ProfilingConfig | None = None):
        self.config = config or ProfilingConfig()
        self.active_profiles: dict[str, Any] = {}
        self.profile_results: list[PerformanceMetrics] = []
        self.monitoring_active = False
        self._monitor_thread: threading.Thread | None = None
        self._monitor_stop_event = threading.Event()

        # Create output directory
        self.output_dir = Path(self.config.profile_output_dir)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except (FileNotFoundError, OSError):
            # If directory creation fails, use current directory as fallback
            self.output_dir = Path.cwd() / "profiling_fallback"
            self.output_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def profile_test(self, test_name: str):
        """Context manager to profile a test."""
        profile_data = {
            "test_name": test_name,
            "start_time": time.time(),
            "profiler": None,
            "memory_start": 0,
            "memory_peak": 0,
            "cpu_samples": [],
            "memory_samples": [],
        }

        # Start profiling
        if self.config.enable_cpu_profiling:
            profile_data["profiler"] = cProfile.Profile()
            profile_data["profiler"].enable()

        # Start memory monitoring
        if self.config.enable_memory_profiling:
            process = psutil.Process()
            profile_data["memory_start"] = process.memory_info().rss / 1024 / 1024  # MB

        # Start system monitoring
        if self.monitoring_active:
            self._start_monitoring_for_test(test_name)

        try:
            yield profile_data
        finally:
            # Stop profiling
            if profile_data["profiler"]:
                profile_data["profiler"].disable()

            # Calculate metrics
            metrics = self._calculate_metrics(test_name, profile_data)

            # Save profile data
            if self.config.save_profiles:
                self._save_profile_data(test_name, profile_data, metrics)

            # Add to results
            self.profile_results.append(metrics)

            # Generate recommendations
            self._generate_recommendations(metrics)

    def _calculate_metrics(self, test_name: str, profile_data: dict[str, Any]) -> PerformanceMetrics:
        """Calculate performance metrics from profile data."""
        end_time = time.time()
        duration = end_time - profile_data["start_time"]

        # Calculate CPU usage
        cpu_percent = 0.0
        if profile_data["cpu_samples"]:
            cpu_percent = sum(profile_data["cpu_samples"]) / len(profile_data["cpu_samples"])

        # Calculate memory usage
        memory_usage = profile_data["memory_start"]
        memory_peak = profile_data["memory_peak"]

        if profile_data["memory_samples"]:
            memory_usage = sum(profile_data["memory_samples"]) / len(profile_data["memory_samples"])
            memory_peak = max(profile_data["memory_samples"])

        # Analyze profiler data
        function_calls = 0
        line_count = 0

        if profile_data["profiler"]:
            stats = pstats.Stats(profile_data["profiler"])
            stats.sort_stats("cumulative")

            # Get function call statistics
            function_calls = stats.total_calls
            line_count = len(stats.stats)

        return PerformanceMetrics(
            test_name=test_name,
            start_time=profile_data["start_time"],
            end_time=end_time,
            duration=duration,
            cpu_percent=cpu_percent,
            memory_usage=memory_usage,
            memory_peak=memory_peak,
            function_calls=function_calls,
            line_count=line_count,
        )

    def _save_profile_data(self, test_name: str, profile_data: dict[str, Any], metrics: PerformanceMetrics):
        """Save profile data to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{test_name}_{timestamp}"

        # Save CPU profile
        if profile_data["profiler"]:
            profile_file = self.output_dir / f"{base_name}.prof"
            profile_data["profiler"].dump_stats(str(profile_file))

        # Save metrics as JSON
        metrics_file = self.output_dir / f"{base_name}_metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(
                {
                    "test_name": metrics.test_name,
                    "duration": metrics.duration,
                    "cpu_percent": metrics.cpu_percent,
                    "memory_usage": metrics.memory_usage,
                    "memory_peak": metrics.memory_peak,
                    "function_calls": metrics.function_calls,
                    "line_count": metrics.line_count,
                    "slow_operations": metrics.slow_operations,
                    "bottlenecks": metrics.bottlenecks,
                    "recommendations": metrics.recommendations,
                },
                f,
                indent=2,
            )

        logger.debug(f"Profile data saved for {test_name}")

    def _generate_recommendations(self, metrics: PerformanceMetrics):
        """Generate performance recommendations."""
        recommendations = []

        # Duration recommendations
        if metrics.duration > self.config.slow_test_threshold:
            recommendations.append(
                f"Test is slow ({metrics.duration:.2f}s). Consider optimizing or mocking external dependencies."
            )

        # Memory recommendations
        if metrics.memory_usage > self.config.memory_threshold:
            recommendations.append(
                f"High memory usage ({metrics.memory_usage:.1f}MB). Check for memory leaks or large data structures."
            )

        if metrics.memory_peak > metrics.memory_usage * 2:
            recommendations.append(
                f"High memory peak ({metrics.memory_peak:.1f}MB). Consider reducing data size or using generators."
            )

        # CPU recommendations
        if metrics.cpu_percent > self.config.cpu_threshold:
            recommendations.append(
                f"High CPU usage ({metrics.cpu_percent:.1f}%). Consider optimizing algorithms or using async operations."
            )

        # Function call recommendations
        if metrics.function_calls > 10000:
            recommendations.append(
                f"Many function calls ({metrics.function_calls}). Consider reducing complexity or using caching."
            )

        metrics.recommendations = recommendations

    def start_monitoring(self, interval: float = 0.1):
        """Start system monitoring."""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self._monitor_stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_system, args=(interval,), daemon=True)
        self._monitor_thread.start()

        logger.debug("Performance monitoring started")

    def stop_monitoring(self):
        """Stop system monitoring."""
        if not self.monitoring_active:
            return

        self.monitoring_active = False
        self._monitor_stop_event.set()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)

        logger.debug("Performance monitoring stopped")

    def _monitor_system(self, interval: float):
        """Monitor system performance."""
        process = psutil.Process()

        while not self._monitor_stop_event.is_set():
            try:
                # Collect CPU and memory data
                cpu_percent = process.cpu_percent()
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024

                # Store samples for active profiles
                for profile_data in self.active_profiles.values():
                    if "cpu_samples" in profile_data:
                        profile_data["cpu_samples"].append(cpu_percent)
                    if "memory_samples" in profile_data:
                        profile_data["memory_samples"].append(memory_mb)
                        profile_data["memory_peak"] = max(profile_data["memory_peak"], memory_mb)

                time.sleep(interval)

            except Exception as e:
                logger.error(f"Error in monitoring thread: {e}")
                time.sleep(interval)

    def _start_monitoring_for_test(self, test_name: str):
        """Start monitoring for a specific test."""
        self.active_profiles[test_name] = {
            "cpu_samples": [],
            "memory_samples": [],
            "memory_peak": 0,
        }

    def generate_performance_report(self) -> dict[str, Any]:
        """Generate a comprehensive performance report."""
        if not self.profile_results:
            return {"status": "no_data", "message": "No performance data available"}

        # Calculate summary statistics
        durations = [m.duration for m in self.profile_results]
        memory_usage = [m.memory_usage for m in self.profile_results]
        cpu_usage = [m.cpu_percent for m in self.profile_results]

        # Find slowest tests
        slowest_tests = sorted(self.profile_results, key=lambda m: m.duration, reverse=True)[:5]

        # Find highest memory usage tests
        memory_intensive_tests = sorted(self.profile_results, key=lambda m: m.memory_usage, reverse=True)[:5]

        # Find highest CPU usage tests
        cpu_intensive_tests = sorted(self.profile_results, key=lambda m: m.cpu_percent, reverse=True)[:5]

        return {
            "status": "success",
            "summary": {
                "total_tests": len(self.profile_results),
                "average_duration": sum(durations) / len(durations),
                "max_duration": max(durations),
                "min_duration": min(durations),
                "average_memory": sum(memory_usage) / len(memory_usage),
                "max_memory": max(memory_usage),
                "average_cpu": sum(cpu_usage) / len(cpu_usage),
                "max_cpu": max(cpu_usage),
            },
            "slowest_tests": [
                {"test_name": m.test_name, "duration": m.duration, "recommendations": m.recommendations}
                for m in slowest_tests
            ],
            "memory_intensive_tests": [
                {
                    "test_name": m.test_name,
                    "memory_usage": m.memory_usage,
                    "memory_peak": m.memory_peak,
                    "recommendations": m.recommendations,
                }
                for m in memory_intensive_tests
            ],
            "cpu_intensive_tests": [
                {"test_name": m.test_name, "cpu_percent": m.cpu_percent, "recommendations": m.recommendations}
                for m in cpu_intensive_tests
            ],
        }

    def save_performance_report(self, filename: str | None = None):
        """Save performance report to file."""
        report = self.generate_performance_report()

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"performance_report_{timestamp}.json"

        report_file = self.output_dir / filename

        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Performance report saved to: {report_file}")
        return report_file


class AsyncPerformanceProfiler:
    """Specialized profiler for async operations."""

    def __init__(self, profiler: PerformanceProfiler):
        self.profiler = profiler
        self.async_operations: list[dict[str, Any]] = []

    @asynccontextmanager
    async def profile_async_operation(self, operation_name: str):
        """Profile an async operation."""
        start_time = time.time()
        operation_data = {
            "name": operation_name,
            "start_time": start_time,
            "end_time": None,
            "duration": None,
            "await_count": 0,
            "task_count": 0,
        }

        try:
            yield operation_data
        finally:
            operation_data["end_time"] = time.time()
            operation_data["duration"] = operation_data["end_time"] - start_time

            # Count async operations
            loop = asyncio.get_running_loop()
            operation_data["task_count"] = len(asyncio.all_tasks())

            self.async_operations.append(operation_data)

    def get_async_summary(self) -> dict[str, Any]:
        """Get summary of async operations."""
        if not self.async_operations:
            return {"status": "no_data"}

        durations = [op["duration"] for op in self.async_operations]

        return {
            "status": "success",
            "total_operations": len(self.async_operations),
            "average_duration": sum(durations) / len(durations),
            "max_duration": max(durations),
            "min_duration": min(durations),
            "operations": self.async_operations,
        }


class PerformanceAnalyzer:
    """Analyzes performance data and provides insights."""

    def __init__(self):
        self.analysis_rules = self._load_analysis_rules()

    def analyze_performance_data(self, metrics: list[PerformanceMetrics]) -> dict[str, Any]:
        """Analyze performance data and provide insights."""
        analysis = {
            "overall_assessment": "good",
            "issues": [],
            "recommendations": [],
            "trends": {},
        }

        # Analyze trends
        analysis["trends"] = self._analyze_trends(metrics)

        # Identify issues
        analysis["issues"] = self._identify_issues(metrics)

        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(metrics)

        # Overall assessment
        if analysis["issues"]:
            analysis["overall_assessment"] = "needs_attention"

        return analysis

    def _analyze_trends(self, metrics: list[PerformanceMetrics]) -> dict[str, Any]:
        """Analyze performance trends."""
        if len(metrics) < 2:
            return {"status": "insufficient_data"}

        # Sort by start time
        sorted_metrics = sorted(metrics, key=lambda m: m.start_time)

        durations = [m.duration for m in sorted_metrics]
        memory_usage = [m.memory_usage for m in sorted_metrics]

        # Calculate trends
        duration_trend = self._calculate_trend(durations)
        memory_trend = self._calculate_trend(memory_usage)

        return {
            "duration_trend": duration_trend,
            "memory_trend": memory_trend,
            "performance_degradation": duration_trend > 0.1,  # 10% increase
            "memory_leak_suspected": memory_trend > 0.05,  # 5% increase
        }

    def _calculate_trend(self, values: list[float]) -> float:
        """Calculate trend slope."""
        if len(values) < 2:
            return 0.0

        # Simple linear regression slope
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _identify_issues(self, metrics: list[PerformanceMetrics]) -> list[dict[str, Any]]:
        """Identify performance issues."""
        issues = []

        for metric in metrics:
            # Slow test
            if metric.duration > 5.0:  # 5 seconds
                issues.append(
                    {
                        "type": "slow_test",
                        "test_name": metric.test_name,
                        "severity": "high" if metric.duration > 10.0 else "medium",
                        "value": metric.duration,
                        "threshold": 5.0,
                    }
                )

            # High memory usage
            if metric.memory_usage > 200.0:  # 200 MB
                issues.append(
                    {
                        "type": "high_memory",
                        "test_name": metric.test_name,
                        "severity": "high" if metric.memory_usage > 500.0 else "medium",
                        "value": metric.memory_usage,
                        "threshold": 200.0,
                    }
                )

            # High CPU usage
            if metric.cpu_percent > 90.0:  # 90%
                issues.append(
                    {
                        "type": "high_cpu",
                        "test_name": metric.test_name,
                        "severity": "high",
                        "value": metric.cpu_percent,
                        "threshold": 90.0,
                    }
                )

        return issues

    def _generate_recommendations(self, metrics: list[PerformanceMetrics]) -> list[str]:
        """Generate performance recommendations."""
        recommendations = []

        # Analyze common patterns
        slow_tests = [m for m in metrics if m.duration > 2.0]
        memory_intensive = [m for m in metrics if m.memory_usage > 100.0]
        cpu_intensive = [m for m in metrics if m.cpu_percent > 80.0]

        if len(slow_tests) > len(metrics) * 0.3:  # More than 30% are slow
            recommendations.append("Consider optimizing test setup and teardown")
            recommendations.append("Use test doubles for external dependencies")

        if len(memory_intensive) > len(metrics) * 0.2:  # More than 20% use high memory
            recommendations.append("Review test data size and cleanup procedures")
            recommendations.append("Consider using generators for large datasets")

        if len(cpu_intensive) > len(metrics) * 0.1:  # More than 10% use high CPU
            recommendations.append("Optimize algorithms and reduce computational complexity")
            recommendations.append("Consider parallelizing independent operations")

        return recommendations

    def _load_analysis_rules(self) -> dict[str, Any]:
        """Load analysis rules and thresholds."""
        return {
            "slow_test_threshold": 2.0,
            "high_memory_threshold": 100.0,
            "high_cpu_threshold": 80.0,
            "performance_degradation_threshold": 0.1,
            "memory_leak_threshold": 0.05,
        }


# Global profiler instance
_global_profiler = PerformanceProfiler()
_global_async_profiler = AsyncPerformanceProfiler(_global_profiler)
_global_analyzer = PerformanceAnalyzer()


def get_profiler() -> PerformanceProfiler:
    """Get the global performance profiler."""
    return _global_profiler


def get_async_profiler() -> AsyncPerformanceProfiler:
    """Get the global async profiler."""
    return _global_async_profiler


def get_analyzer() -> PerformanceAnalyzer:
    """Get the global performance analyzer."""
    return _global_analyzer


# Convenience functions
def profile_test(test_name: str):
    """Profile a test function."""
    profiler = get_profiler()
    return profiler.profile_test(test_name)


async def profile_async_operation(operation_name: str):
    """Profile an async operation."""
    async_profiler = get_async_profiler()
    return async_profiler.profile_async_operation(operation_name)


def start_performance_monitoring(interval: float = 0.1):
    """Start performance monitoring."""
    profiler = get_profiler()
    profiler.start_monitoring(interval)


def stop_performance_monitoring():
    """Stop performance monitoring."""
    profiler = get_profiler()
    profiler.stop_monitoring()


def generate_performance_report() -> dict[str, Any]:
    """Generate a performance report."""
    profiler = get_profiler()
    return profiler.generate_performance_report()


def save_performance_report(filename: str | None = None) -> Path:
    """Save a performance report."""
    profiler = get_profiler()
    return profiler.save_performance_report(filename)


# Decorators for easy use
def profile_performance(test_name: str | None = None):
    """Decorator to profile test performance."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            name = test_name or func.__name__
            profiler = get_profiler()

            with profiler.profile_test(name):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def profile_async_performance(operation_name: str | None = None):
    """Decorator to profile async operation performance."""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            name = operation_name or func.__name__
            async_profiler = get_async_profiler()

            async with async_profiler.profile_async_operation(name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
