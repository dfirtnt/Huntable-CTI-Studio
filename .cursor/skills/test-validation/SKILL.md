---
name: test-validation
description: Runs the standard test sequence (smoke, unit, api, integration, then ui excluding agent_config_mutation), parses pass counts, and validates them against expected baselines. Use when you need to confirm the suite is green with known-good counts; does not fix failures.
---

# Test Validation

Runs the standard Huntable CTI Studio test sequence and reports pass/fail counts for each group.

## Test Sequence

Executes in order:

1. **smoke** - Quick health check
2. **unit** - Unit tests
3. **api** - API endpoint tests
4. **integration** - System integration tests
5. **ui** (excluding `agent_config_mutation`) - Web interface tests

## Usage

When invoked, this skill:

1. Runs each test group sequentially using `./run_tests.py`
2. Captures pass/fail/skip counts from pytest output
3. Reports results in a summary table
4. Does NOT attempt to fix failures (read-only validation)

## Output Format

```
Test Validation Results
=======================

Group         | Passed | Failed | Skipped | Status
------------- | ------ | ------ | ------- | ------
smoke         |     31 |      0 |       0 | ✅ PASS
unit          |    662 |      0 |      27 | ✅ PASS
api           |     42 |      1 |       0 | ❌ FAIL
integration   |     38 |      0 |       2 | ✅ PASS
ui            |     15 |      0 |       1 | ✅ PASS
------------- | ------ | ------ | ------- | ------
TOTAL         |    788 |      1 |      30 | ❌ FAIL
```

## Implementation

```python
import subprocess
import re
from pathlib import Path

def run_test_group(group: str, exclude_markers: list[str] = None) -> dict:
    """Run a test group and parse results."""
    cmd = ["./run_tests.py", group]
    if exclude_markers:
        cmd.extend(["--exclude-markers"] + exclude_markers)
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )
    
    # Parse pytest summary line: "= X passed, Y failed, Z skipped in Ns"
    output = result.stdout + result.stderr
    
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    
    # Match patterns like "25 passed", "1 failed", "3 skipped", "2 errors"
    for pattern, key in [
        (r"(\d+)\s+passed\b", "passed"),
        (r"(\d+)\s+failed\b", "failed"),
        (r"(\d+)\s+skipped", "skipped"),
        (r"(\d+)\s+errors?", "errors"),
    ]:
        match = re.search(pattern, output)
        if match:
            counts[key] = int(match.group(1))
    
    return {
        "counts": counts,
        "success": result.returncode == 0,
        "output": output
    }

# Test groups to run
test_groups = [
    ("smoke", []),
    ("unit", []),
    ("api", []),
    ("integration", []),
    ("ui", ["agent_config_mutation"]),
]

results = []
for group, exclude_markers in test_groups:
    print(f"\n🧪 Running {group} tests...")
    result = run_test_group(group, exclude_markers if exclude_markers else None)
    results.append((group, result))

# Print summary table
print("\n" + "=" * 70)
print("Test Validation Results")
print("=" * 70)
print()
print(f"{'Group':<13} | {'Passed':>6} | {'Failed':>6} | {'Skipped':>7} | Status")
print("-" * 70)

total_passed = 0
total_failed = 0
total_skipped = 0
total_errors = 0

for group, result in results:
    counts = result["counts"]
    passed = counts["passed"]
    failed = counts["failed"] + counts["errors"]
    skipped = counts["skipped"]
    status = "✅ PASS" if result["success"] else "❌ FAIL"
    
    print(f"{group:<13} | {passed:>6} | {failed:>6} | {skipped:>7} | {status}")
    
    total_passed += passed
    total_failed += failed
    total_skipped += skipped
    total_errors += counts["errors"]

print("-" * 70)
overall_status = "✅ PASS" if total_failed == 0 and total_errors == 0 else "❌ FAIL"
print(f"{'TOTAL':<13} | {total_passed:>6} | {total_failed:>6} | {total_skipped:>7} | {overall_status}")
print()
```

## Notes

- This skill does NOT fix failures - it only reports them
- For fixing failures, use the `test-runner-fix` skill instead
- The `ui` group excludes `agent_config_mutation` marker to avoid mutating active configs
- Each test group runs independently (no shared state)
- Failure logs are saved to `test-results/failures_*.log` by `run_tests.py`
