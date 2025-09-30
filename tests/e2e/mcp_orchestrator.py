#!/usr/bin/env python3
"""
MCP Integration for CTIScraper Playwright Test Orchestration
This module provides MCP-based test orchestration and result analysis
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import asyncio
import aiohttp

class PlaywrightMCPOrchestrator:
    """MCP-based orchestrator for Playwright tests"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.test_results_dir = Path("test-results")
        self.test_results_dir.mkdir(exist_ok=True)
    
    async def run_tests(self, test_suite: str = "e2e") -> Dict[str, Any]:
        """Run Playwright tests and return results"""
        print(f"🚀 Starting {test_suite} test suite...")
        
        # Run pytest with Playwright
        cmd = [
            "pytest", 
            f"tests/{test_suite}/", 
            "-v", 
            "--browser", "chromium",
            "--headed=false",
            "--json-report",
            "--json-report-file=test-results/results.json"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Parse results
            results = self._parse_test_results()
            
            # Generate report
            report = await self._generate_report(results, result.returncode)
            
            return report
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0
            }
    
    def _parse_test_results(self) -> Dict[str, Any]:
        """Parse test results from JSON report"""
        results_file = self.test_results_dir / "results.json"
        
        if not results_file.exists():
            return {"status": "no_results"}
        
        try:
            with open(results_file) as f:
                return json.load(f)
        except Exception as e:
            return {"status": "parse_error", "error": str(e)}
    
    async def _generate_report(self, results: Dict[str, Any], exit_code: int) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        report = {
            "timestamp": asyncio.get_event_loop().time(),
            "exit_code": exit_code,
            "status": "passed" if exit_code == 0 else "failed",
            "summary": self._extract_summary(results),
            "details": results,
            "artifacts": self._collect_artifacts(),
            "recommendations": []
        }
        
        # Add recommendations based on results
        if exit_code != 0:
            report["recommendations"].extend([
                "Review failed tests in test-results/ directory",
                "Check browser console logs for JavaScript errors",
                "Verify application is running on correct port",
                "Check database and Redis connectivity"
            ])
        
        return report
    
    def _extract_summary(self, results: Dict[str, Any]) -> Dict[str, int]:
        """Extract test summary from results"""
        summary = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0
        }
        
        if "summary" in results:
            summary.update(results["summary"])
        
        return summary
    
    def _collect_artifacts(self) -> List[str]:
        """Collect available test artifacts"""
        artifacts = []
        
        # Check for common artifact types
        artifact_patterns = [
            "test-results/videos/*.webm",
            "test-results/traces/*.zip",
            "test-results/screenshots/*.png",
            "playwright-report/index.html"
        ]
        
        for pattern in artifact_patterns:
            for path in Path(".").glob(pattern):
                artifacts.append(str(path))
        
        return artifacts
    
    async def analyze_failures(self, results: Dict[str, Any]) -> List[Dict[str, str]]:
        """Analyze test failures and suggest fixes"""
        failures = []
        
        if "tests" in results:
            for test in results["tests"]:
                if test.get("outcome") == "failed":
                    failure = {
                        "test_name": test.get("nodeid", "unknown"),
                        "error": test.get("call", {}).get("longrepr", "No error details"),
                        "suggestion": self._suggest_fix(test)
                    }
                    failures.append(failure)
        
        return failures
    
    def _suggest_fix(self, test: Dict[str, Any]) -> str:
        """Suggest fixes for failed tests"""
        error = str(test.get("call", {}).get("longrepr", "")).lower()
        
        if "timeout" in error:
            return "Increase timeout or check for slow page loads"
        elif "not found" in error or "element" in error:
            return "Check if page elements exist and are visible"
        elif "network" in error or "connection" in error:
            return "Verify application is running and accessible"
        elif "assertion" in error:
            return "Review test assertions and expected values"
        else:
            return "Review test logic and application behavior"
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on CTIScraper application"""
        try:
            async with aiohttp.ClientSession() as session:
                # Check main page
                async with session.get(f"{self.base_url}/") as response:
                    main_page_ok = response.status == 200
                
                # Check health endpoint
                async with session.get(f"{self.base_url}/health") as response:
                    health_ok = response.status == 200
                
                # Check API
                async with session.get(f"{self.base_url}/api/sources") as response:
                    api_ok = response.status == 200
                
                return {
                    "main_page": main_page_ok,
                    "health_endpoint": health_ok,
                    "api_endpoint": api_ok,
                    "overall": main_page_ok and health_ok and api_ok
                }
                
        except Exception as e:
            return {
                "main_page": False,
                "health_endpoint": False,
                "api_endpoint": False,
                "overall": False,
                "error": str(e)
            }

async def main():
    """Main function for MCP orchestration"""
    orchestrator = PlaywrightMCPOrchestrator()
    
    # Health check first
    print("🔍 Performing health check...")
    health = await orchestrator.health_check()
    print(f"Health check: {'✅ PASS' if health['overall'] else '❌ FAIL'}")
    
    if not health['overall']:
        print("❌ Application not healthy, skipping tests")
        sys.exit(1)
    
    # Run tests
    print("🧪 Running Playwright tests...")
    results = await orchestrator.run_tests()
    
    # Print summary
    summary = results.get("summary", {})
    print(f"\n📊 Test Summary:")
    print(f"  Total: {summary.get('total', 0)}")
    print(f"  Passed: {summary.get('passed', 0)}")
    print(f"  Failed: {summary.get('failed', 0)}")
    print(f"  Skipped: {summary.get('skipped', 0)}")
    
    # Analyze failures
    if results.get("status") == "failed":
        print("\n🔍 Analyzing failures...")
        failures = await orchestrator.analyze_failures(results.get("details", {}))
        
        for failure in failures:
            print(f"\n❌ {failure['test_name']}")
            print(f"   Error: {failure['error'][:100]}...")
            print(f"   Suggestion: {failure['suggestion']}")
    
    # Save report
    report_file = Path("test-results/mcp-report.json")
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Report saved to: {report_file}")
    
    # Exit with appropriate code
    sys.exit(0 if results.get("status") == "passed" else 1)

if __name__ == "__main__":
    asyncio.run(main())
