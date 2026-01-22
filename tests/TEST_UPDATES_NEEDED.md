# Test Updates Required After Recent Changes

## Summary of Changes Made
1. **Observables Mode disabled**: Button hidden in `article_detail.html`, marked as "INACTIVE: Planned for future release"
2. **Huntability Mode button disabled**: Made non-clickable (disabled attribute)
3. **Observable Training card hidden**: Removed from `mlops.html` (commented out)
4. **Observable Training page**: Added inactive notice banner
5. **Operational Checklist removed**: User removed from `mlops.html`

## Tests Requiring Updates

### 1. `tests/ui/test_article_detail_advanced_ui.py`

**File**: `test_observable_annotation_creation_and_review` (lines 210-262)

**Issue**: Tries to click `#annotation-mode-observables` which is now hidden/disabled

**Action**: Skip or update test:
```python
@pytest.mark.ui
@pytest.mark.articles
@pytest.mark.skip(reason="Observables mode is inactive - planned for future release")
def test_observable_annotation_creation_and_review(self, page: Page):
    # ... existing test code ...
```

### 2. `tests/playwright/observables_selection.spec.ts`

**Issue**: Line 17-19 tries to click `#annotation-mode-observables` which is now hidden

**Action**: Skip entire test suite:
```typescript
test.describe.skip('Observable annotation selection', () => {
  // ... existing tests ...
});
```

### 3. `tests/playwright/observables_plain.spec.ts`

**Issue**: Line 67 tries to click "Observables Mode" button which is now hidden

**Action**: Skip entire test suite:
```typescript
test.describe.skip('Observables plain selection', () => {
  // ... existing tests ...
});
```

### 4. `tests/playwright/observables_exact_selection.spec.ts`

**Issue**: Lines 8-10 try to click `#annotation-mode-observables` which is now hidden

**Action**: Skip entire test suite:
```typescript
test.describe.skip('Observables exact selection (plain surface)', () => {
  // ... existing tests ...
});
```

### 5. `tests/ui/test_observable_training_ui.py`

**Issue**: Tests observable training page which now shows inactive notice

**Action**: Update to verify inactive notice is present:
```python
@pytest.mark.ui
def test_observable_training_page_loads(self, page: Page):
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    page.goto(f"{base_url}/observables-training")
    page.wait_for_load_state("networkidle")

    # Verify inactive notice is present
    inactive_notice = page.locator("text=Feature Inactive - Planned for Future Release")
    expect(inactive_notice).to_be_visible()
    
    # Original heading should still be present
    heading = page.locator("text=Observable Extractor Training")
    expect(heading).to_be_visible()
```

### 6. Tests for Huntability Mode Button

**Issue**: Any tests that verify the Huntability Mode button is clickable need updating

**Action**: Update expectations to verify button is disabled:
```python
huntability_btn = page.locator("#annotation-mode-huntability")
expect(huntability_btn).to_be_visible()
expect(huntability_btn).to_be_disabled()
```

### 7. Tests for Observable Training Card in MLOps

**Issue**: Any tests checking for Observable Training card in MLOps page

**Action**: Remove or skip tests that look for:
- Observable Training card
- "Manage Observables" link
- Observable Training section

### 8. Tests for Operational Checklist

**Issue**: User removed Operational Checklist from `mlops.html`

**Action**: Remove any tests that verify:
- Operational Checklist section
- `.mlops-checklist` class
- `.mlops-gear-icon` class
- Checklist items

## Recommended Approach

1. **Skip observables tests** with clear reason: "Observables mode is inactive - planned for future release"
2. **Update observable training UI test** to verify inactive notice
3. **Update Huntability Mode button tests** to verify it's disabled
4. **Remove Operational Checklist tests** if they exist

## Notes

- All observables-related code is preserved in comments for future activation
- Huntability annotation system remains fully functional
- Tests can be re-enabled when observables feature is activated
