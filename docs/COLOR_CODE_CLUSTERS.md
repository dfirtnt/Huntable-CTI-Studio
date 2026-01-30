# Color Code Clusters — Same or Roughly Same, Different Representations

Review of hex/rgb color codes across the codebase (src/, browser-extension/, tests/, docs/). Excludes generated site assets (minified CSS/JS).

---

## 1. Exact same color, different representation

These are identical colors; standardizing on one form (e.g. hex) will reduce drift and simplify theming.

| Canonical (use this) | Also found | Locations |
|----------------------|------------|-----------|
| `#ffffff` | `white`, `rgb(255, 255, 255)` | workflow.html (dark summary text), tests (verify_text_colors, workflow_executions), annotation-manager |
| `#f8fafc` | `rgb(248, 250, 252)` | workflow.html (headings, panel text); CSS uses hex, inline styles use both |
| `#cbd5e1` | `rgb(203, 213, 225)` | workflow.html (labels, secondary text, badges); same Tailwind slate-300 |
| `#fde047` | `rgb(253, 224, 71)` | workflow.html (yellow badge text); same Tailwind yellow-300 |
| `#374151` | `rgb(55 65 81)` / `rgb(55, 65, 81)` | workflow.html (summary color light mode), verify_text_colors.spec.ts |
| `#d1d5db` | `rgb(209 213 219)` | workflow.html (summary dark); Tailwind gray-300 |
| `#8b5cf6` | `rgba(139, 92, 246, α)` | workflow.html (borders, focus, hover); violet-500 |

**Recommendation:** Prefer hex (e.g. `#f8fafc`) in one place and reference via CSS variables or a small palette file so rgb() and hex don’t diverge.

---

## 2. One-digit / typo-level difference (likely unintentional)

Same semantic intent, different hex — easy to introduce bugs when copying.

| Color A | Color B | Note | Where |
|---------|---------|------|--------|
| `#cbd5e1` | `#cbd5e0` | Last digit 1 vs 0; very close, not identical | workflow/tests use `#cbd5e1`; **browser-extension/popup.html** uses `#cbd5e0` for `.btn-secondary:hover` |
| `#e5e7eb` | `#e2e8f0` | Gray-200 vs slate-200 | **src/web/static/js**: annotation-manager*.js use `#e5e7eb`; **browser-extension** uses `#e2e8f0` for borders |

**Recommendation:** Align on one: e.g. `#cbd5e1` and `#e5e7eb` (or your design system’s border/muted color) everywhere.

---

## 3. Same role, different shades (semantic duplicates)

Same use (e.g. “heading white”, “dark panel”, “yellow accent”) but different hex/rgb. Not wrong, but inconsistent.

### 3.1 “Bright heading / primary text” (dark theme)

| Value | Hex equivalent | Where |
|-------|----------------|--------|
| `#f8fafc` | — | workflow.html (h2, h3, h4, panel headers) |
| `rgb(248, 250, 252)` | `#f8fafc` | workflow.html CSS block (same as above) |
| `#ffffff` | — | workflow.html (View summaries, execution detail overrides) |

So “heading white” is sometimes `#f8fafc`, sometimes `#ffffff`. Both are correct; pick one for “primary text” and one for “emphasis” if desired.

### 3.2 Dark panel backgrounds (workflow dark theme)

All used for layered panels; similar but intentionally different levels. Good candidates for CSS variables (e.g. `--panel-bg-0` … `--panel-bg-4`).

| Value | Hex | Purpose (in workflow.html) |
|-------|-----|---------------------------|
| `#0a0e1a` | — | Input fields (Tailwind arbitrary) |
| `rgb(15, 20, 35)` | `#0f1423` | Root agents panel |
| `rgb(18, 24, 42)` | `#12182a` | Input/textarea background |
| `rgb(20, 28, 48)` | `#141c30` | Level 1 panels |
| `rgb(22, 30, 52)` | `#161e34` | Level 2 content |
| `rgb(26, 34, 56)` | `#1a2238` | Level 3 bordered |
| `rgb(30, 40, 65)` | `#1e2841` | Level 4 inner |
| `#1f2937` | — | .log-fullscreen dark (gray-800) |
| `#1d3067` | — | Collapsible panel header (inline style in JS) |

`#0a0e1a` is darker than the rgb sequence; the rest are a gradient from darkest to lighter. Consolidating into variables would keep the hierarchy and avoid typos.

### 3.3 Yellow / amber (step numbers, badges, stroke)

| Value | Tailwind | Where |
|-------|----------|--------|
| `#fde047` | yellow-300 | Workflow badge text, “3 Sub-Agents” |
| `#facc15` | yellow-400 | Workflow step “3” |
| `#eab308` | yellow-500 | Workflow overview bar |
| `#fbbf24` | amber-500 | workflow.html JS `node.style.stroke` |
| `rgb(253, 224, 71)` | = #fde047 | CSS yellow badge |
| `rgb(234, 179, 8)` | yellow-500 (different from #eab308) | rgba() yellow badge bg |

So “yellow” is split between yellow-300/400/500 and amber-500. Recommend one primary (e.g. `#eab308` or `#facc15`) for step numbers and one for stroke/accents.

### 3.4 Purple / violet (buttons, borders, focus)

| Value | Where |
|-------|--------|
| `#7C3AED` | Button hover (workflow); violet-600 |
| `#4b4e77` | Button default (workflow) |
| `#3d4063` | Button hover alt |
| `#1d3067` | Collapsible panel header bg |
| `rgba(139, 92, 246, *)` | Borders, focus, hover (violet-500) |
| docs/CHANGELOG: `#8B5CF6`, `#A78BFA`, `#C4B5FD` | Brand (violet-500, violet-400, violet-300) |

Functionally consistent (purple/violet theme); consider aligning with docs palette (e.g. `#8B5CF6` / `#7C3AED`) and reusing a single violet for hover if desired.

### 3.5 Green (success, huntable)

| Value | Where |
|-------|--------|
| `#16a34a`, `#15803d`, `#dcfce7` | annotation-manager*.js (huntable, success) |
| `rgb(34, 197, 94)`, `rgb(134, 239, 172)` | workflow.html (green badge); Tailwind green-500 / green-300 |

Two systems: annotation-manager uses green-600/700/100; workflow uses green-500/300. Pick one palette (e.g. Tailwind green-500/300) and reuse across both if you want one “success” look.

### 3.6 Gray text / borders (neutral UI)

| Value | Where |
|-------|--------|
| `#6b7280` | annotation-manager*.js (gray-500) |
| `#718096` | browser-extension (gray-600) |
| `#4a5568` | browser-extension (gray-600) |
| `#9ca3af` | annotation-manager (gray-400) |

All “muted text / secondary”; different grays. Standardizing on one gray scale (e.g. Tailwind) would make future theming easier.

---

## 4. Summary table — “same but not”

| Cluster | Canonical suggestion | Current variants |
|---------|----------------------|-------------------|
| White | `#ffffff` | #ffffff, white, rgb(255,255,255) |
| Slate heading | `#f8fafc` | #f8fafc, rgb(248,250,252) |
| Slate muted | `#cbd5e1` | #cbd5e1, #cbd5e0, rgb(203,213,225) |
| Yellow accent | `#eab308` or `#facc15` | #fde047, #facc15, #eab308, #fbbf24, rgb(253,224,71), rgb(234,179,8) |
| Purple primary | `#7C3AED` or `#8B5CF6` | #7C3AED, #4b4e77, #3d4063, #1d3067, rgba(139,92,246) |
| Dark panel set | CSS vars | #0a0e1a, #0f1423, #12182a, #141c30, #161e34, #1a2238, #1e2841, #1f2937, #1d3067 |
| Green success | `#16a34a` or Tailwind green-500 | #16a34a, #15803d, #dcfce7, rgb(34,197,94), rgb(134,239,172) |
| Border gray | `#e5e7eb` | #e5e7eb, #e2e8f0 |

---

## 5. Files with the most color definitions (source only)

| File | Notes |
|------|--------|
| `src/web/templates/workflow.html` | Bulk of hex + rgb; dark theme and inline styles |
| `src/web/static/js/annotation-manager.js` | Hex for menu, buttons, states |
| `src/web/static/js/annotation-manager-mobile.js` | Mirrors annotation-manager colors |
| `browser-extension/popup.html` | Own palette (#cbd5e0, #e2e8f0, #667eea, #764ba2, etc.) |
| `browser-extension/icons/icon16.svg` | #667eea, #764ba2, #4a5568 |
| `docs/CHANGELOG.md` | #1a1a2e, #8B5CF6, #A78BFA, #C4B5FD (brand) |
| `tests/playwright/verify_text_colors.spec.ts` | Asserts rgb() and #ffffff |
| `tests/playwright/workflow_executions.spec.ts` | Asserts #ffffff |

---

## 6. Colors to account for in specs

Playwright specs (`verify_text_colors.spec.ts`, `workflow_executions.spec.ts`) currently:

- **Valid “readable” for View summaries:** white (`rgb(255,255,255)` / `#ffffff` / `white`), gray-300 (`rgb(209,213,219)`), gray-700 (`rgb(55,65,81)`).
- **Excluded from “very dark = unreadable” (status/decoration):** red `rgb(239,68,68)`, green `rgb(34,197,94)`, yellow `rgb(234,179,8)`, blue `rgb(59,130,246)`, purple `rgb(168,85,247)`.

These colors exist in the app but are **not** yet in the specs; add them so assertions stay correct and avoid false “unreadable” reports.

### 6.1 Add to “valid readable” (View summaries / general text)

So headings and muted text in execution detail are accepted as readable.

| Color | Hex | Where used |
|-------|-----|------------|
| Slate heading | `#f8fafc`, `rgb(248, 250, 252)` | Panel h2/h3/h4, “Workflow Overview”, section titles |
| Slate muted | `#cbd5e1`, `rgb(203, 213, 225)` | Labels, “OS Detection”, “Junk Filter”, badge secondary |
| Body text (dark) | `#111827`, `rgb(17, 24, 39)` | Execution detail body (intentional; without this, spec flags it as “very dark” unreadable) |

### 6.2 Add to “status / decoration” allowlist (isStatusColor)

So step numbers, badges, and status text in execution detail are not treated as unreadable.

| Role | rgb() | Hex | Where used |
|------|--------|-----|------------|
| Green (badge text) | `rgb(134, 239, 172)` | `#86efac` | Workflow green badge text |
| Yellow (badge text) | `rgb(253, 224, 71)` | `#fde047` | Workflow yellow badge, “3 Sub-Agents” |
| Cyan (step) | `rgb(34, 211, 238)` | `#22d3ee` | Overview step “0” (OS Detection) |
| Blue (step) | `rgb(96, 165, 250)` | `#60a5fa` | Overview step “1” (Junk Filter) |
| Green (step) | `rgb(74, 222, 128)` | `#4ade80` | Overview step “2” (LLM Ranking) |
| Yellow (step) | `rgb(250, 204, 21)` | `#facc15` | Overview step “3” |
| Orange (step) | `rgb(251, 146, 60)` | `#fb923c` | Overview step “4” |
| Pink (step) | `rgb(244, 114, 182)` | `#f472b6` | Overview step “5” |
| Violet (step) | `rgb(192, 132, 252)` | `#c084fc` | Overview step “6” |
| Yellow (small) | `rgb(253, 224, 71)` | `#fde047` | “3 Sub-Agents” label |

Specs already have one green, one yellow, one blue, one purple; the table above adds the **alternate** shades used in workflow overview and badges (e.g. `rgb(134,239,172)`, `rgb(253,224,71)`, `rgb(96,165,250)`, `rgb(192,132,252)`, cyan/orange/pink).

### 6.3 Optional: other UI surfaces

Not required for current “View summary + execution detail” checks; add if you add specs for those areas.

| Area | Colors |
|------|--------|
| Annotation menu (annotation-manager) | `#6b7280`, `#e5e7eb`, `#16a34a`, `#15803d`, `#dc2626`, `#fef2f2`, `#9ca3af`, `#f3f4f6`, `#2563eb` |
| Browser extension popup | `#f8fafc`, `#667eea`, `#764ba2`, `#e2e8f0`, `#1a202c`, `#4a5568`, `#718096`, `#cbd5e0`, `#c6f6d5`, `#22543d`, `#9ae6b4`, `#fed7d7`, `#742a2a`, `#feb2b2`, `#bee3f8`, `#2a4365`, `#90cdf4`, `#2d3748`, `#ffffff` |

---

## Post-implementation policy (color-system normalization)

After refactoring to theme-variables.css and CSS variables:

- **No new literal hex/rgb colors** in app templates or JS; new colors must be added as variables in `src/web/static/css/theme-variables.css`.
- **Browser extension** remains palette-aligned but **exempt** from var() enforcement unless explicitly refactored.

---

**Exit: PASS** — Report written; no code changes. Use this doc to normalize colors (CSS variables, single hex per semantic role) and fix the two one-digit differences in the extension and borders.
