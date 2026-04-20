# UI Test Tiers

The UI suite (627 pytest browser tests + 355 Playwright specs across 49 files)
takes ~45 minutes end to end. The tier system below lets you pick the right
slice for the moment so you do not pay the full cost on every change.

## Tiers at a glance

| Tier         | Command                              | What it runs                                      | Target time |
|--------------|--------------------------------------|---------------------------------------------------|-------------|
| 1. Smoke     | `python run_tests.py ui-smoke`       | pytest `ui_smoke` + `smoke` markers; no Playwright | < 2 min     |
| 2. Touched   | `python run_tests.py ui-fast --area=<X>` | pytest UI (no slow) + one Playwright project | 3-7 min     |
| 3. Fast      | `python run_tests.py ui-fast`        | full UI minus `@slow` (mobile/a11y/perf), parallel | 10-15 min   |
| 4. Full      | `python run_tests.py ui-full`        | everything including `@slow` and quarantined suites | ~45 min     |

## When to use which

- **Tier 1 (smoke)** -- during active work. Use after every couple of edits.
  Confirms the app boots and the core pages render.
- **Tier 2 (touched)** -- before you commit. Pick the `--area` matching what
  you changed (`agent-config`, `workflow`, `sources`, `articles`,
  `intelligence`, `ui-misc`).
- **Tier 3 (fast)** -- before you push. Catches cross-feature regressions
  without paying for mobile / accessibility / performance sweeps.
- **Tier 4 (full)** -- nightly or pre-release. Run via `/loop` or a cron.

## Playwright feature areas (`--area`)

Defined in `tests/playwright.config.ts` as projects. Each project owns a
disjoint set of spec files:

| Area           | Files | What it covers                                             |
|----------------|-------|------------------------------------------------------------|
| `agent-config` | 14    | `agent_config_*.spec.ts` -- presets, validation, autosave  |
| `workflow`     | 16    | workflow save/config/persistence, execution detail tabs    |
| `sources`      | 2     | sources page, chunk coverage                               |
| `articles`     | 5     | article detail, dashboard, navigation, jobs                |
| `intelligence` | 7     | sigma enrich, hunt query evals, observables, optimizer     |
| `ui-misc`      | 5     | collapsible sections, modals, settings, text colors        |
| `quarantine`   | 3     | known-flaky / env-dependent (workflow_executions, observables_plain/exact) |

Run a single area: `npx playwright test --config tests/playwright.config.ts --project=sources`
or via the runner: `python run_tests.py ui-fast --area=sources`.

## Tags and exclusions

- `@pytest.mark.slow` -- mobile responsiveness, accessibility, performance
  (~76 tests). Excluded from tiers 1-3, included in tier 4.
- `@pytest.mark.ui_smoke` -- ~10 critical browser smoke tests, hand-tagged.
- `@pytest.mark.smoke` -- ~30 fast httpx-based page-load checks.
- `@pytest.mark.agent_config_mutation` -- tests that mutate live agent/workflow
  config; excluded by default to keep your local config stable. Pass
  `--include-agent-config-tests` to include them.
- `quarantine` Playwright project -- excluded by default. Tier 4 sets
  `CTI_INCLUDE_QUARANTINE=1` to opt back in.

## Parallelism

- Pytest UI tiers run with `-n 4` workers by default (matches Playwright's
  worker cap on macOS to avoid `ENFILE` overflow).
- `--serial` disables pytest parallelism (useful when chasing flakes).
- `--parallel` opts into `-n auto` (all CPU cores) -- only safe for
  pytest-only runs that do not also start Playwright.
- Playwright is always parallel (4 workers locally, 2 on CI), regardless
  of pytest flags.

## Adding a new spec to the right area

When you add `tests/playwright/your_spec.spec.ts`, update
`tests/playwright.config.ts` -- add the filename pattern to the matching
project's `testMatch` list. If a spec is not in any project, the default run
will silently skip it.
