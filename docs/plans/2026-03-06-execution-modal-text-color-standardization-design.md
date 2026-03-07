# Execution Detail Modal — Text Color Standardization Design

**Date:** 2026-03-06
**Scope:** Execution detail modal only (`#executionDetailContent`)
**Motivation:** Current gray palette bottoms out at `gray-400` (3.4:1 contrast ratio, below WCAG AA). Text is visibly dim, especially in the traceability section headers and inactive tab pills.

---

## Semantic Color System

Four levels on a `gray-800` modal background:

| Level | Tailwind class | Role | Contrast (on gray-800) |
|-------|---------------|------|------------------------|
| L1 | `text-white` | Headings — step names (h4), section titles | 16:1 ✅ |
| L2 | `text-gray-100` | Primary body — panel content, metrics, values, output text | 12:1 ✅ |
| L3 | `text-gray-200` | Secondary — summaries/toggles, header metadata rows, blockquotes | 9:1 ✅ |
| L4 | `text-gray-300` | Muted — "OUTPUT" label, inactive tab text, traceability footer metadata | 5.1:1 ✅ |

`text-gray-400` (3.4:1 ⚠️) is **eliminated entirely** from the modal.
Status/semantic colors (`green`, `red`, `amber`, `purple`) are **not changed**.

---

## Changes by Location

### 1. `headerHtml` (inside `viewExecution()`)
- Metadata rows (`Execution ID`, `Article`, `Status`, etc.): `text-gray-300` → `text-gray-200` (L3)
- Error message body span: `text-gray-300` → `text-gray-100` (L2)

### 2. Empty state fallback
- "No step data available…": `text-gray-400` → `text-gray-300` (L4)

### 3. `renderStepPanel()`
- Step title `<h4>`: `text-gray-100` → `text-white` (L1)
- Step metric (large mono): `text-gray-200` → `text-gray-100` (L2)
- Inputs `<summary>`: `text-gray-400 hover:text-gray-200` → `text-gray-300 hover:text-white` (L4→L1 on hover)
- Inputs content div: `text-gray-300` → `text-gray-100` (L2)
- Output `<summary>`: `text-gray-200` → `text-gray-100` (L2)
- Output content div: `text-gray-300` → `text-gray-100` (L2)

### 4. `renderExecutionTabbed()`
- Inactive tab: `text-gray-300 hover:text-gray-100` → `text-gray-200 hover:text-white` (L3→L1 on hover)
- Tab number span: `opacity-60` → `opacity-75`

### 5. `switchExecTab()` — mirrors `renderExecutionTabbed` inactive state
- Inactive: `text-gray-300 hover:border-gray-400 hover:text-gray-100` → `text-gray-200 hover:border-gray-300 hover:text-white`

### 6. `renderSubTabs()` + `switchExecSubTab()`
- Inactive subtab: `text-gray-400 hover:text-gray-200` → `text-gray-300 hover:text-white` (L4→L1 on hover)
- "OUTPUT" section label: `text-gray-400` → `text-gray-300` (L4)

### 7. `traceabilitySection()`
- "Observable Traceability" `<h4>`: `dark:text-gray-300` → `dark:text-gray-100` (L2)
- Unavailable fallback `<p>`: `dark:text-gray-400` → `dark:text-gray-300` (L4)
- Section `<summary>` headers (▼ Process Tree, ▼ Hunt Queries): `dark:text-gray-300` → `dark:text-gray-200` (L3)
- Blockquote source evidence: `dark:text-gray-300` → `dark:text-gray-200` (L3)
- Reasoning paragraph: `dark:text-gray-300` → `dark:text-gray-200` (L3)
- Footer metadata line (subagent, model, timestamp): `dark:text-gray-400` → `dark:text-gray-300` (L4)

---

## Summary

- **26 targeted class changes** across 7 locations
- **0 changes** to status colors, borders, backgrounds, or non-modal UI
- **0 new CSS rules** — all changes are inline Tailwind class swaps
- All levels WCAG AA compliant (minimum 5.1:1)
