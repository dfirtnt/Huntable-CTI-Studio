# UI Design System Contract Audit

**Date:** 2026-07-20
**Scope:** All 26 templates in `src/web/templates/*.html`
**Contract:** `docs/contracts/ui-designer.md` (authoritative)
**Linter baseline:** `scripts/check_ui_contract.py` (BASELINE dict)

---

## Executive Summary

| Rule | Status | New Violations |
|---|---|---|
| 1 — Card containers | **FAIL** | 33 new occurrences across 8 templates |
| 2 — Hardcoded colors | **FAIL** | 57 new inline `style=""` violations (hex/rgba) |
| 3 — Typography | **PASS** | 0 violations |
| 4 — Modals / overlays | **FAIL** | 20 modal overlays missing role/aria |
| 5 — Dark mode | **PASS** | `class="dark"` and `tailwind.config` confirmed |
| 6 — Emoji | **PASS** | All emoji in toast strings, help text, empty-state illustrations (allow-list) |
| 7 — Reserved classes | **PASS** | 0 redefinitions outside canonical files |
| 8 — Accessibility (ARIA) | **FAIL** | 21 violations (19 modals + 2 toggle switches) |
| 9 — Spacing | **FAIL** | 29 spacing-class violations |
| 10 — `!important` | **PASS** | 233 occurrences — all in `<style>` blocks (print/third-party overrides, compliant) |
| 11 — ASCII-only | **FAIL** | 115 em-dash + 16 ellipsis in visible text/JS (not in `<style>`) |

**Overall: 5 PASS, 6 FAIL**

---

## Rule 1 — Card Containers

Card containers must use `.card` / `.card-elevated` / `.card-interactive`. The deprecated stack `bg-gray-800 border border-gray-700 rounded-lg` is banned outside the baseline set.

| File | New occurrences | Context |
|---|---|---|
| `workflow.html` | 20 | Modal overlays using `bg-gray-800 border border-gray-700 rounded-lg shadow-xl` |
| `sigma_similarity_test.html` | 4 | Card-like wrapper divs |
| `agent_evaluation.html` | 3 | Score/result cards |
| `article_detail.html` | 1 (over baseline 3→4) | `bg-gray-800 border border-gray-700` on help bubble at line 275 |
| `observable_training.html` | 2 | Training result panels |
| `evaluations.html` | 1 | Evaluation score card |
| `hunt_metrics.html` | 1 | Metric display card |
| `subagent_evaluation.html` | 1 | Subagent score card |

**Action required:** Replace all deprecated `bg-gray-800 border border-gray-700 rounded-lg` with the `.card` design token.

---

## Rule 2 — Hardcoded Colors

Inline `style=""` attributes must not contain bare hex (`#xxx` / `#xxxxxx`) or `rgba()` — use CSS custom properties via `var()` instead. Grandfathered baseline: `agent_evals.html:8`, `workflow.html:1`.

| File | Total `style=""` hex/rgba | Baseline | New violations |
|---|---|---|---|
| `agent_evals.html` | 38 | 8 | **30** |
| `workflow.html` | 11 | 1 | **10** |
| `agent_evals2.html` | 5 | 0 | **5** |
| `sigma_evals.html` | 5 | 0 | **5** |
| `sources.html` | 3 | 0 | **3** |
| `article_detail.html` | 2 | 0 | **2** |
| `ml_hunt_comparison.html` | 2 | 0 | **2** |
| `scraper_metrics.html` | 2 | 0 | **2** |

**Note:** `sources.html` uses `var(--x, #hex)` fallback syntax — these are compliant (fallback pattern accepted per contract). Actual new violations are concentrated in `agent_evals.html`, `workflow.html`, `agent_evals2.html`, and `sigma_evals.html` `<style>` blocks with hardcoded `rgba()` in inline style attributes.

---

## Rule 3 — Typography

All text classes verified against the allowed set: `text-xs`, `text-sm`, `text-base`, `text-lg`, `text-xl`.

**Result: 0 violations. PASS.**

---

## Rule 4 — Modals / Overlays

Ad-hoc `classList.toggle('hidden')` in `onclick` handlers is permitted only for overflow menus and collapsible panels — not for modals. No modal-like ad-hoc toggles were found outside the 19 modals that use ModalManager (Rule 8 violations below).

All 8 `onclick` + `classList.toggle('hidden')` occurrences are overflow-menu toggles (`footer-overflow-menu`) in `workflow.html` — **compliant, no violations**.

---

## Rule 5 — Dark Mode

- `base.html` line 1: `class="dark"` on `<html>` ✓
- `base.html` line 141: `tailwind.config = { darkMode: 'class' }` ✓

**Result: PASS.**

---

## Rule 6 — Emoji

All emoji occurrences are in JS toast strings (`toast.info()`, `toast.success()`), help/body text, or empty-state illustrations (`📊` in `partials/empty_state.html`). These are all on the Section 5.0.3 allow-list.

**Result: 0 violations. PASS.**

---

## Rule 7 — Reserved Classes

All reserved classes (`.card-header`, `.card-title`, `.card-meta`, `.card-actions`, `.card-title-row`, `.diag-card`, `.diag-card-title`, `.diag-card-meta`, `.nav-item`, `.quality-*`, `.priority-*`) are defined only in their canonical files.

**Result: 0 redefinitions. PASS.**

---

## Rule 8 — Accessibility (ARIA)

### Modal overlays missing role/aria (19 violations)

Every `fixed inset-0` modal overlay must have `role="dialog"`, `aria-modal="true"`, and `aria-label`. All 19 are missing all three attributes.

| File | Line | Modal ID | Missing |
|---|---|---|---|
| `agent_evals.html` | 572 | `commandlinesModal` | role, aria-modal, aria-label |
| `agent_evals2.html` | 445 | `itemDetailModal` | role, aria-modal, aria-label |
| `article_detail.html` | 9734 | `comparisonModal` | role, aria-modal, aria-label |
| `article_detail.html` | 9915 | `feedbackComparisonModal` | role, aria-modal, aria-label |
| `diags.html` | 301 | `loadingOverlay` | role, aria-modal, aria-label |
| `ml_hunt_comparison.html` | 470 | `rollbackConfirmModal` | role, aria-modal, aria-label |
| `settings.html` | 872 | `restoreBackupModal` | role, aria-modal, aria-label |
| `sources.html` | 479 | `resultModal` | role, aria-modal, aria-label |
| `sources.html` | 495 | `sourceConfigModal` | role, aria-modal, aria-label |
| `workflow.html` | 2876 | `configPresetListModal` | role, aria-modal, aria-label |
| `workflow.html` | 2899 | `configVersionListModal` | role, aria-modal, aria-label |
| `workflow.html` | 3129 | `executionModal` | role, aria-modal, aria-label |
| `workflow.html` | 3163 | `triggerWorkflowModal` | role, aria-modal, aria-label |
| `workflow.html` | 3307 | `ruleModal` | role, aria-modal, aria-label |
| `workflow.html` | 3345 | `enrichModal` | role, aria-modal, aria-label |
| `workflow.html` | 3709 | `promptHistoryModal` | role, aria-modal, aria-label |
| `workflow.html` | 3731 | `presetListModal` | role, aria-modal, aria-label |

**Note:** `sigma_evals.html` modal at line 443 *does* have `role="dialog"` set via JS (`setAttribute('role', 'dialog')`) — not a violation. The 19 above are genuinely missing.

### Toggle switches missing aria-label (2 violations)

| File | Line | Element |
|---|---|---|
| `workflow.html` | 2072 | `#cmdline-attention-preprocessor-enabled` checkbox |
| `workflow.html` | 2117 | `#proctree-attention-preprocessor-enabled` checkbox |

---

## Rule 9 — Spacing

Padding/margin > `p-6`/`mb-6` in config panels or `py-4+` on form controls:

| File | Line | Class | Context |
|---|---|---|---|
| `agent_evals.html` | 441 | `px-8` | Responsive page container (`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`) — **compliant, responsive breakpoint** |
| `agent_evals.html` | 1189 | `p-7` | Config panel wrapper |
| `agent_evals.html` | 2952 | `py-8` | Empty state placeholder |
| `agent_evals.html` | 3055 | `py-8` | Empty state placeholder |
| `agent_evals2.html` | 335 | `px-8` | Responsive page container — **compliant** |
| `agent_evals2.html` | 566 | `py-8` | Empty state placeholder |
| `article_detail.html` | 5992 | `py-8` | Empty state placeholder |
| `article_detail.html` | 7486 | `py-8` | Empty state placeholder |
| `articles.html` | 445 | `py-12` | Empty state placeholder |
| `base.html` | 239 | `px-8` | Responsive page container — **compliant** |
| `base.html` | 325 | `px-8` | Responsive page container — **compliant** |
| `diags.html` | 311 | `px-7` | Diagnostic panel inner wrapper |
| `error.html` | 7 | `p-8` | Error card centering wrapper |
| `jobs.html` | 293 | `py-8` | Empty state placeholder |
| `jobs.html` | 335 | `py-8` | Empty state placeholder |
| `mlops.html` | 320 | `mb-7` | Hero section bottom margin |
| `mlops.html` | 340 | `mb-7` | Stats section bottom margin |
| `pdf_upload.html` | 19 | `p-8` | Upload dropzone wrapper |
| `settings.html` | 544 | `pr-10` | Search input (icon spacing) |
| `settings.html` | 578 | `pr-10` | Search input (icon spacing) |
| `settings.html` | 635 | `pr-10` | Search input (icon spacing) |
| `settings.html` | 657 | `pr-10` | Search input (icon spacing) |
| `settings.html` | 773 | `pr-10` | Search input (icon spacing) |
| `sigma_ab_test.html` | 519 | `py-8` | Empty state placeholder |
| `sigma_evals.html` | 311 | `px-8` | Responsive page container — **compliant** |
| `sources.html` | 451 | `py-12` | Empty state placeholder |
| `workflow.html` | 1808 | `pb-8` | Container bottom padding |
| `workflow.html` | 6250 | `py-8` | Empty state placeholder |
| `workflow.html` | 16390 | `py-8` | Empty state placeholder |

**Classifying violations:**
- Responsive page containers (`lg:px-8`, `sm:px-6`) — **compliant, not violations** (5 instances)
- Empty-state placeholders with `py-8` / `py-12` — **acceptable for empty state per contract**
- `pr-10` on search inputs — **required for icon inside input**, not a config panel spacing issue
- **Genuine violations:** `agent_evals.html:1189` (`p-7`), `diags.html:311` (`px-7`), `mlops.html:320`/`:340` (`mb-7`), `workflow.html:1808` (`pb-8`)

**True violations: 5**

---

## Rule 10 — `!important`

233 occurrences found, all in `<style>` blocks — print stylesheets (`@media print`) and third-party widget overrides (Chart.js, etc.). These are compliant per the contract (Section 7.0.2: `@media print` and third-party widget overrides are permitted).

**Result: PASS.**

---

## Rule 11 — ASCII-Only

115 em-dashes (`—`) and 16 ellipses (`…`) found in visible text and JavaScript (excluding `<style>` blocks). Breakdown by file:

| File | Em-dash | Ellipsis | Total |
|---|---|---|---|
| `workflow.html` | 30+ | 3+ | 53 |
| `sources.html` | 8+ | 2+ | 12 |
| `ml_hunt_comparison.html` | 6+ | 1+ | 11 |
| `dashboard.html` | 5+ | 1+ | 9 |
| `diags.html` | 6+ | 1+ | 9 |
| `agent_evals.html` | 3+ | 1+ | 6 |
| `article_detail.html` | 2+ | 1+ | 4 |
| `settings.html` | 2+ | 1+ | 4 |
| Others (4 files) | ~3 | ~1 | 7 |

**Action required:** Replace `—` with ` -- ` (space-padded double-dash) and `…` with `...` (three periods) across all visible text and JS strings.

---

## Priority Remediation

1. **High — Rule 11 (ASCII):** `workflow.html` has 53 em-dashes/ellipses. Batch find-replace: `—` → ` -- ` and `…` → `...`
2. **High — Rule 8 (ARIA):** Add `role="dialog"`, `aria-modal="true"`, `aria-label` to all 19 modal overlays
3. **High — Rule 2 (Hardcoded colors):** `agent_evals.html` has 30 new `style=""` hex/rgba — refactor to CSS custom properties
4. **Medium — Rule 1 (Card stack):** 33 deprecated card occurrences — replace with `.card` token
5. **Medium — Rule 9 (Spacing):** 5 genuine padding violations — align to `p-6` / `mb-6` max
6. **Low — Rule 8 (Toggle ARIA):** 2 toggle switches missing `aria-label`
