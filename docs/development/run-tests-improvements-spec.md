# run_tests.py Improvements - Development Spec

_Last updated: 2026-05-26_

Status: Proposed
Owner: Andrew
Source: review + QA pass on `run_tests.py` (commit at HEAD when this spec was written)

## Background

`run_tests.py` is the canonical test entrypoint (per `AGENTS.md` / `CLAUDE.md`). It is currently a 2,393-line single-file driver that handles environment setup, container management, pytest + Playwright command construction, live TUI, and report writing. A code review identified a mix of (a) latent bugs, (b) UX problems, (c) performance friction, and (d) coverage policy gaps.

This spec organizes those findings into independently shippable items, each with goal, design, acceptance, and risk. Items are grouped by tier so the smallest-blast-radius work can ship first.

## Non-goals

- Replacing pytest, Playwright, or the existing reporting stack.
- Changing the public CLI surface in ways that break documented invocations in `AGENTS.md`, `Makefile`, or CI.
- Rewriting test code itself. This spec is strictly about the runner.

## Conventions used in this spec

- All file references are clickable links to the source.
- "Net diff" is an estimate of the lines that change in the proposed commit.
- Each item is sized so it can ship as one commit. Larger items note where they should be split.
- Per repo policy: ASCII only in code, config, and commit messages. The spec itself is also ASCII.

---

## Tier 1 - Bug fixes (small, isolated, low risk)

### T1.1 Fix broken Unicode byte-literals at line 1498

**Goal.** Remove dead code that pretends to detect Playwright's check/cross glyphs but does not.

**Problem.** `[run_tests.py:1498`](../../run_tests.py) reads:
```
if any(w in line.lower() for w in ["passed", "failed", "skipped", "\xe2\x9c\x93", "\xc3\x97"]):
```
The two `\x..\x..\x..` strings are 3-character Python `str` values (each byte becomes its own code-point: U+00E2, U+009C, U+0093), not the U+2713 / U+00D7 glyphs they were meant to be. They will never match Playwright output. Verified via `python3 -c 'print(len("\xe2\x9c\x93"))'` -> `3`.

**Design.** Drop the two byte-literals from the list. The word-based checks (`"passed"`, `"failed"`, `"skipped"`) already cover Playwright's reporter output; both `list` and `line` reporters print these words. No replacement glyph is needed because the repo policy is ASCII-only anyway.

**Acceptance.**
- Line 1498 is shorter by exactly 2 list elements.
- `./run_tests.py ui --playwright-only` still increments `pw_test_count` per result line (manual smoke test).
- No new test needed; this is dead code removal.

**Risk.** None. The strings never matched anything.

**Net diff.** -1 line.

---

### T1.2 Fix `_save_failure_log` overwrite when both pytest and Playwright fail

**Goal.** Preserve both failure logs in a mixed-failure run.

**Problem.** Both call sites (`[run_tests.py:1379`](../../run_tests.py), `[run_tests.py:1552`](../../run_tests.py)) call `_save_failure_log`, which opens `failures_{timestamp}.log` in `"w"` mode at `[run_tests.py:1683`](../../run_tests.py). When pytest *and* Playwright both fail in one run, the second write silently wipes the first.

**Design.**
1. Add a `section: str` parameter to `_save_failure_log(self, output, counts, section)`.
2. Path becomes `failures_{timestamp}_{section}.log`.
3. Both call sites pass `"pytest"` or `"playwright"`.
4. Update the user-facing print messages at lines 1396-1398 and 1553-1555 to print the new path.
5. Update `_print_combined_summary` if it references the path (verify before edit).

**Acceptance.**
- Force-fail one pytest test and one Playwright test in a single run.
- `test-results/` contains both `failures_{ts}_pytest.log` and `failures_{ts}_playwright.log`.
- Each file references only the failures from its own section.

**Risk.** Low. External tools that grep `test-results/failures_*.log` continue to find both files (glob still matches).

**Net diff.** ~6 lines.

---

### T1.3 De-duplicate `in_ci` computation

**Goal.** Single source of truth for "are we in CI."

**Problem.** Identical expression at `[run_tests.py:445`](../../run_tests.py) and `[run_tests.py:477`](../../run_tests.py): `os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"`. Future CI environments (e.g. adding GitLab or Buildkite) require touching both spots.

**Design.** Add a module-level helper:
```python
def _in_ci() -> bool:
    return os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
```
Replace both call sites.

**Acceptance.** Both call sites resolve to the helper. `grep -n 'GITHUB_ACTIONS' run_tests.py` shows only the helper definition.

**Risk.** None.

**Net diff.** ~4 lines.

---

### T1.4 Rename `--no-validate` to `--no-teardown` (or honor the original name)

**Goal.** Make the flag's behavior match its name.

**Problem.** `[run_tests.py:2158`](../../run_tests.py) registers `--no-validate` with help text "Skip environment validation." But the only consumer is `teardown_environment` at `[run_tests.py:541`](../../run_tests.py), which short-circuits *teardown*, not validation. The actual environment guard at `[run_tests.py:486-497`](../../run_tests.py) runs unconditionally. The flag silently lies.

**Design.** Two options:

**Option A (recommended): rename.** Rename the flag to `--no-teardown`. Rename `validate_env` field on `RunTestConfig` to `run_teardown` (default `True`). Update help text to "Skip environment teardown after tests."

**Option B: honor the name.** Keep `--no-validate`, gate the env guard at line 486-497 on `self.config.validate_env`. But this is dangerous: the guard exists to prevent test runs from hitting the production database, and a CLI flag to skip it is a foot-gun.

Choose Option A. Document the rename in a one-line entry under `## Changed` in CHANGELOG.md.

**Acceptance.**
- `./run_tests.py --no-teardown smoke` runs and skips teardown logging.
- `./run_tests.py --no-validate smoke` errors with argparse "unrecognized arguments."
- Env guard still runs on every invocation.

**Risk.** Low. If anyone in CI scripts has `--no-validate` hardcoded, they get a clean argparse error rather than silent misbehavior. Search `Makefile`, `.github/`, and `scripts/` for usage before renaming.

**Net diff.** ~5 lines.

---

### T1.5 Defensive negative-timeout clamp

**Goal.** Make latent foot-gun explicit instead of latent.

**Problem.** `[run_tests.py:1346`](../../run_tests.py) and `[run_tests.py:1515`](../../run_tests.py) compute `self.config.timeout - elapsed` for `Popen.wait(timeout=...)`. If elapsed exceeds timeout, the value goes negative. In practice this is rarely fatal because the child has already closed stdout (drained queue saw `None`) and `wait()` returns the cached returncode immediately. But it's an unclamped operation on a value that will appear in stack traces if anything else changes.

**Design.** Extract to a helper:
```python
def _remaining_timeout(self, started_at: float) -> float | None:
    if not self.config.timeout:
        return None
    return max(0.1, self.config.timeout - (time.time() - started_at))
```
Use at both call sites.

**Acceptance.** Manual test with `--timeout 5` on a fast suite passes; with `--timeout 1` on a slow suite either raises `TimeoutExpired` cleanly or returns success when child already exited.

**Risk.** None.

**Net diff.** ~6 lines.

---

### T1.6 Defensive `process` reference in except blocks

**Goal.** Avoid `NameError` masking a real subprocess failure.

**Problem.** At `[run_tests.py:1411`](../../run_tests.py) and `[run_tests.py:1559`](../../run_tests.py), the `except subprocess.TimeoutExpired:` handler calls `process.kill()`. If `subprocess.Popen(...)` itself raised before assigning `process` (e.g. ENOENT on the python binary), the handler raises `NameError` and the original error is lost.

**Design.** Initialize `process: subprocess.Popen | None = None` before the `try`, then guard `if process is not None: process.kill()`.

**Acceptance.** Manually break the path to `self.venv_python` and verify the original error is what surfaces, not `NameError`.

**Risk.** None.

**Net diff.** ~4 lines.

---

### T1.7 Tier 1 commit plan

All seven items above ship as **one commit** on a feature branch:

```
fix(run_tests): correctness pass on bug-class issues

- Drop dead Unicode byte-literals from Playwright result detection (T1.1)
- Suffix failure log with section to prevent overwrite (T1.2)
- Extract _in_ci helper (T1.3)
- Rename --no-validate to --no-teardown (T1.4)
- Clamp negative wait() timeouts (T1.5)
- Initialize process to None before try blocks (T1.6)

No behavior change for green runs. Output paths and one CLI flag changed; CHANGELOG updated.
```

Total estimated diff: ~26 lines net. Target review time: 10 minutes.

---

## Tier 2 - Visible quality wins (small but user-facing)

### T2.1 Strip emoji from print statements (ASCII-only compliance)

**Goal.** Bring `run_tests.py` into compliance with the ASCII-only-in-code policy (`feedback_ascii_only_in_code.md`).

**Problem.** ~30 lines contain emoji (`grep -nP '[^\x00-\x7F]' run_tests.py`). Examples: line 1237 (test tube glyph), 1386 (check/cross), 1455 (mask), 1973 (target). They render inconsistently in CI logs, break narrow-terminal alignment, and violate repo policy.

**Design.** Define a small constant table near the top of the file:
```python
class Glyph:
    PASS = "[PASS]"
    FAIL = "[FAIL]"
    WARN = "[WARN]"
    INFO = "[INFO]"
    DONE = "[done]"
    PENDING = "[ ]"
    BAR_FILL = "="
    BAR_EMPTY = " "
```
Mechanical replacement at every site. Realign banner widths if needed (keep 80-column rules).

**Acceptance.**
- `python3 -c 'open("run_tests.py").read().encode("ascii")'` succeeds (no `UnicodeEncodeError`).
- Spot-check `./run_tests.py smoke` and confirm the human output is still readable.

**Risk.** Low. Visual change only. Any external tool that greps for emoji to detect status (unlikely) breaks.

**Net diff.** ~30 lines.

---

### T2.2 Add `--dry-run` flag

**Goal.** Audit the runner's command construction without running tests.

**Problem.** The marker / path / exclude matrix is the most error-prone part of `run_tests.py`. Today the only way to check what `./run_tests.py ui-fast` will actually invoke is to run it. That costs minutes per check.

**Design.**
1. Add `--dry-run` to argparse. Stored as `dry_run: bool = False` on `RunTestConfig`.
2. In `main()`, after building each config and instantiating the runner, if `config.dry_run`:
   - Print a header naming the test type and resolved context.
   - Call `runner._build_pytest_command()` and print as a shell-quoted line via `shlex.join`.
   - Call `runner._build_playwright_command()`; if `None`, print "(no Playwright section)"; else print as shell-quoted.
   - Print the resolved env vars that the runner would set (`APP_ENV`, `TEST_DATABASE_URL`, `REDIS_URL`, `USE_ASGI_CLIENT`, `CTI_EXCLUDE_AGENT_CONFIG_TESTS`, `CTI_INCLUDE_QUARANTINE`).
   - Skip `setup_environment` (do not start containers) and `run_tests`.
3. Exit 0 after printing all configs.

**Acceptance.**
- `./run_tests.py --dry-run smoke unit api` prints three sets of commands, no containers started, no tests run.
- Output is `eval`-able (shell-quoted).
- Round-trip: copy a printed pytest command, paste into a shell with `APP_ENV=test` exported, and it runs the same tests.

**Risk.** Low. New code path; existing paths untouched. Add a unit test that captures stdout and asserts both commands appear.

**Net diff.** ~50 lines.

---

### T2.3 Default `output_format=progress` should not force `-v`

**Goal.** Stop flooding CI logs by default.

**Problem.** `[run_tests.py:1047`](../../run_tests.py) appends `-v` to pytest unconditionally when `output_format == "progress"`. On a 3,000-test run, every collected nodeid prints. CI artifacts balloon and the in-terminal scroll is unusable for spotting failures.

**Design.**
- `progress` (default): no `-v`. Pytest's default short summary is sufficient.
- `verbose` / `-v` flag: `-v`.
- `--verbose --verbose` or `verbose` format with debug: `-vv`.
- `quiet`: `-q`.

Update help text. Document in CHANGELOG under `## Changed`.

**Acceptance.**
- `./run_tests.py smoke` produces ~10x less stdout than before.
- `./run_tests.py -v smoke` matches pre-change behavior.
- HTML / JUnit / Allure outputs unchanged (they don't depend on `-v`).

**Risk.** Medium for anyone parsing stdout for `PASSED` lines. The TUI's category-detection at `[run_tests.py:1281`](../../run_tests.py) depends on "::" + status keywords, which appear at `-v` and above. Audit before merging.

**Mitigation.** Either keep the in-process parser working at default verbosity (pytest default still prints `tests/foo.py .` style), or use the JSONL report log (`reportlog_*.jsonl`, already produced) as the parse source instead of stdout.

**Net diff.** ~5 lines + parser audit.

---

### T2.4 Tier 2 commit plan

Three commits, in order:

1. `style(run_tests): replace emoji with ASCII glyphs (T2.1)`
2. `feat(run_tests): add --dry-run for command auditing (T2.2)`
3. `fix(run_tests): default progress format no longer forces -v (T2.3)`

T2.3 is gated on T2.2 because `--dry-run` is the easiest way to verify T2.3 didn't break command construction.

---

## Tier 3 - Architecture and policy

### T3.1 Replace ad-hoc TUI with `rich.live.Live`

**Goal.** Replace the scrolling-text + carriage-return progress with a stable footer + scrollable log.

**Problem.** Today the runner streams every pytest line *and* periodically writes `\r[...]` (carriage-return + progress bar) over the same line (`[run_tests.py:1334`](../../run_tests.py), `[run_tests.py:1507`](../../run_tests.py)). The carriage return only clears the current line, but pytest is producing new lines constantly, so the "progress" indicator ends up sprinkled into the log instead of being a stable status. Cleanup at `[run_tests.py:1383`](../../run_tests.py) almost never lands on the right line.

**Design.** Use `rich.live.Live` (already a transitive dependency via pytest-html in many setups; verify and add to `pyproject.toml`'s `test` group if needed).

Layout:
```
+---------- pytest output (scrolling) ----------+
| tests/foo.py::test_bar PASSED                 |
| tests/foo.py::test_baz PASSED                 |
| ...                                           |
+-----------------------------------------------+
| Categories: [==  ] 2/4 | tests: 247/?         |
| elapsed: 00:42  pass: 246  fail: 1  skip: 0   |
+-----------------------------------------------+
```

- Detect TTY via `sys.stdout.isatty()`. In non-TTY (CI), fall back to plain logging - no Live frame.
- Wrap `pw_drain` and `drain_to_queue` so they push events into a shared `Console`-backed log panel, while a separate `Progress` widget tracks category completion.
- Encapsulate the TUI in a new module `tests_runner/tui.py` (see T3.2). The runner calls `tui.start()`, `tui.on_test(line)`, `tui.on_category(name)`, `tui.finish(success)`.

**Acceptance.**
- TTY run: footer is stable while logs scroll. Resize the terminal mid-run; layout adapts.
- Non-TTY run (`./run_tests.py smoke 2>&1 | cat`): plain output, no escape sequences.
- `NO_COLOR=1 ./run_tests.py smoke`: no ANSI colors.
- Existing parsers (`_parse_pytest_output`, `_parse_pytest_output_fallback`) unchanged.

**Risk.** Medium. New runtime dependency, new code path. Mitigate by behind-flag rollout: add `--tui rich` (default `auto`), `--tui plain` to force fallback. Keep the old code path as `plain` for one release.

**Net diff.** ~150 lines added, ~60 removed (net +90).

---

### T3.2 Split `run_tests.py` into a `tests_runner/` package

**Goal.** Reduce the 2,393-line monolith into reviewable modules. Specifically: make the file readable for someone who isn't a daily Python dev (per the user's stated context).

**Problem.** Single file mixes: env loading, container management, pytest command building, Playwright command building, TUI, output parsing, report writing, CLI. Any change requires reading thousands of lines of unrelated code to confirm safety.

**Design.** Target structure:
```
tests_runner/
  __init__.py          # exports main()
  cli.py               # argparse, parse_arguments(), shared --dry-run logic
  config.py            # RunTestType, ExecutionContext, RunTestConfig
  env.py               # _load_dotenv, _strip_cloud_llm_keys, _in_ci, env guards
  containers.py        # _wait_for_test_containers, _ensure_test_containers, _start_test_containers
  pytest_cmd.py        # _build_pytest_command and the marker/path tables
  playwright_cmd.py    # _build_playwright_command and its path table
  tui.py               # Live progress (T3.1)
  parsing.py           # _parse_pytest_output (+ fallback), _parse_playwright_output
  reports.py           # _save_failure_log, JUnit fallback parsing, summary printing
  runner.py            # RunTestRunner (orchestrator); imports the above

run_tests.py           # ~10-line shim: from tests_runner.cli import main; sys.exit(asyncio.run(main()))
```

Migration plan (one commit per module to keep diffs reviewable):
1. Create `tests_runner/__init__.py` and `tests_runner/config.py` (move enums + dataclass).
2. Move `env.py` (dotenv, cloud-key stripping, `_in_ci`).
3. Move `containers.py`.
4. Move `pytest_cmd.py` and `playwright_cmd.py`.
5. Move `parsing.py` and `reports.py`.
6. Move `runner.py` (the `RunTestRunner` class minus what's already moved).
7. Move `cli.py` and rewrite `run_tests.py` as the shim.
8. Optionally: move TUI in T3.1 in its own commit before #7.

**Acceptance.**
- `./run_tests.py smoke unit api integration` produces identical stdout/exit code as before each commit.
- `python -m tests_runner smoke` works as an alternate invocation.
- `mypy tests_runner/` passes (or matches pre-split coverage).
- File sizes: each module ~150-300 lines.

**Risk.** High blast radius (every test invocation goes through this code), but each commit is small and revertable. Mitigate by:
- Running the full test suite at each step (CI gate).
- Capturing stdout of `./run_tests.py --dry-run smoke unit api integration ui` before and after each commit; diff should be empty.
- Holding the split until T1 + T2 are merged so the file is in a known-good state before fragmentation.

**Net diff.** Large. ~2,000 lines moved, ~50 lines added (imports + shim).

---

### T3.3 Coverage policy upgrades

**Goal.** Make `--coverage` actually defend a target.

**Problem.** Today `--coverage` writes HTML/XML but does not gate (`--cov-fail-under` is missing), does not track branches (`--cov-branch`), and loses earlier data when multiple test types run in one invocation (no `--cov-append`).

**Design.**
1. **Add `--cov-fail-under`.** Configurable via env var `CTI_COVERAGE_FAIL_UNDER` (default unset / no gate locally). Set in CI to a starting baseline (suggest: current coverage minus 1 percentage point). Increase over time via Renovate or manual bumps.
2. **Add `--cov-branch`.** Branch coverage finds untested `if/else` paths that line coverage misses. Roughly 5-10% slower per pytest run.
3. **Add `--cov-append` for multi-type runs.** When `len(configs) > 1` and `--coverage` is set, all but the first invocation pass `--cov-append`. After the loop, optionally call `coverage combine && coverage report --fail-under=...`.
4. **Snapshot to JSON.** Add `--cov-report=json:test-results/coverage_{timestamp}.json` so coverage history is queryable alongside the existing `report_*.html` and `junit_*.xml`.
5. **Diff coverage (optional T3.3b).** Add a `--diff-coverage` flag that runs `diff-cover coverage.xml --compare-branch=origin/main --fail-under=80` after pytest. Catches regressions on changed lines specifically.

**Acceptance.**
- `./run_tests.py unit api --coverage` produces a single combined coverage report covering both test types.
- `CTI_COVERAGE_FAIL_UNDER=70 ./run_tests.py unit --coverage` exits non-zero if coverage drops below 70%.
- `test-results/coverage_{timestamp}.json` exists and is valid JSON.

**Risk.** Low. Coverage is opt-in. Default behavior (no `--coverage`) is unchanged.

**Net diff.** ~25 lines.

---

### T3.4 Container health via single `docker compose ps`

**Goal.** Cut polling overhead from N subprocesses per cycle to 1.

**Problem.** `_wait_for_test_containers` (`[run_tests.py:292`](../../run_tests.py)) runs 2 `docker inspect` calls per service per loop iteration, polling every 2 seconds for up to 90 seconds. Worst case: ~180 process spawns.

**Design.** Replace the per-service inspect loop with one call:
```python
result = subprocess.run(
    [*compose_base, "ps", "--format", "json", "postgres_test", "redis_test"],
    capture_output=True, text=True, check=False,
)
# parse JSON, check Health field per service
```
Modern docker-compose (v2.x) outputs JSON-per-line. Fall back to old per-service inspect path if `--format json` errors (older Docker installs).

**Acceptance.**
- `time ./run_tests.py integration` is at least 1-2 seconds faster on first invocation (when containers are starting).
- Behavior unchanged when containers are already healthy.

**Risk.** Low. Wrap in try/except and fall back to current code on parse errors or on Docker versions that don't support `--format json`.

**Net diff.** ~30 lines (new path + fallback).

---

### T3.5 Misc smaller items (one commit each, or batched)

These are items from the review that don't merit their own section:

- **Argparse `mutually_exclusive_group` for `--playwright-only` / `--skip-playwright-js`.** Today the conflict is detected at runtime (`[run_tests.py:1121`](../../run_tests.py)). Move to argparse so the CLI rejects it before any work starts. ~3 lines.
- **Replace substring path matching in `_get_pytest_test_groups`.** `[run_tests.py:632-651`](../../run_tests.py) uses `"smoke" in path`, which can mis-classify paths like `tests/api/test_smoke_endpoints.py`. Use `Path(path).parts` and exact set membership. ~10 lines.
- **Cache plugin-availability checks.** `_build_pytest_command` re-imports `allure`, `pytest_timeout`, `xdist` in subprocesses (`[run_tests.py:980`](../../run_tests.py), `[run_tests.py:1026`](../../run_tests.py), `[run_tests.py:1074`](../../run_tests.py)). Cache results on the `RunTestRunner` instance. ~15 lines.
- **`output_lines` memory.** `[run_tests.py:1268`](../../run_tests.py) accumulates the entire pytest stdout in memory then `"".join(...)` into a second string (`[run_tests.py:1350`](../../run_tests.py)). For UI suites this is ~50 MB twice. Stream to a temp file, then read once for parsing. ~20 lines.
- **Always-log-stderr-on-failure in `_run_command`.** `[run_tests.py:751`](../../run_tests.py) only logs stderr when `--verbose`. Always log on non-zero exit. ~3 lines.

---

## Implementation order (recommendation)

1. **T1 batch (one commit)**: ship the bug fixes first. Builds confidence in the change pipeline.
2. **T2.2 `--dry-run`** before anything else in T2/T3, because everything later wants to verify "did I change command construction?" against this.
3. **T2.1 emoji replacement** and **T2.3 default verbosity**: parallel, both are visible and small.
4. **T3.3 coverage upgrades** and **T3.5 misc**: parallel; pure additions, low risk.
5. **T3.4 container ps batching**: ahead of T3.1 because it has zero UX risk.
6. **T3.1 `rich` TUI**: one PR, behind a flag, default off for one release.
7. **T3.2 file split**: last and largest. Hold until everything above is in.

## Out of scope (this spec)

- Replacing `make` targets. The split (T3.2) preserves the `run_tests.py` entrypoint.
- Renaming `RunTestType` enum values or breaking the test-type CLI surface.
- Changing the `tests/utils/test_environment.py` guard logic.
- Changing report formats (Allure, JUnit, HTML). Filenames change in T1.2 (suffix added) and T3.3 (new `coverage_*.json`).
- Speeding up the tests themselves. This spec is about the runner, not the test suite.

## Open questions

1. **Target coverage threshold for T3.3.** What is the current baseline? Suggest measuring before this spec is approved and setting `CTI_COVERAGE_FAIL_UNDER` to baseline-minus-2.
2. **Drop `output_format=progress` semantics in T2.3.** Does any CI parser depend on the current `-v` output? Audit `.github/workflows/` before merging T2.3.
3. **Python version floor.** The re-exec shim at the top of `run_tests.py` (`[run_tests.py:1-11`](../../run_tests.py)) handles 3.9. Will the split (T3.2) hold the same shim? Recommend: keep the shim in `run_tests.py`, all package modules require 3.10+.
4. **`rich` as a runtime dependency.** Verify it's already present in the test extras group; otherwise T3.1 needs a `pyproject.toml` change.

## Acceptance criteria for the spec as a whole

The spec is implementable when:

- [ ] Each Tier 1 item has been verified against `run_tests.py` at HEAD.
- [ ] Tier 2 has at least one reviewer pass.
- [ ] Tier 3.2 (file split) has a green dry-run output captured before work starts (the diff baseline).
- [ ] `CHANGELOG.md` has placeholder entries for any user-visible changes (T1.2 paths, T1.4 flag rename, T2.1 visual change, T2.3 verbosity).

## Appendix: line-number index

All references in this spec point to `run_tests.py` at the commit in which it was reviewed (see Background). Before implementing, re-grep to confirm the lines have not moved:

```
grep -n "_save_failure_log\|in_ci = \|--no-validate\|\\\\xe2\\\\x9c\\\\x93\|self.config.timeout - " run_tests.py
```
<!--stackedit_data:
eyJoaXN0b3J5IjpbMTk2NzE3MTM0OF19
-->