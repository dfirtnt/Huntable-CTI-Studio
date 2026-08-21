// Workflow — Operator Console + expanded prompt editor module (section toggles,
// pipeline rail, the expanded prompt modal, and shared prompt validation).
//
// Extracted verbatim from src/web/templates/workflow.html (formerly lines
// 2421-2871), dedented by the template's 8-space indent and otherwise unchanged.
// Jinja-free, so it relocates cleanly.
//
// Loaded as a classic script — the remaining inline shell and the four workflow
// modules call these as globals (config.js calls openExpandedPromptEditor,
// _collectPromptIssues and _renderValidateResult; queue.js calls
// _renderValidateResult; the template's onclick attributes call toggle, toggleSA,
// togglePipelineRail, scrollToStep, validateAllConfig and the modal helpers).
//
// It loads BEFORE the inline shell and page.js on purpose. This file registers a
// DOMContentLoaded listener that inline fired FIRST -- ahead of page.js's two
// registrations and the two column-resize listeners at the end of the template --
// and loading here keeps that relative firing order exactly as it was. Its only
// load-time DOM read is #oc-rail (template line ~1849), which is parsed well
// before this script position.
// ── Operator Console: toggle + rail nav + IntersectionObserver ──

function toggle(id) {
  var el = document.getElementById(id);
  if (!el) return;
  if (/^s\d$/.test(id) && el.classList.contains('step-section')) {
    document.querySelectorAll('.step-section').forEach(function(s) {
      if (s.id !== id) s.classList.remove('open');
    });
  }
  el.classList.toggle('open');
}

function toggleSA(id) {
  var el = document.getElementById(id);
  if (el) {
    el.classList.toggle('open');
    var header = el.querySelector('.sa-header');
    if (header) header.setAttribute('aria-expanded', el.classList.contains('open') ? 'true' : 'false');
  }
}

function togglePipelineRail() {
  const rail = document.getElementById('oc-rail');
  if (!rail) return;
  rail.classList.toggle('collapsed');
  try {
    localStorage.setItem('oc-rail-collapsed', rail.classList.contains('collapsed') ? '1' : '0');
  } catch (e) { /* storage unavailable */ }
}

// Restore prior state; default (no stored value) stays collapsed.
(function () {
  try {
    const stored = localStorage.getItem('oc-rail-collapsed');
    if (stored === '0') {
      const rail = document.getElementById('oc-rail');
      if (rail) rail.classList.remove('collapsed');
    }
  } catch (e) { /* storage unavailable */ }
})();

/* ── Expanded Prompt Editor ─────────────────── */
var _expandedPromptAgent = null;

function openExpandedPromptEditor(agentName) {
  _expandedPromptAgent = agentName;
  const overlay = document.getElementById('prompt-expanded-overlay');
  document.getElementById('prompt-exp-title').textContent = agentDisplayName(agentName) + ' Prompt';

  // Get current model info
  const agentId = agentName.toLowerCase().replace(/agent/g, 'agent');
  const prefix = agentName === 'RankAgent' ? 'rankagent' : agentName === 'ExtractAgent' ? 'extractagent' : agentName === 'SigmaAgent' ? 'sigmaagent' : agentName.toLowerCase();
  const providerEl = document.getElementById(prefix + '-provider');
  const modelEl = document.querySelector('[id^="' + prefix + '-model"]');
  const modelInfo = (providerEl ? providerEl.selectedOptions[0]?.text : '') + (modelEl && modelEl.value ? ' / ' + modelEl.value : '');
  document.getElementById('prompt-exp-model').textContent = modelInfo;

  // Load prompt content from inline textareas or display divs
  const sysTextarea = document.getElementById(prefix + '-prompt-system-2');
  const sysDisplay = document.getElementById(prefix + '-prompt-system-display-2');
  const userTextarea = document.getElementById(prefix + '-prompt-user-2');
  const userDisplay = document.getElementById(prefix + '-prompt-user-display-2');

  const sysVal = sysTextarea ? sysTextarea.value : (sysDisplay ? sysDisplay.textContent : '');
  const userVal = userTextarea ? userTextarea.value : (userDisplay ? userDisplay.textContent : '');

  document.getElementById('prompt-exp-system').value = sysVal === '(empty)' ? '' : sysVal;
  document.getElementById('prompt-exp-user').value = userVal === '(empty)' ? '' : userVal;

  // Hide user prompt section when the agent has a locked user scaffold.
  // Use inline style.display to override the parent flex-layout CSS.
  const userLocked = (typeof isLockedExtractorPrompt === 'function' && isLockedExtractorPrompt(agentName))
                  || (typeof isLockedCanonicalPrompt === 'function' && isLockedCanonicalPrompt(agentName));
  const userSection = document.getElementById('prompt-exp-user-section');
  const userLockedMsg = document.getElementById('prompt-exp-user-locked');
  if (userSection && userLockedMsg) {
    userSection.style.display = userLocked ? 'none' : '';
    userLockedMsg.style.display = userLocked ? '' : 'none';
  }

  // Clear any previous validation result when re-opening the modal.
  const prevValidateResult = document.getElementById('prompt-exp-validate-result');
  if (prevValidateResult) {
    prevValidateResult.style.display = 'none';
    prevValidateResult.textContent = '';
    prevValidateResult.className = 'mt-2';
  }

  // Apply view vs edit mode based on the inline-panel's current edit state
  const isEditing = !!(typeof editingPrompts !== 'undefined' && editingPrompts[agentName]);
  applyExpandedEditorMode(isEditing);

  updateExpandedCharCount();

  const expSys = document.getElementById('prompt-exp-system');
  const expUsr = document.getElementById('prompt-exp-user');
  if (expSys) expSys.oninput = updateExpandedCharCount;
  if (expUsr) expUsr.oninput = updateExpandedCharCount;

  overlay.classList.add('visible');
  document.getElementById('prompt-exp-system').focus();
}

// Toggle the modal's read-only/edit affordances. Called on open, and
// when the user transitions from view to edit via the modal's Edit button.
function applyExpandedEditorMode(editing) {
  const sysTA = document.getElementById('prompt-exp-system');
  const usrTA = document.getElementById('prompt-exp-user');
  const editBtn = document.getElementById('prompt-exp-edit-btn');
  const validateBtn = document.getElementById('prompt-exp-validate-btn');
  const saveBtn = document.getElementById('prompt-exp-save-btn');
  const modeBadge = document.getElementById('prompt-exp-mode-badge');

  if (sysTA) sysTA.readOnly = !editing;
  if (usrTA) usrTA.readOnly = !editing;
  if (editBtn) editBtn.style.display = editing ? 'none' : '';
  if (saveBtn) saveBtn.style.display = editing ? '' : 'none';
  if (modeBadge) modeBadge.textContent = editing ? 'Editing' : 'Read-only';
}

// Transition the modal (and the underlying inline panel) into edit mode.
function editExpandedPrompt() {
  if (!_expandedPromptAgent) return;
  const agentName = _expandedPromptAgent;
  // Flip inline-panel state via the same mechanism as the inline Edit button
  if (typeof editingPrompts !== 'undefined') editingPrompts[agentName] = true;
  // Re-render all inline prompt panels so the underlying panel gains its textareas
  if (typeof renderAgentPrompts === 'function') renderAgentPrompts();
  // Flip the modal's affordances
  applyExpandedEditorMode(true);
  // Focus the system textarea so the user can start typing
  const sysTA = document.getElementById('prompt-exp-system');
  if (sysTA) sysTA.focus();
}

function closeExpandedPromptEditor() {
  document.getElementById('prompt-expanded-overlay').classList.remove('visible');
  _expandedPromptAgent = null;
}

function updateExpandedCharCount() {
  const sys = document.getElementById('prompt-exp-system').value.length;
  const usr = document.getElementById('prompt-exp-user').value.length;
  document.getElementById('prompt-exp-charcount').textContent = (sys + usr) + ' chars (system: ' + sys + ', user: ' + usr + ')';
}

function saveExpandedPrompt() {
  if (!_expandedPromptAgent) return;
  const agentName = _expandedPromptAgent;

  // Read directly from modal textareas -- no relay through inline panel needed.
  // Previously this copied values to the inline {prefix}-prompt-system-2 textarea
  // and called saveAgentPrompt2 after a 200ms setTimeout. That approach was brittle:
  // if the inline agent card hadn't been rendered into edit mode yet (collapsed section,
  // different tab, or slow render), the textarea lookup failed and the save silently
  // aborted with "Prompt elements not found". Values are already in the modal -- use them.
  const sysTA = document.getElementById('prompt-exp-system');
  if (!sysTA) return;

  // Gate: run validation before saving. Block on errors; warnings are allowed through.
  const systemVal = (sysTA.value || '').trim();
  const issues = _collectPromptIssues(agentName, systemVal);
  const errors = issues.filter(function(i) { return i.level === 'error'; });
  if (errors.length > 0) {
    const resultDiv = document.getElementById('prompt-exp-validate-result');
    if (resultDiv) _renderValidateResult(resultDiv, issues);
    return;
  }

  const userLocked = (typeof isLockedExtractorPrompt === 'function' && isLockedExtractorPrompt(agentName))
                  || (typeof isLockedCanonicalPrompt === 'function' && isLockedCanonicalPrompt(agentName));
  const usrTA = document.getElementById('prompt-exp-user');
  const userOverride = (!userLocked && usrTA) ? usrTA.value : null;

  // Close modal first so UI feels immediately responsive; save runs async
  closeExpandedPromptEditor();

  if (typeof saveAgentPrompt2 === 'function') {
    saveAgentPrompt2(agentName, { systemOverride: sysTA.value, userOverride: userOverride });
  }
}

// NOTE: _EXTRACTION_AGENTS, _TRACEABILITY_FIELDS, _SYSTEM_WARN_TOKENS, _INSTRUCTIONS_WARN_TOKENS
// are defined as local constants inside _collectPromptIssues() to avoid script-block ordering
// issues (EXTRACT_SUB_AGENTS is defined in a later <script> block).

function _renderValidateResult(resultDiv, issues) {
  resultDiv.textContent = '';
  resultDiv.style.display = '';
  if (issues.length === 0) {
    resultDiv.className = 'mt-2 px-3 py-2 rounded-md text-sm bg-green-50 border border-green-300 text-green-800 dark:bg-green-900/30 dark:border-green-700 dark:text-green-300';
    resultDiv.textContent = 'Validation passed. Prompt is ready to save.';
    return;
  }
  const errorCount = issues.filter(i => i.level === 'error').length;
  const warnCount  = issues.filter(i => i.level === 'warn').length;
  resultDiv.className = errorCount > 0
    ? 'mt-2 px-3 py-2 rounded-md text-sm bg-red-50 border border-red-300 text-red-800 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300'
    : 'mt-2 px-3 py-2 rounded-md text-sm bg-yellow-50 border border-yellow-300 text-yellow-800 dark:bg-yellow-900/30 dark:border-yellow-700 dark:text-yellow-300';
  const parts = [];
  if (errorCount) parts.push(errorCount + ' error' + (errorCount > 1 ? 's' : ''));
  if (warnCount)  parts.push(warnCount  + ' warning' + (warnCount > 1 ? 's' : ''));
  const header = document.createElement('strong');
  header.textContent = 'Validation: ' + parts.join(', ');
  resultDiv.appendChild(header);
  const ul = document.createElement('ul');
  ul.className = 'mt-1 list-disc list-inside space-y-1';
  issues.forEach(function(issue) {
    const li = document.createElement('li');
    li.textContent = '[' + issue.level.toUpperCase() + '] ' + issue.msg;
    ul.appendChild(li);
  });
  resultDiv.appendChild(ul);
}

/**
 * Shared prompt validation logic used by both inline and expanded editors.
 * Returns an array of {level: 'error'|'warn', msg: string} issues.
 */
function _collectPromptIssues(agentName, systemVal) {
  const issues = [];

  // Local constants — defined here (not at module scope) because EXTRACT_SUB_AGENTS
  // is declared in a later <script> block and would be undefined at parse time of this block.
  const _TRACEABILITY_FIELDS = ['value', 'source_evidence', 'extraction_justification', 'confidence_score'];
  const _TRACEABILITY_REQUIRED = ['source_evidence', 'extraction_justification', 'confidence_score'];
  const _SYSTEM_WARN_TOKENS = [
    ['LITERAL TEXT EXTRACTOR',    'ROLE block (sec 1)'],
    ['sub-agent of ExtractAgent', 'ARCHITECTURE CONTEXT (sec 3)'],
    ['Do NOT use prior knowledge','INPUT CONTRACT (sec 4)'],
    ['Do NOT fetch',              'INPUT CONTRACT fetch rule (sec 4)'],
    ['[ ]',                       'VERIFICATION CHECKLIST (sec 12)'],
  ];
  const _INSTRUCTIONS_WARN_TOKENS = [
    ['ONLY valid JSON',   'JSON-only directive (sec 13)'],
    ['When in doubt, OMIT','FINAL REMINDER (sec 16)'],
    ['source_evidence',   'traceability field mention (sec 14)'],
  ];

  // All agents: system prompt must not be empty.
  if (!systemVal) {
    issues.push({ level: 'error', msg: 'System prompt is empty. The agent will hard-fail at runtime.' });
    return issues;
  }

  if (typeof EXTRACT_SUB_AGENTS !== 'undefined' && EXTRACT_SUB_AGENTS.includes(agentName)) {
    // Extraction sub-agents accept two valid system-prompt shapes:
    //   1. Full JSON envelope (role/task/json_example/instructions) -- validated below.
    //   2. Plain role-persona string -- saveAgentPrompt2 will wrap it into the
    //      existing envelope (see line ~10527). For this shape, JSON validation
    //      does not apply; the non-empty check earlier in this function is sufficient.
    let parsed;
    try {
      parsed = JSON.parse(systemVal);
    } catch (e) {
      // Plain role text -- valid shape, skip envelope validation.
      return issues;
    }
    // Defensive: a JSON-parsed scalar (e.g. a quoted string) is also plain-role.
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return issues;
    }

    // Hard fail: user_template must NOT be present (sec 5 note — code-owned scaffold).
    if ('user_template' in parsed) {
      issues.push({ level: 'error', msg: "'user_template' must not be present (Extractor Contract sec 5). The user scaffold is code-owned." });
    }

    // Hard fail: role/system must be non-empty (sec 1).
    const roleContent = ((parsed.system || parsed.role) || '').trim();
    if (!roleContent) {
      issues.push({ level: 'error', msg: "Missing required 'role'/'system' key (Extractor Contract sec 1). Agent will hard-fail at runtime." });
    }

    // Hard fail: instructions must be non-empty (sec 2).
    const instructions = (parsed.instructions || '').trim();
    if (!instructions) {
      issues.push({ level: 'error', msg: "Missing required 'instructions' key (Extractor Contract sec 2). Agent will hard-fail at runtime." });
    }

    // Hard fail: json_example must be present (sec 4).
    if (parsed.json_example === undefined || parsed.json_example === null) {
      issues.push({ level: 'error', msg: "Missing required 'json_example' key (Extractor Contract sec 4). Agent will hard-fail at runtime." });
    } else {
      // Hard fail: json_example must be valid JSON.
      let parsedExample = null;
      try {
        parsedExample = typeof parsed.json_example === 'string'
          ? JSON.parse(parsed.json_example) : parsed.json_example;
      } catch (e) {
        issues.push({ level: 'error', msg: "'json_example' is not valid JSON (Extractor Contract sec 4)." });
      }
      // Hard fail: json_example items must have all traceability fields (sec 3-4).
      if (parsedExample && typeof parsedExample === 'object') {
        let items = null;
        for (const v of Object.values(parsedExample)) {
          if (Array.isArray(v) && v.length > 0 && v[0] && typeof v[0] === 'object') {
            items = v; break;
          }
        }
        if (items) {
          const itemKeys = new Set(Object.keys(items[0]));
          const missing = _TRACEABILITY_REQUIRED.filter(f => !itemKeys.has(f));
          if (missing.length > 0) {
            issues.push({ level: 'error', msg: "json_example items missing traceability fields: " + missing.join(', ') + " (Extractor Contract sec 3-4)." });
          }
          // value is only required for simple extractors (no domain-specific fields)
          const hasDomainFields = [...itemKeys].some(f => !_TRACEABILITY_FIELDS.includes(f));
          if (!hasDomainFields && !itemKeys.has('value')) {
            issues.push({ level: 'error', msg: "json_example items missing 'value' field (simple extractor requires it)." });
          }
        }
      }
    }

    // Warn-only: system/role content tokens (mirrors _SYSTEM_WARN_ONLY).
    if (roleContent) {
      _SYSTEM_WARN_TOKENS.forEach(function([token, label]) {
        if (!roleContent.includes(token)) {
          issues.push({ level: 'warn', msg: "Role/system missing expected token for " + label + ": \"" + token + "\"" });
        }
      });
    }

    // Warn-only: instructions tokens (mirrors _INSTRUCTIONS_WARN_ONLY).
    if (instructions) {
      _INSTRUCTIONS_WARN_TOKENS.forEach(function([token, label]) {
        if (!instructions.includes(token)) {
          issues.push({ level: 'warn', msg: "Instructions missing expected token for " + label + ": \"" + token + "\"" });
        }
      });
    }
  }

  // Non-extraction agents (RankAgent, SigmaAgent, ExtractAgent):
  // If the prompt is JSON with a role/system key, validate it is non-empty.
  // RankAgent hard-fails at runtime if JSON prompt has no system/role (PreprocessInvariantError).
  // SigmaAgent falls back to a default but should still be flagged.
  if (!(typeof EXTRACT_SUB_AGENTS !== 'undefined' && EXTRACT_SUB_AGENTS.includes(agentName))) {
    let parsed = null;
    try { parsed = JSON.parse(systemVal); } catch (_) { /* plain text prompt -- OK */ }
    if (parsed && typeof parsed === 'object') {
      const roleContent = ((parsed.system || parsed.role) || '').trim();
      if (!roleContent) {
        issues.push({ level: 'error', msg: "JSON prompt has empty 'system'/'role' key. Agent will fail or use a fallback at runtime." });
      }
      // Warn if the prompt looks like extraction JSON accidentally applied to a non-extraction agent
      if ('json_example' in parsed || 'instructions' in parsed) {
        const hasEmptyFields = (!parsed.instructions || parsed.instructions === '')
                            || (parsed.json_example === '{}' || parsed.json_example === '');
        if (hasEmptyFields) {
          issues.push({ level: 'warn', msg: "Prompt contains extraction-style keys (json_example, instructions) with empty values. This may be a misconfigured preset." });
        }
      }
    }
  }

  return issues;
}

async function validateAllConfig() {
  const btn = document.getElementById('validate-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Validating...'; }

  try {
    const resp = await fetch('/api/workflow/config/validate');
    const data = await resp.json();
    const issues = data.issues || [];

    if (issues.length === 0) {
      showNotification('Config validation passed. All agents, prompts, and thresholds are valid.', 'success');
    } else {
      const errorCount = issues.filter(function(i) { return i.level === 'error'; }).length;
      const warnCount  = issues.filter(function(i) { return i.level === 'warn'; }).length;
      const summary = [];
      if (errorCount) summary.push(errorCount + ' error' + (errorCount > 1 ? 's' : ''));
      if (warnCount)  summary.push(warnCount  + ' warning' + (warnCount > 1 ? 's' : ''));
      const detail = issues.map(function(i) { return '[' + i.level.toUpperCase() + '] ' + i.msg; }).join('\n');
      showNotification('Validation: ' + summary.join(', ') + '\n' + detail, 'error');
    }
  } catch (e) {
    showNotification('Validation request failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Validate All'; }
  }
}

function validateExpandedPrompt() {
  if (!_expandedPromptAgent) return;
  const resultDiv = document.getElementById('prompt-exp-validate-result');
  const sysTA = document.getElementById('prompt-exp-system');
  if (!resultDiv || !sysTA) return;

  const systemVal = (sysTA.value || '').trim();
  const issues = _collectPromptIssues(_expandedPromptAgent, systemVal);
  _renderValidateResult(resultDiv, issues);
}

// Update char count on input + close overflow menu on outside click + ESC closes expanded editor
document.addEventListener('DOMContentLoaded', () => {
  const expSys = document.getElementById('prompt-exp-system');
  const expUsr = document.getElementById('prompt-exp-user');
  if (expSys) expSys.addEventListener('input', updateExpandedCharCount);
  if (expUsr) expUsr.addEventListener('input', updateExpandedCharCount);
  document.addEventListener('click', (e) => {
    const menu = document.getElementById('footer-overflow-menu');
    if (menu && !e.target.closest('.relative')) menu.classList.add('hidden');
  });
  // Keyboard path for the click-driven step triggers: each carries an inline
  // onclick, so click() reuses that handler rather than duplicating it.
  // preventDefault stops Space scrolling #config-content out from under the
  // section scrollToStep is about to align.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const trigger = e.target.closest('.section-header, .rail-item, .sa-header');
    if (!trigger) return;
    // Nested native controls (the sa-header help buttons) keep their own
    // activation; without this preventDefault would swallow it.
    const inner = e.target.closest('button, a, input, select, textarea, label');
    if (inner && inner !== trigger && trigger.contains(inner)) return;
    e.preventDefault();
    trigger.click();
  });

  // ESC key closes the expanded prompt editor when it's open
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const overlay = document.getElementById('prompt-expanded-overlay');
    if (overlay && overlay.classList.contains('visible')) {
      closeExpandedPromptEditor();
    }
  });
});

// scrollToStep is the only live mutation path for .step-section.open, so
// syncing aria-expanded from there covers every state change.
function _syncStepAriaExpanded() {
  document.querySelectorAll('.step-section').forEach(function(section) {
    var header = section.querySelector('.section-header');
    if (header) header.setAttribute('aria-expanded', section.classList.contains('open') ? 'true' : 'false');
  });
}

function scrollToStep(n) {
  var section = document.getElementById('s' + n);
  var content = document.getElementById('config-content');
  if (!section || !content) return;
  if (!section.classList.contains('open')) {
    document.querySelectorAll('.step-section').forEach(function(s) { s.classList.remove('open'); });
    section.classList.add('open');
  }
  // Align the section header to the container's visible top. offsetTop is
  // unusable here: #config-content is not positioned, so offsetParent is <body>
  // and offsetTop would include the page header above the panel, overshooting
  // every scroll. 'instant' rather than smooth: the accordion re-layout is
  // already instant, and a smooth animation's target goes stale if layout
  // shifts (async config load) or the tab is backgrounded mid-flight.
  var top = content.scrollTop + section.getBoundingClientRect().top - content.getBoundingClientRect().top - 16;
  // Top up the scroll range with the trailing spacer when the collapsed accordion
  // leaves too little content below the target for it to reach the container top.
  var spacer = document.getElementById('config-scroll-spacer');
  if (spacer) {
    var baseScrollHeight = content.scrollHeight - spacer.offsetHeight;
    var deficit = Math.ceil(top + content.clientHeight - baseScrollHeight);
    spacer.style.height = Math.max(0, deficit) + 'px';
  }
  content.scrollTo({ top: top, behavior: 'instant' });
  document.querySelectorAll('.rail-item').forEach(function(el, i) {
    el.classList.toggle('active', i === n);
  });
  _syncStepAriaExpanded();
}

// Rail active state is derived from the open step (single source of truth:
// scrollToStep opens exactly one section and flags the matching rail item).
// No IntersectionObserver here — it would fight the accordion invariant.
