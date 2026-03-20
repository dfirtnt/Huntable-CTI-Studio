---
name: test-validation
description: Runs the standard test sequence (smoke, unit, api, integration, then ui). UI uses --skip-playwright-js (pytest tests/ui only; no npx tests/playwright). Agent/workflow config-mutating tests stay excluded by run_tests.py ui defaults. Parses pass counts; does not fix failures.
---

# Test Validation

Runs the standard Huntable CTI Studio test sequence and reports pass/fail counts for each group.

## Test Sequence

Executes in order:

1. **smoke** - Quick health check
2. **unit** - Unit tests
3. **api** - API endpoint tests
4. **integration** - System integration tests
5. **ui** - `ui --skip-playwright-js` — pytest `tests/ui/` only (skips `npx playwright test tests/playwright/`; config-mutating tests still excluded by `run_tests.py ui` defaults). For full UI including TS Playwright, run `python3 run_tests.py ui` separately.
6. **quality regression** - `regression --context localhost --paths tests/quality/test_quality_categories_seed.py --output-format quiet`
7. **quality contract** - `contract --context localhost --paths tests/quality/test_quality_categories_seed.py --output-format quiet`
8. **quality security** - `security --context localhost --paths tests/quality/test_quality_categories_seed.py --output-format quiet`
9. **quality a11y** - `a11y --context localhost --paths tests/quality/test_quality_categories_seed.py --output-format quiet`
10. **unit --markers regression** - `unit --markers regression`
11. **unit --markers contract** - `unit --markers contract`
12. **unit --markers security** - `unit --markers security`
13. **unit --markers a11y** - `unit --markers a11y`

## Usage

When invoked, this skill:

1. Runs each test group sequentially using `python3 run_tests.py` (ui step includes `--skip-playwright-js`)
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

def run_test_group(group: str, exclude_markers: list[str] = None, extra_args: list[str] = None) -> dict:
    """Run a test group and parse results."""
    cmd = ["python3", "run_tests.py", group]
    if exclude_markers:
        cmd.extend(["--exclude-markers"] + exclude_markers)
    if extra_args:
        cmd.extend(extra_args)
    
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

# Test groups: (run_tests.py category, exclude_markers, extra_args, display_name=None)
# display_name used in table; if None, category is used.
quality_path_args = ["--context", "localhost", "--paths", "tests/quality/test_quality_categories_seed.py", "--output-format", "quiet"]
test_groups = [
    ("smoke", [], None, None),
    ("unit", [], None, None),
    ("api", [], None, None),
    ("integration", [], None, None),
    ("ui", [], ["--skip-playwright-js"], None),
    ("regression", [], quality_path_args, None),
    ("contract", [], quality_path_args, None),
    ("security", [], quality_path_args, None),
    ("a11y", [], quality_path_args, None),
    ("unit", [], ["--markers", "regression"], "unit regression"),
    ("unit", [], ["--markers", "contract"], "unit contract"),
    ("unit", [], ["--markers", "security"], "unit security"),
    ("unit", [], ["--markers", "a11y"], "unit a11y"),
]

results = []
for item in test_groups:
    group = item[0]
    exclude_markers = item[1]
    extra_args = item[2] if len(item) > 2 else None
    display_name = item[3] if (len(item) > 3 and item[3] is not None) else group
    print(f"\n🧪 Running {display_name} tests...")
    result = run_test_group(group, exclude_markers if exclude_markers else None, extra_args)
    results.append((display_name, result))

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
- The `ui` step uses `--skip-playwright-js` so validation finishes in reasonable time; it does **not** run `tests/playwright/*.spec.ts`. Full browser parity: `python3 run_tests.py ui` (omit the flag).
- Agent/workflow config-mutating tests stay excluded by `run_tests.py ui` defaults unless you pass `--include-agent-config-tests`
- Quality runs (regression, contract, security, a11y) use `--context localhost --paths tests/quality/test_quality_categories_seed.py --output-format quiet`
- Unit marker runs: `unit --markers regression|contract|security|a11y` (expected 1 passed each)
- Each test group runs independently (no shared state)
- Failure logs are saved to `test-results/failures_*.log` by `run_tests.py`
