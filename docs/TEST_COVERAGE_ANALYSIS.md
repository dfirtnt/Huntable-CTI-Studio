# Workflow Page Test Coverage Analysis

## Current Coverage ✅

### Collapsible Panels
- ✅ Header click expands/collapses panels (7 panels tested)
- ✅ Caret text updates (▼/▲)
- ✅ Multiple panels can be toggled independently
- ✅ Nested panels (sub-agents) work correctly

### Configuration Functionality
- ✅ Form validation (thresholds, ranges)
- ✅ Autosave on input changes
- ✅ Toggle interactions and state management
- ✅ Provider/model switching
- ✅ Preset loading/restoration
- ✅ Save button state management
- ✅ Prompt editing and saving

## Missing Coverage 🚧

### 1. **Keyboard Navigation** (REQUIRED by AGENTS.md)
**Priority: HIGH** - Accessibility requirement

Missing tests:
- [ ] Enter key expands/collapses panel
- [ ] Space key expands/collapses panel
- [ ] Tab navigation to panel headers
- [ ] Focus management when panels expand/collapse
- [ ] Keyboard navigation between panels

**Implementation**: Lines 451-457 in `base.html` - keyboard handler exists but untested

---

### 2. **ARIA Attributes** (REQUIRED by AGENTS.md)
**Priority: HIGH** - Accessibility requirement

Missing tests:
- [ ] Headers have `role="button"`
- [ ] Headers have `tabindex="0"`
- [ ] Headers have `aria-controls` pointing to content
- [ ] Headers have `aria-expanded` (true/false) bound to state
- [ ] Toggle icons have `aria-hidden="true"`
- [ ] ARIA attributes update when panel state changes

**Implementation**: Lines 405-413, 417 in `base.html` - attributes set but untested

---

### 3. **Interactive Element Click Prevention** (REQUIRED by AGENTS.md)
**Priority: HIGH** - Critical UX requirement

Missing tests:
- [ ] Clicking button inside header does NOT toggle panel
- [ ] Clicking input inside header does NOT toggle panel
- [ ] Clicking select inside header does NOT toggle panel
- [ ] Clicking label inside header does NOT toggle panel
- [ ] Clicking link inside header does NOT toggle panel
- [ ] Clicking textarea inside header does NOT toggle panel

**Implementation**: Lines 420-430 in `base.html` - prevention logic exists but untested

---

### 4. **Panel Initialization**
**Priority: MEDIUM**

Missing tests:
- [ ] `initCollapsiblePanels()` called on page load
- [ ] Panels initialized after config reload
- [ ] Panels initialized after tab switch
- [ ] Panels initialized after dynamic content added (prompts)
- [ ] No duplicate event handlers after re-initialization

**Implementation**: Multiple calls to `initCollapsiblePanels()` in workflow.html (lines 3505, 3855, 5611, etc.)

---

### 5. **Dynamic Panel Addition**
**Priority: MEDIUM**

Missing tests:
- [ ] Prompt panels initialized after `renderAgentPrompts()`
- [ ] QA prompt panels initialized after enabling QA
- [ ] Sub-agent panels initialized after rendering
- [ ] Panels work correctly after dynamic addition

**Implementation**: `initCollapsiblePanels(container)` called with specific containers

---

### 6. **Panel State Persistence**
**Priority: LOW**

Missing tests:
- [ ] Panel state persists during form interactions
- [ ] Panel state persists during autosave
- [ ] Panel state persists during config reload (if implemented)
- [ ] Multiple panels can be expanded simultaneously

---

### 7. **Edge Cases**
**Priority: LOW**

Missing tests:
- [ ] Panel with missing content element (should not initialize)
- [ ] Panel with missing toggle element (should still work)
- [ ] Rapid clicking (debouncing/prevention)
- [ ] Panel initialization with invalid panelId

---

## Recommended Test Files to Create

### 1. `tests/playwright/workflow_collapsible_accessibility.spec.ts` (NEW)
**Purpose**: Test keyboard navigation and ARIA attributes

**Tests needed**:
```typescript
- should toggle panel with Enter key
- should toggle panel with Space key
- should have proper ARIA attributes on headers
- should update aria-expanded when panel toggles
- should mark toggle icon as aria-hidden
- should be keyboard focusable (tabindex="0")
```

### 2. `tests/playwright/workflow_collapsible_interactive_elements.spec.ts` (NEW)
**Purpose**: Test click prevention on interactive elements

**Tests needed**:
```typescript
- should not toggle when clicking button inside header
- should not toggle when clicking input inside header
- should not toggle when clicking select inside header
- should not toggle when clicking label inside header
- should not toggle when clicking link inside header
```

### 3. `tests/playwright/workflow_collapsible_initialization.spec.ts` (NEW)
**Purpose**: Test panel initialization and dynamic addition

**Tests needed**:
```typescript
- should initialize panels on page load
- should initialize panels after config reload
- should initialize dynamically added prompt panels
- should not create duplicate event handlers
- should handle missing content element gracefully
```

### 4. Update `tests/playwright/collapsible_sections.spec.ts`
**Add tests**:
```typescript
- should allow multiple panels expanded simultaneously
- should maintain panel state during form interactions
```

---

## Priority Summary

| Priority | Category | Tests Needed | Impact |
|----------|----------|--------------|--------|
| **HIGH** | Keyboard Navigation | 5 tests | Accessibility compliance |
| **HIGH** | ARIA Attributes | 6 tests | Accessibility compliance |
| **HIGH** | Interactive Element Prevention | 6 tests | Critical UX requirement |
| **MEDIUM** | Panel Initialization | 5 tests | Dynamic content support |
| **MEDIUM** | Dynamic Panel Addition | 4 tests | Prompt rendering |
| **LOW** | State Persistence | 4 tests | User experience |
| **LOW** | Edge Cases | 4 tests | Robustness |

**Total**: ~34 new tests recommended

---

## Implementation Notes

1. **Keyboard tests** should use `page.keyboard.press('Enter')` and `page.keyboard.press('Space')`
2. **ARIA tests** should check attributes: `getAttribute('role')`, `getAttribute('aria-expanded')`, etc.
3. **Click prevention tests** should click interactive elements and verify panel doesn't toggle
4. **Initialization tests** should verify `data-collapsible-initialized` attribute and event handlers

---

## AGENTS.md Compliance Check

From `AGENTS.md` requirements:
- ✅ Entire header toggles expand/collapse (tested)
- ✅ Caret is INDICATIVE ONLY (tested)
- ✅ Pointer cursor on full header (visual, not tested)
- ✅ Caret reflects expanded/collapsed state (tested)
- ⚠️ Header is `<button>` or `role="button"` (NOT TESTED)
- ⚠️ `aria-expanded` bound to state (NOT TESTED)
- ⚠️ Keyboard support (Enter + Space) (NOT TESTED)
- ⚠️ Caret is decorative (`aria-hidden="true"`) (NOT TESTED)
- ⚠️ Interactive elements inside headers MUST NOT toggle (NOT TESTED)

**Compliance**: 4/9 requirements tested, 5/9 missing
