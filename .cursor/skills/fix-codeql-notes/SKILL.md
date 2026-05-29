---
name: fix-codeql-notes
description: Fix non-complex CodeQL note-severity alerts — unused imports, unused local variables, unused global variables — in Python files. Run this skill when CodeQL surfaces py/unused-import, py/unused-local-variable, py/unused-global-variable, or py/repeated-import alerts. Produces only minimal, targeted edits; never refactors unrelated code.
---

# Fix CodeQL Notes (Unused Imports / Variables)

Resolves the following CodeQL rule IDs — all note severity, all mechanical fixes:

| Rule ID | What triggers it |
|---|---|
| `py/unused-import` | `import X` or `from M import X` where `X` is never referenced |
| `py/repeated-import` | The same module imported twice (second import is redundant) |
| `py/unused-local-variable` | A local variable is assigned but its value is never read |
| `py/unused-global-variable` | A module-level variable is defined but never referenced |

---

## Step 0 — Gather the alert list

Pull the current open alerts from GitHub (do not guess):

```bash
gh api repos/{owner}/{repo}/code-scanning/alerts \
  --paginate \
  -q '.[] | select(.state=="open") | select(.rule.id | test("py/unused-import|py/repeated-import|py/unused-local-variable|py/unused-global-variable")) | {rule: .rule.id, file: .most_recent_instance.location.path, start_line: .most_recent_instance.location.start_line, message: .most_recent_instance.message.text}'
```

Group alerts by file. Process one file at a time (read → edit → verify).

---

## Step 1 — For each file: Read it, then apply the right fix

Read the full file before editing anything. Understand context — an unused name might be inside a `try/except` guard, a `TYPE_CHECKING` block, or `__all__`.

### Rule: `py/unused-import` and `py/repeated-import`

**Fix decision tree (in order):**

1. **Is the import in `__all__`?** → Keep it. Not a real unused import; CodeQL can be wrong here.
2. **Is the import inside `if TYPE_CHECKING:` block?** → Keep it; it exists only for type annotations.
3. **Is the import in a `try/except ImportError` guard and is it truly never referenced anywhere in the file?** → Delete the entire `from M import X` line (or the name from a multi-name import).
4. **Repeated import (`py/repeated-import`):** Delete whichever occurrence is farther from the actual use site. Typically the earlier one is the stale copy.
5. **Plain unused import with no special context:** Delete the import line. If it's part of a multi-name import (`from M import A, B, C`), remove only the unused names; reformat the line if it becomes a single name.

**Do NOT add `# noqa` comments.** `# noqa: F401` suppresses ruff/flake8, not CodeQL. The fix must be a real code change.

**Do NOT add `_ = SomeName` usage stubs** unless the import is side-effectful and you have confirmed the side effect is intentional. Ask the user if unsure.

### Rule: `py/unused-local-variable`

**Fix decision tree:**

1. **Is the variable used in an `assert` or logging call later in the same scope?** → CodeQL may have fired on a shadowing assignment. Read more carefully; if it IS used, skip — this is a false positive, leave the code alone.
2. **Is the assignment a function call whose return value is discarded (e.g., `result = some_call()` but `result` is never read)?**
   - If the call has side effects you want to preserve: replace `result = some_call()` → `some_call()`. Drop the assignment entirely.
   - If the call is purely for its return value and discarding it is clearly intentional (e.g., unpacking in `for`): prefix with `_`: `_result = some_call()`.
3. **Is the variable used in a `with` statement or unpacking context where discarding is idiomatic?** → Prefix with `_`.
4. **Truly dead assignment (value overwritten before read, or scope ends without use):** Delete the assignment line if the call has no side effects; otherwise convert to a bare call.

### Rule: `py/unused-global-variable`

**Fix decision tree:**

1. **Is the variable in `__all__` or part of the public API?** → Keep it; CodeQL is wrong here.
2. **Is it prefixed with `_` already?** → It's private but still flagged. Safe to delete if grep confirms zero references in the entire repo.
3. **No references anywhere in the repo (grep confirms)?** → Delete the assignment and any associated comment block. If it's a compiled regex (`re.compile(...)`) with a descriptive comment, delete both.
4. **Partial usage (used in some branches but not others)?** → This is a more complex case; leave it for a human review and skip.

---

## Step 2 — Verify (mandatory)

After editing each file, run the tests relevant to that file:

```bash
python run_tests.py --filter <module_or_test_path>
```

For script files with no direct unit tests, run the linter to confirm no syntax errors:

```bash
python -m py_compile <file>
ruff check <file>
```

---

## Step 3 — Commit

Group all fixes for a single CodeQL rule ID into one commit. Use message format:

```
fix(codeql): remove unused imports / locals / globals (py/<rule-id>)
```

Example:
```
fix(codeql): remove unused imports in run_tests.py and scripts (py/unused-import)
fix(codeql): drop unused local variables in tests and evaluation_api (py/unused-local-variable)
fix(codeql): remove unused module-level constants (py/unused-global-variable)
```

---

## Safety constraints

- **Never remove an import that appears in `__all__`**, a decorator, a type annotation string literal, or a `getattr`/`importlib` dynamic lookup.
- **Never touch `vulture_whitelist.py`** — its "ineffectual statements" are intentional Vulture false-positive suppressors; a different CodeQL rule fires there (`py/ineffectual-statement`) and those require separate handling.
- **Never edit files that have `# type: ignore` lines related to the import** without understanding why.
- **One file at a time.** Read the file fully before editing; do not batch edits across files in a single Edit call unless the files are trivially small and unrelated.
- **Do not fix `py/empty-except`, `py/cyclic-import`, `py/path-injection`, or `py/jinja2/autoescape-false`** — those are out of scope for this skill (they require non-mechanical judgment).

---

## Quick reference — current open alerts in this repo

Run Step 0 to get the live list. As of the last audit, the in-scope alerts are:

### `py/unused-import`
| File | Unused names |
|---|---|
| `run_tests.py` | `PerformanceProfiler`, `start_performance_monitoring`, `stop_performance_monitoring` (lines 113–115, inside `try` guard) |
| `scripts/verify_backup.py` | `shutil` |
| `scripts/restore_database.py` | `shutil` |

### `py/repeated-import`
| File | Duplicate |
|---|---|
| `run_tests.py` | `asyncio` — imported on line 60; re-imported inside `if __name__ == "__main__"` block (line 135) |
| `tests/services/test_rank_prompt_parser.py` | `json` — imported twice |

### `py/unused-local-variable`
| File | Variable | Fix |
|---|---|---|
| `tests/unit/test_restore_database_v2.py` | `stopped` (in `test_stop_calls_docker_stop_for_each_container`) | bare call: `restore._stop_app_containers()` |
| `scripts/_restore_common.py` | `upper` (~line 124) | remove the assignment line; `upper` is already computed correctly in surrounding code |
| `src/web/routes/evaluation_api.py` | `executions_by_id` (~line 2077 block) | verify which block is the dead one; remove the dead assignment |
| `tests/test_database.py` | `manager` | bare call or `_manager = ...` |
| `tests/workflows/test_agentic_workflow.py` | `return_error_for_cmdline` | bare call or prefix `_` |

### `py/unused-global-variable`
| File | Variable | Fix |
|---|---|---|
| `src/services/proc_tree_attention_preprocessor.py` | `_EXE_TOKEN_RE` (~line 159) | Delete — confirmed zero references across entire repo |
| `src/services/proc_tree_attention_preprocessor.py` | `_WEAK_REGEX_INDICES` (~line 101) | Delete — confirmed zero references; `_STRONG_REGEX_INDICES` is separate and may be used, check independently |
| `tests_runner/tui.py` | `_RunnerTUI` | **FALSE POSITIVE — skip.** `_RunnerTUI` is a re-export alias imported by `tests_runner/runner.py` and `tests/test_run_tests_parsing.py`. CodeQL cannot see cross-file re-exports. Do NOT delete. |
| `run_tests.py` | `DEBUGGING_AVAILABLE` | Delete both the `= True` and `= False` branches in the try/except block. Confirmed unused in `run_tests.py` (the same-named var in `tests_runner/runner.py` is a separate definition and IS used there). |
