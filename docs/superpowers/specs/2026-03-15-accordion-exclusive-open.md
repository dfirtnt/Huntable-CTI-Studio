# Spec: Accordion Exclusive-Open for Pipeline Steps

**Date:** 2026-03-15
**Status:** Approved
**Scope:** `src/web/templates/workflow.html` — inline `<script>` block only

---

## Problem

The Operator Console pipeline steps (s0–s6) currently allow multiple sections to be open simultaneously. The desired behaviour is accordion-style: exactly one section is always open, and opening a new section closes the previously open one.

## Behaviour Rules

1. **One section open at all times** — clicking an already-open section header does nothing.
2. **Opening a new section closes all others** — sections s0–s6 are mutually exclusive.
3. **Sub-agent prompt panels are unaffected** — `toggleSA()` remains independent; prompt panels within a section can still be opened/closed freely regardless of accordion state.
4. **Rail navigation enforces the same rule** — clicking a rail node via `scrollToStep(n)` also closes all other sections before opening the target.

## Changes

### `toggle(id)` — rewrite

```js
function toggle(id) {
  var el = document.getElementById(id);
  if (!el || el.classList.contains('open')) return;
  ['s0','s1','s2','s3','s4','s5','s6'].forEach(function(sid) {
    if (sid !== id) {
      var s = document.getElementById(sid);
      if (s) s.classList.remove('open');
    }
  });
  el.classList.add('open');
}
```

### `scrollToStep(n)` — add sibling-close before existing add

Before the existing `section.classList.add('open')` line, insert:
```js
['s0','s1','s2','s3','s4','s5','s6'].forEach(function(sid) {
  var s = document.getElementById(sid);
  if (s && 's' + n !== sid) s.classList.remove('open');
});
```

### `toggleSA(id)` — no change

### CSS — no change

### HTML — no change

## Files Touched

| File | Change |
|------|--------|
| `src/web/templates/workflow.html` | Rewrite `toggle()`, patch `scrollToStep()` |

## Out of Scope

- Animation/transition between sections (existing CSS transitions are preserved as-is)
- Persisting open-section state across page reloads
- Any change to the sub-agent prompt accordion system
