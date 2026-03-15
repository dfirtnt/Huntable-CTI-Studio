# Workflow Config Tab Redesign — Operator Console Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat accordion config tab with a two-panel Operator Console — vertical pipeline rail (left) + step-scoped config sections (right) + sticky footer.

**Architecture:** Left rail (200px fixed) shows 7 animated pipeline nodes (0–6). Right side is a scrollable form with 7 step sections (`#s0`–`#s6`), each scoped to a step accent color via `--sc` CSS custom property. Sticky footer holds Save/Reset/Presets buttons.

**Tech Stack:** Jinja2, Vanilla JS, Tailwind CSS, Google Fonts (JetBrains Mono, DM Sans), CSS custom properties from `theme-variables.css`

---

## Chunk 1: Fonts and CSS Foundation

### Task 1: Add JetBrains Mono and DM Sans to base.html

**Files:**
- Modify: `src/web/templates/base.html:9`

- [ ] **Step 1: Read current font line**

```bash
grep -n "fonts.googleapis" src/web/templates/base.html | head -5
```

- [ ] **Step 2: Replace line 9 with preconnect tags + updated font link**

Current line 9:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
```

Replace with (these 3 lines replace the 1 existing line):
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 3: Verify font line is correct**

```bash
grep -n "JetBrains\|DM+Sans\|preconnect" src/web/templates/base.html
```

Expected: 3 lines showing preconnect + updated href.

- [ ] **Step 4: Commit**

```bash
git add src/web/templates/base.html
git commit -m "feat(ui): add JetBrains Mono and DM Sans to Google Fonts link"
```

---

### Task 2: Append Operator Console CSS to workflow.html

**Files:**
- Modify: `src/web/templates/workflow.html` (existing `<style>` block, before its closing `</style>` tag)

The `<style>` block starts around line 6 and ends around line 390. Append the following CSS block just before the closing `</style>`.

- [ ] **Step 1: Find the closing tag of the style block**

```bash
grep -n "^</style>" src/web/templates/workflow.html | head -3
```

- [ ] **Step 2: Append Operator Console CSS before `</style>`**

Insert the following CSS block immediately before the closing `</style>` tag of the existing style block:

```css
/* ═══════════════════════════════════════════════════
   OPERATOR CONSOLE — Config Tab Layout
   ═══════════════════════════════════════════════════ */

/* ─── Layout Shell ─────────────────────────────────── */
.oc-shell {
  display: flex;
  height: calc(100vh - 148px);
  min-height: 580px;
  background: var(--panel-bg-0);
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.07);
}

.oc-rail {
  width: 200px;
  flex-shrink: 0;
  background: var(--panel-bg-0);
  border-right: 1px solid rgba(255,255,255,0.07);
  padding: 20px 0 20px;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}

.oc-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel-bg-1);
}

#config-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 12px;
  scroll-behavior: smooth;
}

.oc-footer {
  flex-shrink: 0;
  border-top: 1px solid rgba(255,255,255,0.07);
  background: var(--panel-bg-0);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

/* ─── Rail Items ────────────────────────────────────── */
.rail-connector {
  width: 2px;
  height: 20px;
  margin: 0 auto;
  background: repeating-linear-gradient(
    to bottom,
    rgba(255,255,255,0.18) 0px,
    rgba(255,255,255,0.18) 4px,
    transparent 4px,
    transparent 9px
  );
  background-size: 2px 9px;
  animation: oc-rail-flow 1.4s linear infinite;
}

@keyframes oc-rail-flow {
  from { background-position: 0 0; }
  to   { background-position: 0 9px; }
}

.rail-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
  transition: background 0.15s;
  border-radius: 7px;
  margin: 0 6px;
  text-decoration: none;
}
.rail-item:hover { background: rgba(255,255,255,0.05); }
.rail-item.active { background: rgba(255,255,255,0.07); }

.rail-node {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 2px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  transition: box-shadow 0.25s;
  background: var(--panel-bg-1);
  flex-shrink: 0;
}
.rail-item.active .rail-node {
  box-shadow: 0 0 12px currentColor, 0 0 4px currentColor;
}

.rail-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--text-secondary);
  text-align: center;
  margin-top: 4px;
  line-height: 1.25;
}
.rail-item.active .rail-label { color: var(--text-primary); }

.rail-sublabel {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: rgba(255,255,255,0.3);
  text-align: center;
  margin-top: 1px;
}

/* Step color utilities */
.c0 { color: var(--step-0); }
.c1 { color: var(--step-1); }
.c2 { color: var(--step-2); }
.c3 { color: var(--step-3); }
.c4 { color: var(--step-4); }
.c5 { color: var(--step-5); }
.c6 { color: var(--step-6); }

/* ─── Step Sections ─────────────────────────────────── */
/* Scope --sc to section's accent color */
#s0 { --sc: var(--step-0); }
#s1 { --sc: var(--step-1); }
#s2 { --sc: var(--step-2); }
#s3 { --sc: var(--step-3); }
#s4 { --sc: var(--step-4); }
#s5 { --sc: var(--step-5); }
#s6 { --sc: var(--step-6); }

.step-section {
  position: relative;
  border-left: 3px solid var(--sc);
  border-radius: 0 8px 8px 0;
  background: var(--panel-bg-1);
  margin-bottom: 10px;
  overflow: hidden;
  transition: border-left-width 0.15s, box-shadow 0.2s;
}
.step-section.open {
  border-left-width: 4px;
  box-shadow: -3px 0 10px var(--sc);
}

.section-tint {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, var(--sc), transparent);
  opacity: 0.035;
  pointer-events: none;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  cursor: pointer;
  user-select: none;
  position: relative;
  z-index: 1;
}
.section-header:hover { background: rgba(255,255,255,0.02); }

.step-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  color: var(--sc);
  border: 1px solid var(--sc);
  border-radius: 3px;
  padding: 1px 5px;
  white-space: nowrap;
  flex-shrink: 0;
  opacity: 0.9;
}

.section-title {
  font-family: 'DM Sans', sans-serif;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.section-meta {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: rgba(255,255,255,0.35);
  margin-left: auto;
  white-space: nowrap;
}

.section-chevron {
  font-size: 10px;
  color: var(--text-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}
.step-section.open .section-chevron { transform: rotate(180deg); }

.section-body {
  display: none;
  padding: 0 16px 16px;
  border-top: 1px solid rgba(255,255,255,0.06);
  position: relative;
  z-index: 1;
}
.step-section.open .section-body { display: block; }

/* ─── Form Field Typography ─────────────────────────── */
.oc-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.055em;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 4px;
}

.oc-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--sc, var(--text-primary));
}

/* Slider value displays use step accent color */
.step-section .threshold-slider .text-purple-400 {
  color: var(--sc) !important;
}

/* ─── Sub-Agent Accordion ───────────────────────────── */
.sa-item {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px;
  margin-bottom: 8px;
  overflow: hidden;
}

.sa-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 13px;
  cursor: pointer;
  background: rgba(255,255,255,0.02);
  user-select: none;
}
.sa-header:hover { background: rgba(255,255,255,0.04); }
.sa-item.open > .sa-header { background: rgba(255,255,255,0.05); }

.sa-title {
  font-family: 'DM Sans', sans-serif;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.sa-body {
  display: none;
  padding: 12px 13px;
  border-top: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.01);
}
.sa-item.open .sa-body { display: block; }
.sa-item.open .sa-chevron { transform: rotate(180deg); }
.sa-chevron { transition: transform 0.2s; font-size: 10px; color: var(--text-secondary); }

/* ─── Footer label + version display ───────────────── */
.oc-footer-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  color: rgba(255,255,255,0.35);
}
```

- [ ] **Step 3: Verify CSS was appended before closing style tag**

```bash
grep -c "oc-shell\|oc-rail\|step-section\|sa-item" src/web/templates/workflow.html
```

Expected: multiple matches (at least 4 distinct classes found).

- [ ] **Step 4: Commit**

```bash
git add src/web/templates/workflow.html
git commit -m "feat(ui): add Operator Console CSS to workflow.html style block"
```

---

## Chunk 2: Config Tab HTML Replacement

### Task 3: Replace config tab inner content (lines 407–1471)

**Files:**
- Modify: `src/web/templates/workflow.html:407-1471`

This task replaces the entire `<div class="agents-panel ...">` block (lines 407–1471) inside `#tab-content-config` with the new Operator Console two-panel layout. All existing form element IDs, `name` attributes, `onchange`/`oninput` handlers, and prompt container divs are preserved exactly. The modals at lines 1473+ are NOT touched.

**Critical IDs that must survive (do not remove or rename):**
- `workflowConfigForm` — the form itself
- `os-detection-model-container`, `os-detection-prompt-container`
- `rank-agent-model-container`, `rank-agent-prompt-container`
- `rank-agent-qa-prompt-container`, `rank-qa-agent-prompt-content`
- `rank-agent-qa-configs`
- `extract-agent-model-container`, `extract-agent-prompt-container`, `extract-agent-qa-prompt-container`
- `sigma-agent-model-container`, `sigma-agent-prompt-container`
- `cmdlineextract-agent-prompt-container`, `cmdlineextract-agent-qa-configs`, `cmdlineextract-agent-qa-prompt-container`
- `proctreeextract-agent-prompt-container`, `proctreeextract-agent-qa-configs`, `proctreeextract-agent-qa-prompt-container`
- `huntqueriesextract-agent-prompt-container`, `huntqueriesextract-agent-qa-configs`, `huntqueriesextract-agent-qa-prompt-container`
- All badge span IDs: `rank-agent-enabled-pill`, `rank-agent-qa-badge`, `rank-agent-enabled-badge`, `rank-qa-agent-enabled-badge`
- All sub-agent badge IDs: `cmdlineextract-agent-enabled-pill`, `cmdlineextract-agent-qa-badge`, `cmdlineextract-agent-enabled-badge`, and same pattern for `proctreeextract` and `huntqueriesextract`

- [ ] **Step 1: Read lines 407–1471 to confirm current structure before replacement**

Read `src/web/templates/workflow.html` lines 407–420 (confirm outer wrapper) and 1467–1472 (confirm end of form + div).

- [ ] **Step 2: Write a Python replacement script**

Create `scripts/replace_config_tab.py`:

```python
#!/usr/bin/env python3
"""Replace config tab inner content in workflow.html."""
import re, sys

with open('src/web/templates/workflow.html', 'r') as f:
    content = f.read()

# Find the section to replace: from agents-panel opening div to its closing div
# This is lines 407-1471: the `<div class="agents-panel ...">` block
START_MARKER = '        <div class="agents-panel rounded-lg shadow-lg p-6 mb-8">'
END_MARKER = '        </div>\n\n        <!-- Config Preset List Modal -->'

start_idx = content.find(START_MARKER)
end_idx = content.find(END_MARKER)

if start_idx == -1 or end_idx == -1:
    print(f"ERROR: markers not found. start={start_idx}, end={end_idx}")
    sys.exit(1)

# end_idx should point to the end of the agents-panel div
# We want to replace START_MARKER...(up to but not including END_MARKER)
old_section = content[start_idx:end_idx]
print(f"Replacing {len(old_section)} chars ({old_section.count(chr(10))} lines)")

NEW_HTML = """REPLACE_ME"""

new_content = content[:start_idx] + NEW_HTML + content[end_idx:]
with open('src/web/templates/workflow.html', 'w') as f:
    f.write(new_content)
print("Done.")
```

> **Note:** Do NOT run this script yet — first complete Step 3 which writes the actual NEW_HTML content.

- [ ] **Step 3: Write the full replacement HTML**

The `NEW_HTML` string in the script should be replaced with the following complete HTML block. This replaces `REPLACE_ME` in the script above:

```html
<!-- Operator Console: two-panel config layout -->
        <form id="workflowConfigForm" novalidate>
        <div class="oc-shell">

          <!-- ── Left: Pipeline Rail ──────────────────── -->
          <nav class="oc-rail" aria-label="Pipeline steps">
            <div style="padding: 0 12px 8px; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: rgba(255,255,255,0.3);">PIPELINE</div>

            <div class="rail-item c0 active" onclick="scrollToStep(0)" role="button" tabindex="0">
              <div class="rail-node">0</div>
              <div class="rail-label">OS Detection</div>
              <div class="rail-sublabel">os-detect</div>
            </div>
            <div class="rail-connector"></div>

            <div class="rail-item c1" onclick="scrollToStep(1)" role="button" tabindex="0">
              <div class="rail-node">1</div>
              <div class="rail-label">Junk Filter</div>
              <div class="rail-sublabel">threshold</div>
            </div>
            <div class="rail-connector"></div>

            <div class="rail-item c2" onclick="scrollToStep(2)" role="button" tabindex="0">
              <div class="rail-node">2</div>
              <div class="rail-label">LLM Ranking</div>
              <div class="rail-sublabel">rank-agent</div>
            </div>
            <div class="rail-connector"></div>

            <div class="rail-item c3" onclick="scrollToStep(3)" role="button" tabindex="0">
              <div class="rail-node">3</div>
              <div class="rail-label">Extract Agent</div>
              <div class="rail-sublabel">supervisor</div>
            </div>
            <div class="rail-connector"></div>

            <div class="rail-item c4" onclick="scrollToStep(4)" role="button" tabindex="0">
              <div class="rail-node">4</div>
              <div class="rail-label">Generate SIGMA</div>
              <div class="rail-sublabel">sigma-agent</div>
            </div>
            <div class="rail-connector"></div>

            <div class="rail-item c5" onclick="scrollToStep(5)" role="button" tabindex="0">
              <div class="rail-node">5</div>
              <div class="rail-label">Similarity Search</div>
              <div class="rail-sublabel">dedup</div>
            </div>
            <div class="rail-connector"></div>

            <div class="rail-item c6" onclick="scrollToStep(6)" role="button" tabindex="0">
              <div class="rail-node">6</div>
              <div class="rail-label">Queue</div>
              <div class="rail-sublabel">terminal</div>
            </div>
          </nav>

          <!-- ── Right: Content + Footer ──────────────── -->
          <div class="oc-right">
            <div id="config-content">

              <!-- ══ STEP 0: OS DETECTION ══════════════════ -->
              <section id="s0" class="step-section open">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s0')">
                  <span class="step-badge">STEP 0</span>
                  <span class="section-title">OS Detection</span>
                  <span class="section-meta">model · prompt</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3">
                    <div id="os-detection-model-container"></div>
                    <div id="os-detection-prompt-container" class="mt-3"></div>
                  </div>
                </div>
              </section>

              <!-- ══ STEP 1: JUNK FILTER ════════════════════ -->
              <section id="s1" class="step-section">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s1')">
                  <span class="step-badge">STEP 1</span>
                  <span class="section-title">Junk Filter</span>
                  <span class="section-meta">threshold</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3">
                    <div class="threshold-slider">
                      <div class="flex justify-between items-center mb-1">
                        <label for="junkFilterThreshold" class="flex items-center gap-2 text-sm font-semibold" style="color: var(--text-primary) !important;">
                          Junk filter threshold
                          <button type="button" onclick="showHelp('junkFilterThreshold')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
                          </button>
                        </label>
                        <span id="junkFilterThreshold-value" class="oc-value">0.8</span>
                      </div>
                      <input type="range" id="junkFilterThreshold" name="junk_filter_threshold" min="0" max="1" step="0.05" value="0.8" required class="threshold-slider-input w-full" oninput="updateThresholdDisplay('junkFilterThreshold'); validateThreshold(this, 0, 1); autoSaveConfig()">
                      <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1"><span>0.0</span><span>1.0</span></div>
                      <p class="text-xs text-gray-500 dark:text-gray-300 mt-1">Min confidence for content filtering — higher = more aggressive</p>
                      <p id="junkFilterThreshold-error" class="text-xs text-red-500 dark:text-red-400 mt-1 hidden"></p>
                    </div>
                  </div>
                </div>
              </section>

              <!-- ══ STEP 2: LLM RANKING ════════════════════ -->
              <section id="s2" class="step-section">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s2')">
                  <span class="step-badge">STEP 2</span>
                  <span class="section-title">LLM Ranking</span>
                  <span id="rank-agent-enabled-pill" class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Enabled</span>
                  <span id="rank-agent-qa-badge" class="px-2 py-0.5 text-xs rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300">QA: OFF</span>
                  <span class="section-meta">rank-agent · threshold · qa</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3 space-y-4">

                    <!-- Enable/Disable -->
                    <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700" style="background: var(--panel-bg-5) !important;">
                      <div class="flex items-center justify-between">
                        <div>
                          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Rank Agent Enabled</label>
                          <p class="text-xs text-gray-500 dark:text-gray-400">If disabled, ranking is skipped and workflow proceeds directly to extraction.</p>
                        </div>
                        <div class="flex items-center gap-2">
                          <span id="rank-agent-enabled-badge" class="px-2 py-1 text-[11px] rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Enabled</span>
                          <label class="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" id="rank-agent-enabled" name="rank_agent_enabled" aria-label="Rank Agent Enabled" class="sr-only peer" onchange="updateRankEnabledBadge(); updateRankQAState(false); autoSaveConfig();">
                            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                          </label>
                        </div>
                      </div>
                    </div>

                    <!-- Model -->
                    <div>
                      <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Rank Agent Model</h4>
                      <div id="rank-agent-model-container"></div>
                    </div>

                    <!-- Test Button -->
                    <div>
                      <button type="button" onclick="const id = promptForArticleId(2155); if (id) testRankAgent(id);" class="w-full px-4 py-2 btn-workflow text-white text-sm font-medium rounded-md transition-colors">
                        ⚡ Test Rank Agent
                      </button>
                    </div>

                    <!-- Ranking Threshold -->
                    <div class="threshold-slider">
                      <div class="flex justify-between items-center mb-1">
                        <label for="rankingThreshold" class="flex items-center gap-2 text-sm font-semibold" style="color: var(--text-primary) !important;">
                          Ranking threshold
                          <button type="button" onclick="showHelp('rankingThreshold')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
                          </button>
                        </label>
                        <span id="rankingThreshold-value" class="oc-value">6</span>
                      </div>
                      <input type="range" id="rankingThreshold" name="ranking_threshold" min="0" max="10" step="0.1" value="6" required class="threshold-slider-input w-full" oninput="updateThresholdDisplay('rankingThreshold'); validateThreshold(this, 0, 10); autoSaveConfig()">
                      <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1"><span>0</span><span>10</span></div>
                      <p class="text-xs text-gray-500 dark:text-gray-300 mt-1">Minimum LLM score to continue workflow — articles below this are dropped</p>
                      <p id="rankingThreshold-error" class="text-xs text-red-500 dark:text-red-400 mt-1 hidden"></p>
                    </div>

                    <!-- Rank Agent Prompt -->
                    <div>
                      <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Rank Agent Prompts</h4>
                      <div id="rank-agent-prompt-container"></div>
                    </div>

                    <!-- QA Toggle -->
                    <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700" style="background: var(--panel-bg-5) !important;">
                      <div class="flex items-center justify-between">
                        <div>
                          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Rank QA Agent</label>
                          <p class="text-xs text-gray-500 dark:text-gray-400">Enable QA validation using the configured QA retry limit</p>
                        </div>
                        <div class="flex items-center gap-2">
                          <span id="rank-qa-agent-enabled-badge" class="px-2 py-1 text-[11px] rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300">Disabled</span>
                          <label class="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" id="qa-rankagent" name="qa_enabled[RankAgent]" class="sr-only peer" onchange="updateRankQAEnabledBadge(); updateQABadge('rank-agent'); autoSaveConfig();">
                            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                          </label>
                        </div>
                      </div>
                    </div>

                    <!-- RankQA sub-panel (shown when QA enabled) -->
                    <div id="rank-agent-qa-configs" class="hidden bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 space-y-3" style="background: var(--panel-bg-5) !important;">
                      <label class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                        Rank QA Model Provider
                        <button type="button" onclick="showHelp('rankAgentQA')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help">
                          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
                        </button>
                      </label>
                      <select id="rankqa-provider" name="agent_models[RankAgentQA_provider]" onchange="onAgentProviderChange('rankqa')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-3 py-2 text-gray-50 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-sm">
                        <option value="lmstudio">LMStudio (Local)</option>
                        <option value="openai">OpenAI (Cloud)</option>
                        <option value="anthropic">Anthropic Claude (Cloud)</option>
                      </select>
                      <div data-agent-prefix="rankqa" data-provider="lmstudio">
                        <select id="rankqa-model" name="agent_models[RankAgentQA]" onchange="validateAgentModelOnChange('rankqa'); autoSaveModelChange()" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-3 py-2 text-gray-50 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 font-mono text-sm"></select>
                      </div>
                      <div data-agent-prefix="rankqa" data-provider="openai" class="hidden">
                        <input type="text" id="rankqa-model-openai" name="agent_models[RankAgentQA]" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-3 py-2 text-gray-50 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 font-mono text-sm" placeholder="gpt-4o-mini" onchange="validateAgentModelOnChange('rankqa'); autoSaveModelChange()" oninput="validateAgentModelOnChange('rankqa'); autoSaveModelChange()">
                      </div>
                      <div data-agent-prefix="rankqa" data-provider="anthropic" class="hidden">
                        <input type="text" id="rankqa-model-anthropic" name="agent_models[RankAgentQA]" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-3 py-2 text-gray-50 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 font-mono text-sm" placeholder="claude-sonnet-4-5" onchange="validateAgentModelOnChange('rankqa'); autoSaveModelChange()" oninput="validateAgentModelOnChange('rankqa'); autoSaveModelChange()">
                      </div>
                      <div class="mt-3 flex gap-3">
                        <div class="flex-1 threshold-slider">
                          <div class="flex justify-between items-center mb-1">
                            <label for="rankqa-temperature" class="block text-sm font-semibold" style="color: var(--text-primary) !important;">Temperature</label>
                            <span id="rankqa-temperature-value" class="text-purple-400 font-medium">0.1</span>
                          </div>
                          <input type="range" id="rankqa-temperature" name="agent_models[RankAgentQA_temperature]" min="0" max="2" step="0.1" value="0.1" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('rankqa-temperature'); autoSaveModelChange()">
                          <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1"><span>0</span><span>2</span></div>
                        </div>
                        <div class="flex-1 threshold-slider">
                          <div class="flex justify-between items-center mb-1">
                            <label for="rankqa-top-p" class="block text-sm font-semibold" style="color: var(--text-primary) !important;">Top_P</label>
                            <span id="rankqa-top-p-value" class="text-purple-400 font-medium">0.9</span>
                          </div>
                          <input type="range" id="rankqa-top-p" name="agent_models[RankAgentQA_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('rankqa-top-p'); autoSaveModelChange()">
                          <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1"><span>0.0</span><span>1.0</span></div>
                        </div>
                      </div>
                    </div>

                    <!-- Rank QA Prompt container -->
                    <div id="rank-agent-qa-prompt-container" class="hidden">
                      <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Rank QA Agent Prompts</h4>
                      <div id="rank-qa-agent-prompt-content"></div>
                    </div>

                    <!-- Global QA Settings (max retries) -->
                    <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700" style="background: var(--panel-bg-5) !important;">
                      <label for="qaMaxRetries" class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        QA Max Retries
                        <button type="button" onclick="showHelp('qaMaxRetries')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help">
                          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
                        </button>
                      </label>
                      <input type="number" id="qaMaxRetries" name="qa_max_retries" min="1" max="3" step="1" oninput="validateThreshold(this, 1, 3); autoSaveConfig()" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-3 py-2 text-gray-50 placeholder-gray-500 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500">
                      <p class="text-xs text-gray-500 dark:text-gray-300 mt-1">Maximum feedback cycles from any QA agent (1–3)</p>
                      <p id="qaMaxRetries-error" class="text-xs text-red-500 dark:text-red-400 mt-1 hidden"></p>
                    </div>

                  </div>
                </div>
              </section>

              <!-- ══ STEP 3: EXTRACT AGENT ═══════════════════ -->
              <section id="s3" class="step-section">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s3')">
                  <span class="step-badge">STEP 3</span>
                  <span class="section-title">Extract Agent</span>
                  <span class="px-2 py-0.5 text-xs rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 font-medium">Supervisor</span>
                  <span class="section-meta">supervisor · sub-agents</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3 space-y-4">

                    <!-- Supervisor Model -->
                    <div>
                      <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Supervisor Model (Fallback)</h4>
                      <div id="extract-agent-model-container"></div>
                    </div>

                    <!-- Supervisor Prompt -->
                    <div>
                      <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">Extract Agent Prompt</h4>
                      <div id="extract-agent-prompt-container"></div>
                    </div>

                    <!-- Supervisor QA Prompt -->
                    <div id="extract-agent-qa-prompt-container" class="hidden"></div>

                    <!-- Sub-Agents accordion -->
                    <div class="pt-4 border-t border-yellow-700/40">
                      <h4 class="text-xs font-semibold mb-3" style="color: var(--text-secondary) !important;">SUB-AGENTS — Execution Order</h4>

                      <!-- CmdlineExtract -->
                      <div id="sa-cmdline" class="sa-item">
                        <div class="sa-header" onclick="toggleSA('sa-cmdline')">
                          <span class="sa-title">CmdlineExtract</span>
                          <span class="text-xs text-gray-500 dark:text-gray-400">Command Line Extraction</span>
                          <span id="cmdlineextract-agent-enabled-pill" class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 ml-auto">Enabled</span>
                          <span id="cmdlineextract-agent-qa-badge" class="px-2 py-0.5 text-xs rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300 ml-1">QA: OFF</span>
                          <span class="sa-chevron ml-2">▼</span>
                        </div>
                        <div class="sa-body space-y-3">
                          <!-- Enable/Disable -->
                          <div class="flex items-center justify-between">
                            <div>
                              <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">Enable CmdlineExtract</label>
                              <p class="text-[10px] text-gray-500 dark:text-gray-400">Toggle off to skip (outputs 0 observables)</p>
                            </div>
                            <div class="flex items-center gap-2">
                              <span id="cmdlineextract-agent-enabled-badge" class="px-2 py-1 text-[11px] rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Enabled</span>
                              <label class="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" id="toggle-cmdlineextract-enabled" name="extract_subagent_enabled[CmdlineExtract]" aria-label="Enable CmdlineExtract" class="sr-only peer" onchange="handleExtractAgentToggle('CmdlineExtract')">
                                <div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                              </label>
                            </div>
                          </div>
                          <!-- Model -->
                          <div class="space-y-2">
                            <label class="flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300">
                              Model Provider
                              <button type="button" onclick="showHelp('cmdlineExtract')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg></button>
                            </label>
                            <select id="cmdlineextract-provider" name="agent_models[CmdlineExtract_provider]" onchange="onAgentProviderChange('cmdlineextract')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-50 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-xs">
                              <option value="lmstudio">LMStudio (Local)</option>
                              <option value="openai">OpenAI (Cloud)</option>
                              <option value="anthropic">Anthropic Claude (Cloud)</option>
                            </select>
                            <div data-agent-prefix="cmdlineextract" data-provider="lmstudio">
                              <select id="cmdlineextract-model" name="agent_models[CmdlineExtract_model]" onchange="validateAgentModelOnChange('cmdlineextract'); autoSaveModelChange()" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"><option value="">Use Extract Agents Fallback Model</option></select>
                            </div>
                            <div data-agent-prefix="cmdlineextract" data-provider="openai" class="hidden">
                              <input type="text" id="cmdlineextract-model-openai" name="agent_models[CmdlineExtract_model]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="gpt-4o-mini" onchange="validateAgentModelOnChange('cmdlineextract'); autoSaveModelChange()" oninput="validateAgentModelOnChange('cmdlineextract'); autoSaveModelChange()">
                            </div>
                            <div data-agent-prefix="cmdlineextract" data-provider="anthropic" class="hidden">
                              <input type="text" id="cmdlineextract-model-anthropic" name="agent_models[CmdlineExtract_model]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="claude-sonnet-4-5" onchange="validateAgentModelOnChange('cmdlineextract'); autoSaveModelChange()" oninput="validateAgentModelOnChange('cmdlineextract'); autoSaveModelChange()">
                            </div>
                          </div>
                          <!-- Temperature + Top_P -->
                          <div class="flex gap-3">
                            <div class="flex-1 threshold-slider">
                              <div class="flex justify-between items-center mb-1"><label for="cmdlineextract-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label><span id="cmdlineextract-temperature-value" class="text-purple-400 font-medium text-xs">0</span></div>
                              <input type="range" id="cmdlineextract-temperature" name="agent_models[CmdlineExtract_temperature]" min="0" max="2" step="0.1" value="0.0" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('cmdlineextract-temperature'); autoSaveModelChange()">
                              <div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0</span><span>2</span></div>
                            </div>
                            <div class="flex-1 threshold-slider">
                              <div class="flex justify-between items-center mb-1"><label for="cmdlineextract-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label><span id="cmdlineextract-top-p-value" class="text-purple-400 font-medium text-xs">0.9</span></div>
                              <input type="range" id="cmdlineextract-top-p" name="agent_models[CmdlineExtract_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('cmdlineextract-top-p'); autoSaveModelChange()">
                              <div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0.0</span><span>1.0</span></div>
                            </div>
                          </div>
                          <!-- Prompt container -->
                          <div id="cmdlineextract-agent-prompt-container"></div>
                          <!-- Attention Preprocessor -->
                          <div class="flex items-center justify-between">
                            <div>
                              <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">Attention Preprocessor</label>
                              <p class="text-[10px] text-gray-500 dark:text-gray-400">Surface high-likelihood command snippets before full article (LOLBAS anchors)</p>
                            </div>
                            <label class="relative inline-flex items-center cursor-pointer">
                              <input type="checkbox" id="cmdline-attention-preprocessor-enabled" name="cmdline_attention_preprocessor_enabled" class="sr-only peer" onchange="autoSaveConfig();">
                              <div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                            </label>
                          </div>
                          <!-- QA Toggle -->
                          <div class="flex items-center justify-between">
                            <div>
                              <label class="block text-xs font-medium text-gray-700 dark:text-gray-300">CmdlineExtract QA Agent</label>
                              <p class="text-[10px] text-gray-500 dark:text-gray-400">Enable QA validation</p>
                            </div>
                            <label class="relative inline-flex items-center cursor-pointer">
                              <input type="checkbox" id="qa-cmdlineextract" name="qa_enabled[CmdlineExtract]" class="sr-only peer" onchange="updateQABadge('cmdlineextract-agent'); autoSaveConfig();">
                              <div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600 peer-disabled:opacity-50 peer-disabled:cursor-not-allowed"></div>
                            </label>
                          </div>
                          <!-- CmdlineQA sub-panel -->
                          <div id="cmdlineextract-agent-qa-configs" class="hidden space-y-2">
                            <label class="flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-gray-300">CmdLine QA Model Provider
                              <button type="button" onclick="showHelp('cmdlineQA')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg></button>
                            </label>
                            <select id="cmdlineqa-provider" name="agent_models[CmdLineQA_provider]" onchange="onAgentProviderChange('cmdlineqa')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-50 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-xs">
                              <option value="lmstudio">LMStudio (Local)</option><option value="openai">OpenAI (Cloud)</option><option value="anthropic">Anthropic Claude (Cloud)</option>
                            </select>
                            <div data-agent-prefix="cmdlineqa" data-provider="lmstudio"><select id="cmdlineqa-model" name="agent_models[CmdLineQA]" onchange="autoSaveModelChange()" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"></select></div>
                            <div data-agent-prefix="cmdlineqa" data-provider="openai" class="hidden"><input type="text" id="cmdlineqa-model-openai" name="agent_models[CmdLineQA]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="gpt-4o-mini" onchange="autoSaveModelChange()"></div>
                            <div data-agent-prefix="cmdlineqa" data-provider="anthropic" class="hidden"><input type="text" id="cmdlineqa-model-anthropic" name="agent_models[CmdLineQA]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="claude-sonnet-4-5" onchange="autoSaveModelChange()"></div>
                            <div class="mt-2 flex gap-3">
                              <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="cmdlineqa-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label><span id="cmdlineqa-temperature-value" class="text-purple-400 font-medium text-xs">0.1</span></div><input type="range" id="cmdlineqa-temperature" name="agent_models[CmdLineQA_temperature]" min="0" max="2" step="0.1" value="0.1" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('cmdlineqa-temperature'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0</span><span>2</span></div></div>
                              <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="cmdlineqa-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label><span id="cmdlineqa-top-p-value" class="text-purple-400 font-medium text-xs">0.9</span></div><input type="range" id="cmdlineqa-top-p" name="agent_models[CmdLineQA_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('cmdlineqa-top-p'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0.0</span><span>1.0</span></div></div>
                            </div>
                          </div>
                          <div id="cmdlineextract-agent-qa-prompt-container" class="hidden"></div>
                          <!-- Test + Preset buttons -->
                          <div class="flex gap-2 pt-1">
                            <button type="button" onclick="const id = promptForArticleId(2155); if (id) testSubAgent('CmdlineExtract', id);" class="flex-1 px-3 py-2 btn-workflow text-white text-xs font-medium rounded-md transition-colors">⚡ Test CmdlineExtract</button>
                            <button type="button" onclick="saveSubAgentPreset('cmdline')" class="flex-1 px-3 py-2 text-xs font-medium rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-white">Save Preset</button>
                            <button type="button" onclick="showConfigPresetListForScope('cmdline')" class="flex-1 px-3 py-2 text-xs font-medium rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-white">Load Preset</button>
                          </div>
                        </div>
                      </div>

                      <!-- ProcTreeExtract -->
                      <div id="sa-proctree" class="sa-item">
                        <div class="sa-header" onclick="toggleSA('sa-proctree')">
                          <span class="sa-title">ProcTreeExtract</span>
                          <span class="text-xs text-gray-500 dark:text-gray-400">Process Lineage</span>
                          <span id="proctreeextract-agent-enabled-pill" class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 ml-auto">Enabled</span>
                          <span id="proctreeextract-agent-qa-badge" class="px-2 py-0.5 text-xs rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300 ml-1">QA: OFF</span>
                          <span class="sa-chevron ml-2">▼</span>
                        </div>
                        <div class="sa-body space-y-3">
                          <!-- Enable/Disable -->
                          <div class="flex items-center justify-between">
                            <div><label class="block text-xs font-medium text-gray-700 dark:text-gray-300">Enable ProcTreeExtract</label><p class="text-[10px] text-gray-500 dark:text-gray-400">Toggle off to skip</p></div>
                            <div class="flex items-center gap-2">
                              <span id="proctreeextract-agent-enabled-badge" class="px-2 py-1 text-[11px] rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Enabled</span>
                              <label class="relative inline-flex items-center cursor-pointer"><input type="checkbox" id="toggle-proctreeextract-enabled" name="extract_subagent_enabled[ProcTreeExtract]" aria-label="Enable ProcTreeExtract" class="sr-only peer" onchange="handleExtractAgentToggle('ProcTreeExtract')"><div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div></label>
                            </div>
                          </div>
                          <!-- Model -->
                          <div class="space-y-2">
                            <label class="text-xs font-medium text-gray-700 dark:text-gray-300">Model Provider</label>
                            <select id="proctreeextract-provider" name="agent_models[ProcTreeExtract_provider]" onchange="onAgentProviderChange('proctreeextract')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-50 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-xs"><option value="lmstudio">LMStudio (Local)</option><option value="openai">OpenAI (Cloud)</option><option value="anthropic">Anthropic Claude (Cloud)</option></select>
                            <div data-agent-prefix="proctreeextract" data-provider="lmstudio"><select id="proctreeextract-model" name="agent_models[ProcTreeExtract_model]" onchange="validateAgentModelOnChange('proctreeextract'); autoSaveModelChange()" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"><option value="">Use Extract Agents Fallback Model</option></select></div>
                            <div data-agent-prefix="proctreeextract" data-provider="openai" class="hidden"><input type="text" id="proctreeextract-model-openai" name="agent_models[ProcTreeExtract_model]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="gpt-4o-mini" onchange="validateAgentModelOnChange('proctreeextract'); autoSaveModelChange()" oninput="validateAgentModelOnChange('proctreeextract'); autoSaveModelChange()"></div>
                            <div data-agent-prefix="proctreeextract" data-provider="anthropic" class="hidden"><input type="text" id="proctreeextract-model-anthropic" name="agent_models[ProcTreeExtract_model]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="claude-sonnet-4-5" onchange="validateAgentModelOnChange('proctreeextract'); autoSaveModelChange()" oninput="validateAgentModelOnChange('proctreeextract'); autoSaveModelChange()"></div>
                          </div>
                          <!-- Temperature + Top_P -->
                          <div class="flex gap-3">
                            <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="proctreeextract-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label><span id="proctreeextract-temperature-value" class="text-purple-400 font-medium text-xs">0</span></div><input type="range" id="proctreeextract-temperature" name="agent_models[ProcTreeExtract_temperature]" min="0" max="2" step="0.1" value="0.0" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('proctreeextract-temperature'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0</span><span>2</span></div></div>
                            <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="proctreeextract-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label><span id="proctreeextract-top-p-value" class="text-purple-400 font-medium text-xs">0.9</span></div><input type="range" id="proctreeextract-top-p" name="agent_models[ProcTreeExtract_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('proctreeextract-top-p'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0.0</span><span>1.0</span></div></div>
                          </div>
                          <!-- Prompt container -->
                          <div id="proctreeextract-agent-prompt-container"></div>
                          <!-- QA Toggle -->
                          <div class="flex items-center justify-between">
                            <div><label class="block text-xs font-medium text-gray-700 dark:text-gray-300">ProcTreeExtract QA Agent</label><p class="text-[10px] text-gray-500 dark:text-gray-400">Enable QA validation</p></div>
                            <label class="relative inline-flex items-center cursor-pointer"><input type="checkbox" id="qa-proctreeextract" name="qa_enabled[ProcTreeExtract]" class="sr-only peer" onchange="updateQABadge('proctreeextract-agent'); autoSaveConfig();"><div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600 peer-disabled:opacity-50"></div></label>
                          </div>
                          <!-- ProcTreeQA sub-panel -->
                          <div id="proctreeextract-agent-qa-configs" class="hidden space-y-2">
                            <label class="text-xs font-medium text-gray-700 dark:text-gray-300">ProcTree QA Model Provider</label>
                            <select id="proctreeqa-provider" name="agent_models[ProcTreeQA_provider]" onchange="onAgentProviderChange('proctreeqa')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-50 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-xs"><option value="lmstudio">LMStudio (Local)</option><option value="openai">OpenAI (Cloud)</option><option value="anthropic">Anthropic Claude (Cloud)</option></select>
                            <div data-agent-prefix="proctreeqa" data-provider="lmstudio"><select id="proctreeqa-model" name="agent_models[ProcTreeQA]" onchange="autoSaveModelChange()" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"></select></div>
                            <div data-agent-prefix="proctreeqa" data-provider="openai" class="hidden"><input type="text" id="proctreeqa-model-openai" name="agent_models[ProcTreeQA]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="gpt-4o-mini" onchange="autoSaveModelChange()"></div>
                            <div data-agent-prefix="proctreeqa" data-provider="anthropic" class="hidden"><input type="text" id="proctreeqa-model-anthropic" name="agent_models[ProcTreeQA]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="claude-sonnet-4-5" onchange="autoSaveModelChange()"></div>
                            <div class="mt-2 flex gap-3">
                              <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="proctreeqa-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label><span id="proctreeqa-temperature-value" class="text-purple-400 font-medium text-xs">0.1</span></div><input type="range" id="proctreeqa-temperature" name="agent_models[ProcTreeQA_temperature]" min="0" max="2" step="0.1" value="0.1" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('proctreeqa-temperature'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0</span><span>2</span></div></div>
                              <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="proctreeqa-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label><span id="proctreeqa-top-p-value" class="text-purple-400 font-medium text-xs">0.9</span></div><input type="range" id="proctreeqa-top-p" name="agent_models[ProcTreeQA_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('proctreeqa-top-p'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0.0</span><span>1.0</span></div></div>
                            </div>
                          </div>
                          <div id="proctreeextract-agent-qa-prompt-container" class="hidden"></div>
                          <!-- Test + Preset buttons -->
                          <div class="flex gap-2 pt-1">
                            <button type="button" onclick="const id = promptForArticleId(2155); if (id) testSubAgent('ProcTreeExtract', id);" class="flex-1 px-3 py-2 btn-workflow text-white text-xs font-medium rounded-md transition-colors">⚡ Test ProcTreeExtract</button>
                            <button type="button" onclick="saveSubAgentPreset('proctree')" class="flex-1 px-3 py-2 text-xs font-medium rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-white">Save Preset</button>
                            <button type="button" onclick="showConfigPresetListForScope('proctree')" class="flex-1 px-3 py-2 text-xs font-medium rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-white">Load Preset</button>
                          </div>
                        </div>
                      </div>

                      <!-- HuntQueriesExtract -->
                      <div id="sa-huntqueries" class="sa-item">
                        <div class="sa-header" onclick="toggleSA('sa-huntqueries')">
                          <span class="sa-title">HuntQueriesExtract</span>
                          <span class="text-xs text-gray-500 dark:text-gray-400">Hunt Queries</span>
                          <span id="huntqueriesextract-agent-enabled-pill" class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 ml-auto">Enabled</span>
                          <span id="huntqueriesextract-agent-qa-badge" class="px-2 py-0.5 text-xs rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300 ml-1">QA: OFF</span>
                          <span class="sa-chevron ml-2">▼</span>
                        </div>
                        <div class="sa-body space-y-3">
                          <!-- Enable/Disable -->
                          <div class="flex items-center justify-between">
                            <div><label class="block text-xs font-medium text-gray-700 dark:text-gray-300">Enable HuntQueriesExtract</label><p class="text-[10px] text-gray-500 dark:text-gray-400">Toggle off to skip</p></div>
                            <div class="flex items-center gap-2">
                              <span id="huntqueriesextract-agent-enabled-badge" class="px-2 py-1 text-[11px] rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Enabled</span>
                              <label class="relative inline-flex items-center cursor-pointer"><input type="checkbox" id="toggle-huntqueriesextract-enabled" name="extract_subagent_enabled[HuntQueriesExtract]" aria-label="Enable HuntQueriesExtract" class="sr-only peer" onchange="handleExtractAgentToggle('HuntQueriesExtract')"><div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div></label>
                            </div>
                          </div>
                          <!-- Model -->
                          <div class="space-y-2">
                            <label class="text-xs font-medium text-gray-700 dark:text-gray-300">Model Provider</label>
                            <select id="huntqueriesextract-provider" name="agent_models[HuntQueriesExtract_provider]" onchange="onAgentProviderChange('huntqueriesextract')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-50 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-xs"><option value="lmstudio">LMStudio (Local)</option><option value="openai">OpenAI (Cloud)</option><option value="anthropic">Anthropic Claude (Cloud)</option></select>
                            <div data-agent-prefix="huntqueriesextract" data-provider="lmstudio"><select id="huntqueriesextract-model" name="agent_models[HuntQueriesExtract_model]" onchange="validateAgentModelOnChange('huntqueriesextract'); autoSaveModelChange()" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"><option value="">Use Extract Agents Fallback Model</option></select></div>
                            <div data-agent-prefix="huntqueriesextract" data-provider="openai" class="hidden"><input type="text" id="huntqueriesextract-model-openai" name="agent_models[HuntQueriesExtract_model]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="gpt-4o-mini" onchange="validateAgentModelOnChange('huntqueriesextract'); autoSaveModelChange()" oninput="validateAgentModelOnChange('huntqueriesextract'); autoSaveModelChange()"></div>
                            <div data-agent-prefix="huntqueriesextract" data-provider="anthropic" class="hidden"><input type="text" id="huntqueriesextract-model-anthropic" name="agent_models[HuntQueriesExtract_model]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="claude-sonnet-4-5" onchange="validateAgentModelOnChange('huntqueriesextract'); autoSaveModelChange()" oninput="validateAgentModelOnChange('huntqueriesextract'); autoSaveModelChange()"></div>
                          </div>
                          <!-- Temperature + Top_P -->
                          <div class="flex gap-3">
                            <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="huntqueriesextract-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label><span id="huntqueriesextract-temperature-value" class="text-purple-400 font-medium text-xs">0</span></div><input type="range" id="huntqueriesextract-temperature" name="agent_models[HuntQueriesExtract_temperature]" min="0" max="2" step="0.1" value="0.0" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('huntqueriesextract-temperature'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0</span><span>2</span></div></div>
                            <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="huntqueriesextract-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label><span id="huntqueriesextract-top-p-value" class="text-purple-400 font-medium text-xs">0.9</span></div><input type="range" id="huntqueriesextract-top-p" name="agent_models[HuntQueriesExtract_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('huntqueriesextract-top-p'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0.0</span><span>1.0</span></div></div>
                          </div>
                          <!-- Prompt container -->
                          <div id="huntqueriesextract-agent-prompt-container"></div>
                          <!-- QA Toggle -->
                          <div class="flex items-center justify-between">
                            <div><label class="block text-xs font-medium text-gray-700 dark:text-gray-300">HuntQueriesExtract QA Agent</label><p class="text-[10px] text-gray-500 dark:text-gray-400">Enable QA validation</p></div>
                            <label class="relative inline-flex items-center cursor-pointer"><input type="checkbox" id="qa-huntqueriesextract" name="qa_enabled[HuntQueriesExtract]" class="sr-only peer" onchange="updateQABadge('huntqueriesextract-agent'); autoSaveConfig();"><div class="w-10 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600 peer-disabled:opacity-50"></div></label>
                          </div>
                          <!-- HuntQueriesQA sub-panel -->
                          <div id="huntqueriesextract-agent-qa-configs" class="hidden space-y-2">
                            <label class="text-xs font-medium text-gray-700 dark:text-gray-300">HuntQueries QA Model Provider</label>
                            <select id="huntqueriesqa-provider" name="agent_models[HuntQueriesQA_provider]" onchange="onAgentProviderChange('huntqueriesqa')" class="w-full bg-panel-0 border border-gray-700 rounded-lg px-2 py-1.5 text-gray-50 focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 text-xs"><option value="lmstudio">LMStudio (Local)</option><option value="openai">OpenAI (Cloud)</option><option value="anthropic">Anthropic Claude (Cloud)</option></select>
                            <div data-agent-prefix="huntqueriesqa" data-provider="lmstudio"><select id="huntqueriesqa-model" name="agent_models[HuntQueriesQA]" onchange="autoSaveModelChange()" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"></select></div>
                            <div data-agent-prefix="huntqueriesqa" data-provider="openai" class="hidden"><input type="text" id="huntqueriesqa-model-openai" name="agent_models[HuntQueriesQA]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="gpt-4o-mini" onchange="autoSaveModelChange()"></div>
                            <div data-agent-prefix="huntqueriesqa" data-provider="anthropic" class="hidden"><input type="text" id="huntqueriesqa-model-anthropic" name="agent_models[HuntQueriesQA]" class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs" placeholder="claude-sonnet-4-5" onchange="autoSaveModelChange()"></div>
                            <div class="mt-2 flex gap-3">
                              <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="huntqueriesqa-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label><span id="huntqueriesqa-temperature-value" class="text-purple-400 font-medium text-xs">0.1</span></div><input type="range" id="huntqueriesqa-temperature" name="agent_models[HuntQueriesQA_temperature]" min="0" max="2" step="0.1" value="0.1" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('huntqueriesqa-temperature'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0</span><span>2</span></div></div>
                              <div class="flex-1 threshold-slider"><div class="flex justify-between items-center mb-1"><label for="huntqueriesqa-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label><span id="huntqueriesqa-top-p-value" class="text-purple-400 font-medium text-xs">0.9</span></div><input type="range" id="huntqueriesqa-top-p" name="agent_models[HuntQueriesQA_top_p]" min="0" max="1" step="0.01" value="0.9" class="threshold-slider-input w-full" oninput="updateThresholdDisplay('huntqueriesqa-top-p'); autoSaveModelChange()"><div class="flex justify-between text-[10px] text-gray-500 mt-1"><span>0.0</span><span>1.0</span></div></div>
                            </div>
                          </div>
                          <div id="huntqueriesextract-agent-qa-prompt-container" class="hidden"></div>
                          <!-- Test + Preset buttons -->
                          <div class="flex gap-2 pt-1">
                            <button type="button" onclick="const id = promptForArticleId(2155); if (id) testSubAgent('HuntQueriesExtract', id);" class="flex-1 px-3 py-2 btn-workflow text-white text-xs font-medium rounded-md transition-colors">⚡ Test HuntQueriesExtract</button>
                            <button type="button" onclick="saveSubAgentPreset('huntqueries')" class="flex-1 px-3 py-2 text-xs font-medium rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-white">Save Preset</button>
                            <button type="button" onclick="showConfigPresetListForScope('huntqueries')" class="flex-1 px-3 py-2 text-xs font-medium rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-white">Load Preset</button>
                          </div>
                        </div>
                      </div>

                    </div><!-- end sub-agents accordion -->
                  </div>
                </div>
              </section>

              <!-- ══ STEP 4: GENERATE SIGMA ══════════════════ -->
              <section id="s4" class="step-section">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s4')">
                  <span class="step-badge">STEP 4</span>
                  <span class="section-title">Generate SIGMA</span>
                  <span class="section-meta">sigma-agent · content-source</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3 space-y-4">
                    <!-- Model -->
                    <div>
                      <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">SIGMA Agent Model</h4>
                      <div id="sigma-agent-model-container"></div>
                    </div>
                    <!-- Use Full Article Content -->
                    <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700" style="background: var(--panel-bg-5) !important;">
                      <div class="flex items-center justify-between">
                        <div>
                          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Use Full Article Content (Minus Junk)</label>
                          <p class="text-xs text-gray-500 dark:text-gray-400">If enabled, SIGMA uses junk-filtered article content instead of extracted observables summary.</p>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer">
                          <input type="checkbox" id="sigma-fallback-enabled" name="sigma_fallback_enabled" aria-label="Use Full Article Content (Minus Junk)" class="sr-only peer" onchange="autoSaveConfig();">
                          <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                        </label>
                      </div>
                    </div>
                    <!-- Test button -->
                    <div>
                      <div class="flex items-start gap-2 mb-2 text-xs text-gray-600 dark:text-gray-300">
                        <svg class="w-4 h-4 mt-0.5 text-gray-500 dark:text-gray-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
                        <p class="leading-snug">Test requests run directly on article content. In live workflow, SIGMA ingests observables from Extract Agents (unless full content enabled above).</p>
                      </div>
                      <button type="button" onclick="const id = promptForArticleId(2155); if (id) testSigmaAgent(id);" class="w-full px-4 py-2 btn-workflow text-white text-sm font-medium rounded-md transition-colors">
                        ⚡ Test SIGMA Agent
                      </button>
                    </div>
                    <!-- Prompt -->
                    <div id="sigma-agent-prompt-container"></div>
                  </div>
                </div>
              </section>

              <!-- ══ STEP 5: SIMILARITY SEARCH ══════════════ -->
              <section id="s5" class="step-section">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s5')">
                  <span class="step-badge">STEP 5</span>
                  <span class="section-title">Similarity Search</span>
                  <span class="section-meta">dedup threshold</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3">
                    <div class="threshold-slider">
                      <div class="flex justify-between items-center mb-1">
                        <label for="similarityThreshold" class="flex items-center gap-2 text-sm font-semibold" style="color: var(--text-primary) !important;">
                          Similarity threshold
                          <button type="button" onclick="showHelp('similarityThreshold')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none" title="Help">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
                          </button>
                        </label>
                        <span id="similarityThreshold-value" class="oc-value">0.5</span>
                      </div>
                      <input type="range" id="similarityThreshold" name="similarity_threshold" min="0" max="1" step="0.05" value="0.5" required class="threshold-slider-input w-full" oninput="updateThresholdDisplay('similarityThreshold'); validateThreshold(this, 0, 1); autoSaveConfig()">
                      <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1"><span>0.0</span><span>1.0</span></div>
                      <p class="text-xs text-gray-500 dark:text-gray-300 mt-1">Max similarity to queue a rule — rules above this are considered duplicates</p>
                      <p id="similarityThreshold-error" class="text-xs text-red-500 dark:text-red-400 mt-1 hidden"></p>
                    </div>
                  </div>
                </div>
              </section>

              <!-- ══ STEP 6: QUEUE (terminal) ════════════════ -->
              <section id="s6" class="step-section">
                <div class="section-tint"></div>
                <div class="section-header" onclick="toggle('s6')">
                  <span class="step-badge">STEP 6</span>
                  <span class="section-title">Queue</span>
                  <span class="section-meta">terminal</span>
                  <span class="section-chevron">▼</span>
                </div>
                <div class="section-body">
                  <div class="mt-3">
                    <p class="text-sm text-gray-500 dark:text-gray-400" style="font-family: 'JetBrains Mono', monospace; font-size: 11px;">
                      No configurable parameters. Rules passing the similarity check are automatically queued for review.
                    </p>
                  </div>
                </div>
              </section>

              <!-- ── Config Display ────────────────────────── -->
              {% include 'components/workflow_config_snippet.html' %}

            </div><!-- end #config-content -->

            <!-- ── Sticky Footer ─────────────────────────── -->
            <div class="oc-footer">
              <div class="flex items-center gap-3">
                <button type="button" onclick="showGenerateCommandsModal()" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-md transition-colors font-medium">
                  🔧 LMStudio Commands
                </button>
                <button type="button" onclick="saveConfigPreset()" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-md transition-colors font-medium">💾 Save Preset</button>
                <button type="button" onclick="showConfigPresetList()" class="px-3 py-1.5 btn-workflow text-white text-xs rounded-md transition-colors font-medium">📂 Load Preset</button>
                <button type="button" onclick="showConfigVersionList()" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-md transition-colors font-medium">🔄 Versions</button>
                <button type="button" onclick="exportPresetToFile()" class="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white text-xs rounded-md transition-colors font-medium">📤 Export</button>
                <label for="import-preset-input" class="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 text-white text-xs rounded-md transition-colors font-medium cursor-pointer">📥 Import</label>
                <input type="file" id="import-preset-input" accept=".json" class="hidden" onchange="importPresetFromFile(event)">
              </div>
              <div class="flex items-center gap-3">
                <button type="button" onclick="loadConfig()" class="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-xs">
                  Reset
                </button>
                <button type="submit" id="save-config-button" class="px-5 py-1.5 bg-purple-600 hover:bg-purple-700 text-white rounded-md transition-colors font-medium text-xs disabled:opacity-50 disabled:cursor-not-allowed" disabled>
                  Save Configuration
                </button>
              </div>
            </div><!-- end oc-footer -->

          </div><!-- end oc-right -->
        </div><!-- end oc-shell -->

        <script>
        // ── Operator Console: toggle functions + rail nav + IntersectionObserver ──

        function toggle(id) {
          const el = document.getElementById(id);
          if (el) el.classList.toggle('open');
        }

        function toggleSA(id) {
          const el = document.getElementById(id);
          if (el) el.classList.toggle('open');
        }

        function scrollToStep(n) {
          const section = document.getElementById('s' + n);
          const content = document.getElementById('config-content');
          if (!section || !content) return;
          if (!section.classList.contains('open')) section.classList.add('open');
          content.scrollTo({ top: section.offsetTop - 16, behavior: 'smooth' });
          document.querySelectorAll('.rail-item').forEach((el, i) => {
            el.classList.toggle('active', i === n);
          });
        }

        // IntersectionObserver: sync active rail node with visible section
        (function initRailObserver() {
          const content = document.getElementById('config-content');
          if (!content) return;
          const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
              if (entry.isIntersecting) {
                const idx = parseInt(entry.target.dataset.stepIndex, 10);
                document.querySelectorAll('.rail-item').forEach((el, i) => {
                  el.classList.toggle('active', i === idx);
                });
              }
            });
          }, {
            root: content,
            rootMargin: '-10% 0px -85% 0px',
            threshold: 0
          });
          document.querySelectorAll('.step-section').forEach((el, i) => {
            el.dataset.stepIndex = i;
            observer.observe(el);
          });
        })();
        </script>
        </form>

```

- [ ] **Step 4: Update the Python script with the actual HTML and run it**

Replace the `REPLACE_ME` placeholder in `scripts/replace_config_tab.py` with the HTML block from Step 3. Then run:

```bash
python3 scripts/replace_config_tab.py
```

Expected output:
```
Replacing NNNNN chars (NNNN lines)
Done.
```

- [ ] **Step 5: Verify critical IDs are all present in the new HTML**

```bash
python3 - <<'EOF'
import re
with open('src/web/templates/workflow.html') as f:
    html = f.read()

required_ids = [
    'workflowConfigForm', 'save-config-button',
    'os-detection-model-container', 'os-detection-prompt-container',
    'rank-agent-model-container', 'rank-agent-prompt-container',
    'rank-agent-qa-prompt-container', 'rank-qa-agent-prompt-content',
    'rank-agent-qa-configs',
    'extract-agent-model-container', 'extract-agent-prompt-container',
    'extract-agent-qa-prompt-container',
    'sigma-agent-model-container', 'sigma-agent-prompt-container',
    'cmdlineextract-agent-prompt-container', 'cmdlineextract-agent-qa-configs',
    'cmdlineextract-agent-qa-prompt-container',
    'proctreeextract-agent-prompt-container', 'proctreeextract-agent-qa-configs',
    'proctreeextract-agent-qa-prompt-container',
    'huntqueriesextract-agent-prompt-container', 'huntqueriesextract-agent-qa-configs',
    'huntqueriesextract-agent-qa-prompt-container',
    'junkFilterThreshold', 'rankingThreshold', 'similarityThreshold',
    'rank-agent-enabled', 'qa-rankagent',
    'toggle-cmdlineextract-enabled', 'toggle-proctreeextract-enabled',
    'toggle-huntqueriesextract-enabled',
    'sigma-fallback-enabled', 'qaMaxRetries',
    'import-preset-input', 'configPresetListModal', 'configVersionListModal',
]
missing = [id for id in required_ids if f'id="{id}"' not in html]
if missing:
    print("MISSING IDs:", missing)
else:
    print("All", len(required_ids), "required IDs present.")
EOF
```

Expected: `All 35 required IDs present.`

- [ ] **Step 6: Verify no duplicate IDs (count occurrences)**

```bash
python3 - <<'EOF'
import re, collections
with open('src/web/templates/workflow.html') as f:
    html = f.read()
ids = re.findall(r'\bid="([^"]+)"', html)
counts = collections.Counter(ids)
dups = {k: v for k, v in counts.items() if v > 1}
# Some IDs like import-preset-input-modal appear twice intentionally in modals
known_dups = {'import-preset-input-modal'}
real_dups = {k: v for k, v in dups.items() if k not in known_dups}
if real_dups:
    print("DUPLICATE IDs:", real_dups)
else:
    print("No unexpected duplicate IDs.")
EOF
```

Expected: `No unexpected duplicate IDs.`

- [ ] **Step 7: Commit**

```bash
git add src/web/templates/workflow.html scripts/replace_config_tab.py
git commit -m "feat(ui): implement Operator Console config tab redesign"
```

---

### Task 4: Visual verification

**Files:** No changes

- [ ] **Step 1: Start the dev server**

```bash
./start.sh
```

Or if already running, reload the page.

- [ ] **Step 2: Open the config tab in browser**

Navigate to `http://127.0.0.1:8001/workflow#config`

- [ ] **Step 3: Verify layout structure**

Check that:
- [ ] Left rail with 7 numbered nodes (0–6) is visible at left edge
- [ ] Pipeline connector lines are visible between nodes with downward-flow animation
- [ ] Step 0 (OS Detection) is expanded by default, others collapsed
- [ ] Clicking a rail node scrolls to and expands the corresponding step section
- [ ] Each section has a colored left border matching its step color
- [ ] Sticky footer with Save/Reset buttons is always visible at the bottom
- [ ] All sub-agent panels expand/collapse independently via `toggleSA()`

- [ ] **Step 4: Verify JS functionality**

Check that:
- [ ] `loadConfig()` populates all model selectors (open browser devtools console, look for errors)
- [ ] `autoSaveConfig()` enables the Save button when a threshold slider is moved
- [ ] QA toggle for RankAgent shows/hides the QA sub-panel (`rank-agent-qa-configs`)
- [ ] Enable/disable toggle for CmdlineExtract calls `handleExtractAgentToggle`
- [ ] Footer Save button submits the form (check Network tab for POST to `/api/workflow/config`)
- [ ] No JS errors in console

- [ ] **Step 5: Commit cleanup script**

```bash
git rm scripts/replace_config_tab.py
git commit -m "chore: remove one-off config tab replacement script"
```

---

## Summary

| Task | Files | Risk |
|------|-------|------|
| 1: Fonts | `base.html` | Low |
| 2: CSS | `workflow.html` style block | Low |
| 3: HTML replacement | `workflow.html` lines 407–1471 | Medium (large substitution; verify IDs) |
| 4: Visual check | — | — |

**Do not skip Task 3 Step 5 (ID presence check) and Step 6 (duplicate ID check)** — these are the main failure modes for this type of DOM replacement.
