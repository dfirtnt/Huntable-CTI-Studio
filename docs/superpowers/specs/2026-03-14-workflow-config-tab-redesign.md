# Workflow Config Tab Redesign — Operator Console

**Date:** 2026-03-14
**Scope:** `#tab-content-config` inside `workflow.html` only (tab nav unchanged)
**Status:** Approved

---

## Summary

Redesign the workflow config tab from a flat accordion of collapsible panels into an **Operator Console** — a two-panel layout with a vertical pipeline rail on the left and step-scoped config sections on the right.

The redesign addresses both aesthetics (generic Tailwind utility-class feel) and interaction model (no visual hierarchy expressing pipeline order, no sequential grouping).

---

## Design Direction

**Aesthetic:** Industrial operator console. `JetBrains Mono` for all values, identifiers, and step numbers. `DM Sans` for labels and buttons. Step accent colors from existing CSS variables (`--step-0` through `--step-6`). All colors reference `theme-variables.css` — **no new hex values**.

**Key differentiator:** The pipeline execution order (0 → 6) is the backbone of the UI. Every visual element reinforces the sequential nature of the system.

---

## Layout

### Left: Pipeline Rail (200px, fixed)
- Background: `--panel-bg-0` (darkest layer)
- 7 numbered nodes (0–6), each styled with its step color via rail color utility classes `.c0`–`.c6` (defined in the new CSS block; each sets `color: var(--step-N)`)
- Nodes connected by animated dashed vertical lines: `repeating-linear-gradient` on a `<div>` with `background-position` keyframe animation simulating downward data flow
- Active node: `box-shadow` pulse glow in step color
- Clicking a node: smooth-scrolls to the corresponding section and expands it if collapsed; updates active rail class
- Active node also updated via `IntersectionObserver` as user scrolls (see below)

### Right: Config Content Area (flex-fill, scrollable div `id="config-content"`)
- Each pipeline step is a `<section>` with `id="s0"` through `id="s6"`
- Each section has a CSS custom property `--sc` scoped at the section level: `#s0 { --sc: var(--step-0); }` etc., allowing all child elements (border beams, slider thumbs, focus rings, badge borders, slider values) to inherit the step accent color without per-step CSS repetition
- Left border beam: `3px solid var(--sc)`, widens to `4px` with `box-shadow: 0 0 8px var(--sc)` when section has `.open` class
- Background tint: `linear-gradient(90deg, var(--sc), transparent)` at `3%` opacity via `.section-tint` overlay div
- Section header: collapsible via `toggle(id)` JS function, shows `STEP N` badge + title + meta summary + chevron

### Bottom: Sticky Footer (fixed, `left: 200px; right: 0`)
- Always visible: config version + saved timestamp + action buttons
- Element IDs and onclick handlers (must match existing wiring):
  - **Reset**: `onclick="loadConfig()"` — existing function, reloads config from API
  - **Presets**: `onclick="showConfigPresetList()"` — opens `#configPresetListModal`
  - **Versions**: `onclick="showConfigVersionList()"` — opens `#configVersionListModal`
  - **Save Configuration**: `id="save-config-button"`, `type="submit"` on the wrapping `<form id="workflowConfigForm">`, `disabled` initially (enabled by `autoSaveConfig()`)
- The `#configPresetListModal` and `#configVersionListModal` divs remain outside the new layout (already in the DOM, unchanged)

---

## Step Sections — Content Structure

Pipeline order, section IDs, and section content:

| Step | ID | Name | Key content |
|------|----|------|-------------|
| 0 | `#s0` | OS Detection | Provider/model/temperature + prompt container |
| 1 | `#s1` | Junk Filter | Junk filter threshold slider |
| 2 | `#s2` | LLM Ranking | Provider/model/temperature + ranking threshold slider + prompt container + QA toggle → QA sub-panel |
| 3 | `#s3` | Extract Agent | Supervisor provider/model/temperature + supervisor prompt container + sub-agents accordion |
| 4 | `#s4` | Generate SIGMA | Provider/model/temperature + SIGMA content source toggle + prompt container + test button |
| 5 | `#s5` | Similarity Search | Similarity threshold slider |
| 6 | `#s6` | Queue | Read-only note: "No configurable parameters. Rules passing similarity check are automatically queued." |

**Note on SIGMA content source (Step 4):** The existing `id="sigma-fallback-enabled"` checkbox (`name="sigma_fallback_enabled"`, `onchange="autoSaveConfig()"`) currently lives in its own collapsible panel. In the redesign it moves into Step 4 as a toggle row.

**Note on Step 6:** The existing Queue step has no configurable parameters in the config form. Render a static note only. Do not drop any existing form fields — there are none for this step.

---

## Prompt Containers (per agent)

Each agent retains its existing prompt container div (`id="rank-agent-prompt-container"`, `id="os-detection-prompt-container"`, etc.). The existing `renderAgentPrompts()` function (defined at line ~6942) dynamically populates these containers when `loadConfig()` runs. **Do not change the container IDs or remove these divs** — the JS that fills them is unchanged.

The prompt panels rendered inside these containers use `saveAgentPrompt2(agentName)` (defined at line ~8623) for their Save buttons. This is the correct function for the dynamically rendered panels — not `saveAgentPrompt` (line ~4588, used elsewhere). Do not conflate the two.

The "📜 History" button in the dynamically rendered panels calls `showPromptHistory(agentName)` — this function dynamically creates and injects a modal element each time (it does not reference the static `#promptHistoryModal` div at line ~2202, which is a separate legacy element).

---

## Collapsible Behavior

The **new step sections and sub-agent accordion** use a CSS-class-based model: a `toggle(id)` JS function adds/removes the `.open` class, which CSS uses to show/hide `.section-body` via `display: none / block`.

The **existing `initCollapsiblePanels()`** function operates on elements with `data-collapsible-panel` attributes. The dynamically rendered prompt panels (injected by `renderAgentPrompts()`) still use `data-collapsible-panel` — `initCollapsiblePanels()` is called by `renderAgentPrompts()` after injecting them and must not be removed. The two systems do not conflict: they operate on different DOM subtrees.

**Do not add `data-collapsible-panel` attributes to the new step sections or sub-agent accordion items** — those use `toggle()` directly.

---

## Test Buttons

Each test button calls the following functions (existing, unchanged):

| Section | Button label | `onclick` |
|---------|-------------|-----------|
| Step 2 (LLM Ranking) | ⚡ Test Rank Agent | `const id = promptForArticleId(2155); if (id) testRankAgent(id);` |
| Step 3 CmdlineExtract | ⚡ Test CmdlineExtract | `const id = promptForArticleId(2155); if (id) testSubAgent('CmdlineExtract', id);` |
| Step 3 ProcTreeExtract | ⚡ Test ProcTreeExtract | `const id = promptForArticleId(2155); if (id) testSubAgent('ProcTreeExtract', id);` |
| Step 3 HuntQueriesExtract | ⚡ Test HuntQueriesExtract | `const id = promptForArticleId(2155); if (id) testSubAgent('HuntQueriesExtract', id);` |
| Step 4 (SIGMA) | ⚡ Test SIGMA Agent | `const id = promptForArticleId(2155); if (id) testSigmaAgent(id);` |

---

## QA Sub-Panel

For agents that support QA (Step 2: RankAgent; each sub-agent in Step 3):

- A toggle row wires to the existing `onchange` handler for `id="qa-{agentPrefix}"` checkbox (e.g. `id="qa-rankagent"`, `name="qa_enabled[RankAgent]"`)
- When enabled, a QA sub-panel appears with:
  - Provider/model selectors (existing element IDs: `id="{prefix}-provider"`, `id="{prefix}-model"`, etc.)
  - The existing QA prompt container div (`id="rank-agent-qa-prompt-container"`, `id="{prefix}-agent-qa-prompt-container"`)
- All existing `onchange` attributes on provider/model selectors are preserved as-is

---

## Sub-Agent Accordion (Step 3)

Agents in execution order: CmdlineExtract → ProcTreeExtract → HuntQueriesExtract → RegistryExtract.

Each sub-agent row is collapsible via `toggleSA(id)`. Body contains:
- Provider/model/temperature selectors (existing element IDs preserved)
- Enable/disable toggle wired to existing `data-derived-persist-key` on the disabled_agents config
- Prompt container div (existing `id`, e.g. `id="cmdlineextract-agent-prompt-container"`)
- QA toggle + QA prompt container
- Save Preset / Load Preset buttons (`onclick="saveSubAgentPreset('cmdline')"` / `onclick="showConfigPresetListForScope('cmdline')"`) — preserved from existing UI
- Test button (see table above)

---

## IntersectionObserver for Active Rail Node

```js
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const idx = entry.target.dataset.stepIndex;
      document.querySelectorAll('.rail-item').forEach((el, i) => {
        el.classList.toggle('active', String(i) === idx);
      });
    }
  });
}, {
  root: document.getElementById('config-content'), // the scrollable div
  rootMargin: '-10% 0px -85% 0px',
  threshold: 0
});
document.querySelectorAll('.step-section').forEach((el, i) => {
  el.dataset.stepIndex = i;
  observer.observe(el);
});
```

Each step section gets `data-step-index="{n}"`. The observer fires when a section enters the top 15% of the scrollable viewport.

---

## Typography

| Use | Font | Size | Weight |
|-----|------|------|--------|
| Section titles | DM Sans | 13.5px | 600 |
| Form labels | DM Sans | 10px uppercase | 600 |
| Step badge text | JetBrains Mono | 9px | 700 |
| Model/provider values in selects | JetBrains Mono | 11.5px | 400 |
| Slider values | JetBrains Mono | 12px | 700 |
| Rail step names | DM Sans | 11.5px | 500 |
| Rail sub-labels | JetBrains Mono | 9px | 400 |
| Prompt textarea | JetBrains Mono | 10.5px | 400 |

---

## CSS Architecture

- Step accent colors scoped via `#s0 { --sc: var(--step-0); }` through `#s6 { --sc: var(--step-6); }`
- Rail color utilities: `.c0 { color: var(--step-0); }` through `.c6 { color: var(--step-6); }`
- **No new hex values** — all colors reference `theme-variables.css` variables
- Prompt panel system/user border colors: `var(--step-1)` (blue) for System Prompt, `var(--step-2)` (green) for User Prompt — these map to `#60a5fa` and `#4ade80` respectively in the theme file
- All new styles go in a `<style>` block at the top of the config tab content, or as a scoped addition to the existing per-page `<style>` block in `workflow.html`
- Animation: connector lines use CSS-only `repeating-linear-gradient` + `background-position` keyframe — no JS

---

## Font Loading

In `src/web/templates/base.html`, **append** to the existing Google Fonts `<link>` tag (do not create a second link; do not remove Inter):

Add `JetBrains+Mono:wght@400;600;700` and `DM+Sans:wght@400;500;600;700` to the existing font families parameter. Ensure a `<link rel="preconnect" href="https://fonts.googleapis.com">` and `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>` are present before the font `<link>`.

---

## Files to Modify

1. **`src/web/templates/workflow.html`** — replace the inner HTML of `#tab-content-config` with the new layout. All existing form element IDs, `name` attributes, `onchange` handlers, and `data-*` attributes on inputs/selects/checkboxes are preserved exactly. Modals (`#configPresetListModal`, `#configVersionListModal`, `#promptHistoryModal`) remain outside the new layout, unchanged.
2. **`src/web/templates/base.html`** — update Google Fonts link to include JetBrains Mono and DM Sans.
3. **`src/web/static/css/theme-variables.css`** — no changes needed.

---

## Implementation Notes (Non-blocking)

- **Step 3 supervisor containers:** Include `id="extract-agent-model-container"` for the supervisor model and `id="extract-agent-prompt-container"` for the supervisor prompt. Both exist in the current DOM and must survive the redesign.
- **Step 3 supervisor QA prompt:** Include `id="extract-agent-qa-prompt-container"` in the Step 3 QA sub-panel. This is the supervisor-level QA prompt container (distinct from sub-agent QA containers at `id="cmdlineextract-agent-qa-prompt-container"` etc.). If omitted, `renderAgentPrompts()` silently fails to inject supervisor QA prompts.
- **QA toggle `onchange` strings must be copied exactly from existing elements** — do not re-derive. E.g. `id="qa-rankagent"` onchange is `"updateRankQAEnabledBadge(); updateQABadge('rank-agent'); autoSaveConfig();"`.
- **Sub-agent enable/disable** is handled by `handleExtractAgentToggle(agentName)` called from checkbox `onchange`, not by writing `data-derived-persist-key` directly.

---

## Out of Scope

- Tab navigation bar (`⚙️ Configuration | 🔄 Executions | 📥 SIGMA Queue`) — unchanged
- Page header — unchanged
- Executions tab, Queue tab — unchanged
- All JavaScript business logic — existing functions preserved, only DOM structure changes
- `workflow_config.html` (standalone config page) — unchanged
