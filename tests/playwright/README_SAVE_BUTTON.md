# Workflow Save Button Tests

Automated Playwright tests for the workflow configuration save button functionality.

## Test Coverage

The test suite (`workflow_save_button.spec.ts`) covers:

1. **Initial State**
   - Button starts disabled and grey
   - Proper disabled styling (opacity, cursor)

2. **State Changes**
   - Button enables when threshold values change
   - Button enables when model selection changes
   - Button enables when description changes
   - Button tracks changes in all form fields

3. **Save Functionality**
   - Shows loading state ("Saving...") during save
   - Shows success state ("✓ Saved!") after save
   - Disables button after successful save
   - Handles form submission correctly

4. **Reset Functionality**
   - Button disables after reset
   - Form values reset correctly

5. **Auto-save Integration**
   - Button state updates when models change via auto-save

## Running Tests

### Run all save button tests:
```bash
npx playwright test tests/playwright/workflow_save_button.spec.ts
```

### Run specific test:
```bash
npx playwright test tests/playwright/workflow_save_button.spec.ts --grep "should enable save button when threshold"
```

### Run with UI (headed mode):
```bash
npx playwright test tests/playwright/workflow_save_button.spec.ts --headed
```

### Run with debug:
```bash
npx playwright test tests/playwright/workflow_save_button.spec.ts --debug
```

## Prerequisites

- Application running on `http://localhost:8001` (or set `CTI_SCRAPER_URL` env var)
- Playwright installed: `npm install` or `pnpm install`
- Browsers installed: `npx playwright install`

## Test Environment

Tests use the default base URL `http://localhost:8001` but can be overridden:
```bash
CTI_SCRAPER_URL=http://localhost:8001 npx playwright test tests/playwright/workflow_save_button.spec.ts
```

## Expected Behavior

1. **On Page Load**: Save button should be disabled (grey, opacity 0.5, cursor not-allowed)
2. **On Change**: Save button should enable (full opacity, cursor pointer)
3. **On Save**: Button shows "Saving..." then "✓ Saved!" then returns to normal
4. **After Save**: Button disables again if no new changes
5. **On Reset**: Button disables and form resets

## Debugging

If tests fail:
1. Check that the application is running
2. Verify the workflow page loads correctly
3. Check browser console for JavaScript errors
4. Run with `--headed` to see what's happening
5. Check screenshots in `test-results/` directory

