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

### `scrollToStep(n)` — explicit before/after

`scrollToStep` intentionally does **not** enforce the no-op rule for an already-active section — scrolling and rail-highlight updates are still desirable on re-click. Only the open/close logic is made exclusive.

**Before (lines 1342–1351):**
```js
function scrollToStep(n) {
  var section = document.getElementById('s' + n);
  var content = document.getElementById('config-content');
  if (!section || !content) return;
  if (!section.classList.contains('open')) section.classList.add('open');
  content.scrollTo({ top: section.offsetTop - 16, behavior: 'smooth' });
  document.querySelectorAll('.rail-item').forEach(function(el, i) {
    el.classList.toggle('active', i === n);
  });
}
```

**After:**
```js
function scrollToStep(n) {
  var section = document.getElementById('s' + n);
  var content = document.getElementById('config-content');
  if (!section || !content) return;
  var target = 's' + n;
  ['s0','s1','s2','s3','s4','s5','s6'].forEach(function(sid) {
    var s = document.getElementById(sid);
    if (s && sid !== target) s.classList.remove('open');
  });
  section.classList.add('open');
  content.scrollTo({ top: section.offsetTop - 16, behavior: 'smooth' });
  document.querySelectorAll('.rail-item').forEach(function(el, i) {
    el.classList.toggle('active', i === n);
  });
}
```

Key differences from the old version: sibling-close sweep replaces the conditional guard; `var target = 's' + n` avoids repeated concatenation and makes the comparison unambiguous.

### `toggleSA(id)` — no change

`toggleSA` uses IDs prefixed `sa-` (`sa-cmdline`, `sa-proctree`, `sa-huntqueries`, etc.) — none of which appear in the `['s0'…'s6']` sibling list. Independence is structurally guaranteed by the disjoint ID namespaces.

### CSS — no change

### HTML — no change

## Initial-Load Invariant

`s0` has `class="step-section open"` hardcoded in the HTML. This satisfies rule 1 ("one section open at all times") on first load without any JS.

**Fragility note:** if the hardcoded `open` is ever removed (e.g. for a saved-state restore feature), `toggle()`'s early-return guard (`if … el.classList.contains('open')) return`) would prevent any section from ever opening, since no section starts open. To guard against this, a `DOMContentLoaded` safety net should be added if the hardcoded `open` is ever removed:

```js
// Safety net — only needed if hardcoded open on s0 is removed in future
document.addEventListener('DOMContentLoaded', function() {
  var hasOpen = document.querySelector('.step-section.open');
  if (!hasOpen) {
    var first = document.getElementById('s0');
    if (first) first.classList.add('open');
  }
});
```

For the current implementation this safety net is **out of scope** — the hardcoded `open` on `s0` is the source of truth.

## Files Touched

| File | Change |
|------|--------|
| `src/web/templates/workflow.html` | Rewrite `toggle()`, patch `scrollToStep()` |

## Out of Scope

- Animation/transition between sections (existing CSS transitions are preserved as-is)
- Persisting open-section state across page reloads
- Any change to the sub-agent prompt accordion system
