#!/usr/bin/env python3
"""
CTI Scraper Grouped Test Execution Script

Executes tests in groups (smoke, unit, api, integration, ui, e2e, performance, ai)
one group at a time and reports broken tests.

Usage:
    python scripts/run_tests_by_group.py                    # Run all groups
    python scripts/run_tests_by_group.py --group smoke      # Run specific group
    python scripts/run_tests_by_group.py --stop-on-failure # Stop at first failure
    python scripts/run_tests_by_group.py --verbose          # Verbose output
"""

import os
import sys
import subprocess
import json
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class TestResult:
    """Test execution result."""
    group: str
    success: bool
    passed: int
    failed: int
    skipped: int
    errors: int
    duration: float
    broken_tests: List[Dict[str, str]]
    output: str
    error_output: str


class TestGroupRunner:
    """Run tests by group and collect results."""
    
    # Test groups in execution order
    TEST_GROUPS = [
        ("smoke", "Quick health check (~30s)"),
        ("unit", "Unit tests excluding other categories (~1m)"),
        ("api", "API endpoint tests (~2m)"),
        ("integration", "System integration tests (~3m)"),
        ("ui", "Web interface tests (~5m)"),
        ("e2e", "End-to-end tests (~3m)"),
        ("performance", "Performance tests (~2m)"),
        ("ai", "AI-specific tests (~3m)"),
    ]
    
    def __init__(self, verbose: bool = False, stop_on_failure: bool = False):
        self.verbose = verbose
        self.stop_on_failure = stop_on_failure
        self.results: List[TestResult] = []
        self.start_time = time.time()
        
    def run_group(self, group_name: str) -> TestResult:
        """Run tests for a specific group."""
        print(f"\n{'='*80}")
        print(f"Running {group_name.upper()} tests...")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        
        # Build command - use run_tests.py which handles venv and paths correctly
        # For smoke tests, run_tests.py uses -m smoke which collects all tests
        # This is the standard way smoke tests have been run
        cmd = ["python3", "run_tests.py", group_name]
        if self.verbose:
            cmd.append("--verbose")
        
        # Run command
        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout per group
            )
            
            duration = time.time() - start_time
            
            # Parse output
            counts = self._parse_pytest_output(result.stdout + result.stderr)
            broken_tests = self._extract_broken_tests(result.stdout + result.stderr)
            
            test_result = TestResult(
                group=group_name,
                success=result.returncode == 0,
                passed=counts.get("passed", 0),
                failed=counts.get("failed", 0),
                skipped=counts.get("skipped", 0),
                errors=counts.get("errors", 0),
                duration=duration,
                broken_tests=broken_tests,
                output=result.stdout,
                error_output=result.stderr
            )
            
            # Print summary
            self._print_group_summary(test_result)
            
            return test_result
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f"⚠️  {group_name.upper()} tests timed out after {duration:.2f}s")
            return TestResult(
                group=group_name,
                success=False,
                passed=0,
                failed=0,
                skipped=0,
                errors=1,
                duration=duration,
                broken_tests=[{"test": "TIMEOUT", "reason": f"Tests timed out after {duration:.2f}s"}],
                output="",
                error_output="Timeout expired"
            )
        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ Error running {group_name.upper()} tests: {e}")
            return TestResult(
                group=group_name,
                success=False,
                passed=0,
                failed=0,
                skipped=0,
                errors=1,
                duration=duration,
                broken_tests=[{"test": "ERROR", "reason": str(e)}],
                output="",
                error_output=str(e)
            )
    
    def _parse_pytest_output(self, output: str) -> Dict[str, int]:
        """Parse pytest output to extract test counts."""
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        
        # Pattern: = X failed, Y passed, Z skipped
        pattern = r'=\s*(\d+)\s+failed.*?(\d+)\s+passed.*?(\d+)\s+skipped'
        match = re.search(pattern, output)
        if match:
            counts["failed"] = int(match.group(1))
            counts["passed"] = int(match.group(2))
            counts["skipped"] = int(match.group(3))
        
        # Also look for errors
        error_pattern = r'(\d+)\s+errors?'
        error_match = re.search(error_pattern, output)
        if error_match:
            counts["errors"] = int(error_match.group(1))
        
        return counts
    
    def _extract_broken_tests(self, output: str) -> List[Dict[str, str]]:
        """Extract broken test information from pytest output."""
        broken_tests = []
        
        # Pattern: FAILED tests/ui/test_file.py::TestClass::test_method
        failed_pattern = r'FAILED\s+(tests/[^\s]+::[^\s]+)'
        failed_matches = re.findall(failed_pattern, output)
        
        for test_path in failed_matches:
            # Try to extract failure reason (next few lines after FAILED)
            lines = output.split('\n')
            for i, line in enumerate(lines):
                if f"FAILED {test_path}" in line:
                    # Get next few lines for context
                    reason_lines = []
                    for j in range(i+1, min(i+5, len(lines))):
                        if lines[j].strip() and not lines[j].startswith('='):
                            reason_lines.append(lines[j].strip())
                            if len(reason_lines) >= 2:
                                break
                    reason = ' '.join(reason_lines[:2]) if reason_lines else "No reason provided"
                    broken_tests.append({
                        "test": test_path,
                        "reason": reason[:200]  # Limit reason length
                    })
                    break
        
        return broken_tests
    
    def _print_group_summary(self, result: TestResult):
        """Print summary for a test group."""
        status = "✅ PASSED" if result.success else "❌ FAILED"
        print(f"\n{result.group.upper()} Tests: {status}")
        print(f"  Passed: {result.passed}")
        print(f"  Failed: {result.failed}")
        print(f"  Skipped: {result.skipped}")
        print(f"  Errors: {result.errors}")
        print(f"  Duration: {result.duration:.2f}s")
        
        if result.broken_tests:
            print(f"\n  Broken Tests ({len(result.broken_tests)}):")
            for broken in result.broken_tests[:10]:  # Show first 10
                print(f"    - {broken['test']}")
                if broken['reason']:
                    print(f"      Reason: {broken['reason']}")
            if len(result.broken_tests) > 10:
                print(f"    ... and {len(result.broken_tests) - 10} more")
    
    def run_all_groups(self, groups: Optional[List[str]] = None) -> List[TestResult]:
        """Run all test groups or specified groups."""
        groups_to_run = groups or [g[0] for g in self.TEST_GROUPS]
        
        print(f"\n{'='*80}")
        print("CTI Scraper Grouped Test Execution")
        print(f"{'='*80}")
        print(f"Groups to run: {', '.join(groups_to_run)}")
        print(f"Stop on failure: {self.stop_on_failure}")
        print(f"{'='*80}\n")
        
        for group_name, description in self.TEST_GROUPS:
            if group_name not in groups_to_run:
                continue
            
            result = self.run_group(group_name)
            self.results.append(result)
            
            # Stop if failure and stop_on_failure is True
            if not result.success and self.stop_on_failure:
                print(f"\n⚠️  Stopping execution due to failure in {group_name} group")
                break
        
        return self.results
    
    def generate_reports(self):
        """Generate JSON, Markdown, and text reports."""
        total_duration = time.time() - self.start_time
        
        # Calculate totals
        total_passed = sum(r.passed for r in self.results)
        total_failed = sum(r.failed for r in self.results)
        total_skipped = sum(r.skipped for r in self.results)
        total_errors = sum(r.errors for r in self.results)
        all_broken = []
        for r in self.results:
            all_broken.extend(r.broken_tests)
        
        # JSON Report
        json_report = {
            "timestamp": datetime.now().isoformat(),
            "total_duration": total_duration,
            "groups": [asdict(r) for r in self.results],
            "summary": {
                "total_passed": total_passed,
                "total_failed": total_failed,
                "total_skipped": total_skipped,
                "total_errors": total_errors,
                "total_broken_tests": len(all_broken),
                "groups_run": len(self.results),
                "groups_passed": sum(1 for r in self.results if r.success),
                "groups_failed": sum(1 for r in self.results if not r.success)
            }
        }
        
        json_path = project_root / "test_results_by_group.json"
        with open(json_path, "w") as f:
            json.dump(json_report, f, indent=2)
        print(f"\n📊 JSON report saved to: {json_path}")
        
        # Markdown Report
        md_path = project_root / "test_results_summary.md"
        with open(md_path, "w") as f:
            f.write("# Test Execution Summary\n\n")
            f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Duration**: {total_duration:.2f}s\n\n")
            f.write("## Summary\n\n")
            f.write(f"- **Passed**: {total_passed}\n")
            f.write(f"- **Failed**: {total_failed}\n")
            f.write(f"- **Skipped**: {total_skipped}\n")
            f.write(f"- **Errors**: {total_errors}\n")
            f.write(f"- **Groups Run**: {len(self.results)}\n")
            f.write(f"- **Groups Passed**: {sum(1 for r in self.results if r.success)}\n")
            f.write(f"- **Groups Failed**: {sum(1 for r in self.results if not r.success)}\n\n")
            
            f.write("## Group Results\n\n")
            f.write("| Group | Status | Passed | Failed | Skipped | Errors | Duration |\n")
            f.write("|-------|--------|--------|--------|----------|--------|----------|\n")
            for r in self.results:
                status = "✅ PASS" if r.success else "❌ FAIL"
                f.write(f"| {r.group} | {status} | {r.passed} | {r.failed} | {r.skipped} | {r.errors} | {r.duration:.2f}s |\n")
            
            if all_broken:
                f.write("\n## Broken Tests\n\n")
                for broken in all_broken:
                    f.write(f"### {broken['test']}\n\n")
                    f.write(f"**Reason**: {broken['reason']}\n\n")
        
        print(f"📄 Markdown report saved to: {md_path}")
        
        # Text Report (Broken Tests List)
        txt_path = project_root / "broken_tests.txt"
        with open(txt_path, "w") as f:
            f.write("Broken Tests List\n")
            f.write("="*80 + "\n\n")
            if all_broken:
                for broken in all_broken:
                    f.write(f"{broken['test']}\n")
                    f.write(f"  Reason: {broken['reason']}\n\n")
            else:
                f.write("No broken tests found.\n")
        
        print(f"📝 Broken tests list saved to: {txt_path}")
        
        # Print final summary
        print(f"\n{'='*80}")
        print("FINAL SUMMARY")
        print(f"{'='*80}")
        print(f"Total Duration: {total_duration:.2f}s")
        print(f"Groups Run: {len(self.results)}")
        print(f"Groups Passed: {sum(1 for r in self.results if r.success)}")
        print(f"Groups Failed: {sum(1 for r in self.results if not r.success)}")
        print(f"Total Tests Passed: {total_passed}")
        print(f"Total Tests Failed: {total_failed}")
        print(f"Total Broken Tests: {len(all_broken)}")
        print(f"{'='*80}\n")
        
        if all_broken:
            print("Broken Tests:")
            for broken in all_broken[:20]:  # Show first 20
                print(f"  - {broken['test']}")
            if len(all_broken) > 20:
                print(f"  ... and {len(all_broken) - 20} more (see broken_tests.txt)")
        
        return json_report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run tests by group and report broken tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_tests_by_group.py                    # Run all groups
  python scripts/run_tests_by_group.py --group smoke      # Run specific group
  python scripts/run_tests_by_group.py --group ui --group e2e  # Run multiple groups
  python scripts/run_tests_by_group.py --stop-on-failure   # Stop at first failure
  python scripts/run_tests_by_group.py --verbose           # Verbose output
        """
    )
    
    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        help="Test group to run (can be specified multiple times)",
        choices=[g[0] for g in TestGroupRunner.TEST_GROUPS]
    )
    
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop execution at first group failure"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    runner = TestGroupRunner(
        verbose=args.verbose,
        stop_on_failure=args.stop_on_failure
    )
    
    try:
        results = runner.run_all_groups(groups=args.groups)
        runner.generate_reports()
        
        # Exit with error code if any group failed
        if any(not r.success for r in results):
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Execution interrupted by user")
        runner.generate_reports()
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

