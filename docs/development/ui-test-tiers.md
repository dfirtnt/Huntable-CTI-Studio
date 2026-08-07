# UI Test Tiers

<!-- AUDIT: Accuracy -- 2026-07-17: counts below were stale (from before the "UI test diet" commits that cut
     the suite, e.g. 1a490501, f1e1db0e, 24d78955). Re-measured directly: `pytest --collect-only tests/ui/`
     collects 116 tests; `npx playwright test --config tests/playwright.config.ts --list` reports
     "218 tests in 33 files" for the default (non-quarantine) project set. Time estimates in the table below
     are not re-verified (would require a full ~45min run) and are left as-is. -->
The UI suite (116 pytest browser tests + 218 Playwright specs across 33 files)
takes ~45 minutes end to end. The tier system below lets you pick the right
slice for the moment so you do not pay the full cost on every change.

## Tiers at a glance

| Tier         | Command                              | What it runs                                      | Target time |
|--------------|--------------------------------------|---------------------------------------------------|-------------|
| 1. Smoke     | `python3 run_tests.py ui-smoke`       | pytest `ui_smoke` + `smoke` markers; no Playwright | < 2 min     |
| 2. Touched   | `python3 run_tests.py ui-fast --area=<X>` | pytest UI (no slow) + one Playwright project | 3-7 min     |
| 3. Fast      | `python3 run_tests.py ui-fast`        | full UI minus `@slow` (mobile/a11y/perf), parallel | 10-15 min   |
| 4. Full      | `python3 run_tests.py ui-full`        | everything including `@slow` and quarantined suites | ~45 min     |

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

<!-- AUDIT: Accuracy -- file counts re-measured 2026-07-17 via `npx playwright test --config tests/playwright.config.ts --list`,
     grouped by project. Previous counts (and some "what it covers" descriptions) referenced spec files removed by
     the UI test-suite reduction commits (e.g. navigation.spec.ts, chat.spec.ts, chunk_coverage.spec.ts,
     agent_evals_hunt_query.spec.ts, observables_selection.spec.ts) that no longer exist on disk; the config's
     `testMatch` patterns for those files are now dead (match zero files), including all three `quarantine`
     patterns. -->
| Area           | Files | What it covers                                             |
|----------------|-------|------------------------------------------------------------|
| `agent-config` | 14    | `agent_config_*.spec.ts` -- presets, validation, autosave  |
| `workflow`     | 8     | execution detail tabs, prompt editor, workflow config persistence/versions, platform badge/detection |
| `sources`      | 1     | sources page                                                |
| `articles`     | 3     | article detail, dashboard, jobs                             |
| `intelligence` | 3     | sigma enrich, sigma queue lifecycle, sigma similarity unification |
| `ui-misc`      | 4     | collapsible sections, modals, settings                     |
| `quarantine`   | 0     | patterns reference files that no longer exist (dead config; see audit note) |

Run a single area: `npx playwright test --config tests/playwright.config.ts --project=sources`
or via the runner: `python3 run_tests.py ui-fast --area=sources`.

## Tags and exclusions

- `@pytest.mark.slow` -- mobile responsiveness, accessibility, performance.
  <!-- AUDIT: Accuracy -- `pytest --collect-only -m slow tests/ui/` collects 0 tests as of 2026-07-17 (6 tests
       repo-wide carry the marker, none under tests/ui/); the "~76 tests" figure is stale. Excluding this marker
       from tiers 1-3 is currently a no-op for the pytest side. -->
  Excluded from tiers 1-3, included in tier 4.
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

_Last updated: 2026-07-03_
