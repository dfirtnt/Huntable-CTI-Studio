import { defineConfig, devices } from '@playwright/test';
import { allure } from 'allure-playwright';

/**
 * Playwright configuration for CTIScraper tests.
 *
 * Projects group specs by feature area so runs can be batched:
 *   npx playwright test --project=agent-config
 *   npx playwright test --project=smoke
 *   npx playwright test --grep @smoke
 *
 * Tier system (mirrors run_tests.py ui-* aliases):
 *   - smoke      -> @smoke-tagged tests across all features (fast critical path)
 *   - <feature>  -> agent-config | workflow | sources | articles | intelligence | ui-misc
 *   - quarantine -> known-flaky / env-dependent suites (excluded from default runs)
 *
 * When CTI_EXCLUDE_AGENT_CONFIG_TESTS=1 (run_tests.py ui --exclude-markers
 * agent_config_mutation), specs that mutate agent/workflow config are ignored
 * so local config is not changed.
 */
const excludeAgentConfigTests = process.env.CTI_EXCLUDE_AGENT_CONFIG_TESTS === '1';

/* Quarantined specs are excluded from the default project list. To run them,
 * pass `--project=quarantine` explicitly (which sets CTI_INCLUDE_QUARANTINE=1
 * is not required when --project is given because Playwright honors the flag). */
const includeQuarantine = process.env.CTI_INCLUDE_QUARANTINE === '1';

const browser = { ...devices['Desktop Chrome'] };

const featureProjects = [
  {
    name: 'agent-config',
    use: browser,
    testMatch: /playwright\/agent_config_.*\.spec\.ts$/,
  },
  {
    name: 'workflow',
    use: browser,
    testMatch: [
      /playwright\/workflow_(?!executions\.spec).*\.spec\.ts$/,
      /playwright\/verify_workflow_.*\.spec\.ts$/,
      /playwright\/test_workflow_buttons\.spec\.ts$/,
      /playwright\/execution_detail_tabs\.spec\.ts$/,
      /playwright\/eval_workflow\.spec\.ts$/,
      /playwright\/expanded_prompt_editor_save\.spec\.ts$/,
    ],
  },
  {
    name: 'sources',
    use: browser,
    testMatch: [
      /playwright\/sources_page\.spec\.ts$/,
      /playwright\/chunk_coverage\.spec\.ts$/,
    ],
  },
  {
    name: 'articles',
    use: browser,
    testMatch: [
      /playwright\/article_detail\.spec\.ts$/,
      /playwright\/dashboard\.spec\.ts$/,
      /playwright\/navigation\.spec\.ts$/,
      /playwright\/chat\.spec\.ts$/,
      /playwright\/jobs\.spec\.ts$/,
    ],
  },
  {
    name: 'intelligence',
    use: browser,
    testMatch: [
      /playwright\/sigma_enrich\.spec\.ts$/,
      /playwright\/agent_evals_hunt_query\.spec\.ts$/,
      /playwright\/agent_evals_input_persistence\.spec\.ts$/,
      /playwright\/observables_selection\.spec\.ts$/,
      /playwright\/llm_optimizer_api\.spec\.ts$/,
      /playwright\/proctree_disable_persistence\.spec\.ts$/,
      /playwright\/os_fallback_toggle\.spec\.ts$/,
      /playwright\/model_selectors\.spec\.ts$/,
    ],
  },
  {
    name: 'ui-misc',
    use: browser,
    testMatch: [
      /playwright\/collapsible_sections\.spec\.ts$/,
      /playwright\/modal_.*\.spec\.ts$/,
      /playwright\/settings\.spec\.ts$/,
      /playwright\/verify_text_colors\.spec\.ts$/,
    ],
  },
];

const quarantineProject = {
  name: 'quarantine',
  use: browser,
  testMatch: [
    /playwright\/workflow_executions\.spec\.ts$/,
    /playwright\/observables_plain\.spec\.ts$/,
    /playwright\/observables_exact_selection\.spec\.ts$/,
  ],
};

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.(spec|test)\.(ts|js)$/,

  /* Exclude specs that mutate workflow/agent config when requested */
  ...(excludeAgentConfigTests && {
    testIgnore: [
      'playwright/agent_config_*.spec.ts',
      'playwright/workflow_save_button.spec.ts',
      'playwright/workflow_config_persistence.spec.ts',
      'playwright/workflow_config_versions.spec.ts',
    ],
  }),

  /* Run tests in files in parallel for speed */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Local: cap at 4 workers to avoid macOS ENFILE (file table overflow) from
   * allure-playwright writing many JSON results simultaneously.
   * CI keeps 2 for stability. */
  workers: process.env.CI ? 2 : 4,

  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],
    ['line'],
    ['allure-playwright', {
      outputFolder: 'allure-results',
      suiteTitle: false
    }]
  ],

  /* Maximum time one test can run for. */
  timeout: 300000, // 5 minutes for slow workflow tests

  /* Shared settings for all the projects below. */
  use: {
    baseURL: process.env.CTI_SCRAPER_URL || 'http://localhost:8001',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  /*
   * Feature-grouped projects.
   *
   * Default run executes everything except `quarantine`. To run a single
   * batch: `npx playwright test --project=<name>`.
   * To run only fast smoke checks across all features:
   *   `npx playwright test --grep @smoke`
   */
  projects: includeQuarantine
    ? [...featureProjects, quarantineProject]
    : featureProjects,

  /* Global setup to check web server health before tests */
  globalSetup: require.resolve('./playwright/global-setup.ts'),
});
