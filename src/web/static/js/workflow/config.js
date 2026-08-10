// Workflow — configuration module (agent config, providers/models, prompts, presets).
//
// Extracted verbatim from src/web/templates/workflow.html: the contiguous
// config region (formerly lines 3872-10530), then the global sub-agent
// fallback block (formerly lines 12127-12169) appended below.
//
// Loaded as a classic script AFTER workflow.html's main inline block, which
// still declares the shared header this code reads at load time
// (EXTRACT_SUB_AGENTS, AGENT_DISPLAY_NAMES, currentTab).

// Configuration Functions
let currentConfig = null;
let isInitializing = true; // Flag to prevent autosave during page initialization
window.isInitializing = true; // Mirror for Playwright waitForFunction
let agentPrompts = {};
let agentModels = {};
const extractSubAgents = EXTRACT_SUB_AGENTS;
let disabledExtractAgents = new Set();
let autoSaveTimeout = null; // Debounce timer for autosave
let autoSaveModelChangeTimeout = null; // Debounce timer for model-change autosave
let lastValidationWarnAt = 0; // Throttle validation-failure console.warn (avoid spam)
const VALIDATION_WARN_THROTTLE_MS = 10000; // Log same validation failure at most once per 10s
let isSavingPrompt = false; // Block autoSave during prompt save to prevent overwriting
let lastPromptSaveAt = 0; // Timestamp of last prompt save (prevents loadAgentPrompts race from overwriting)
let lastSavedPromptAgent = null; // Agent name last saved

// Early global stub to avoid inline-handler errors before full script loads
if (typeof window !== 'undefined' && typeof window.onAgentProviderChange !== 'function') {
    window.onAgentProviderChange = function stubAgentProviderChange(agentPrefix) {
        if (typeof window._onAgentProviderChangeImpl === 'function') {
            return window._onAgentProviderChangeImpl(agentPrefix);
        }
        // no-op until main script finishes loading
    };
}

// Early stub for global provider refresh to prevent ReferenceError before definition
if (typeof window !== 'undefined' && typeof window.refreshAllProviderBlocks !== 'function') {
    window.refreshAllProviderBlocks = function stubRefreshAllProviderBlocks() {
        // no-op until main script defines real function
    };
}

// #region agent log helper (disabled)
function __dbgLog(hypothesisId, message, data) {
    // Debug logging disabled - no-op to prevent network errors
    // Original implementation attempted to send logs to http://127.0.0.1:7242/ingest
}
// #endregion

// All available providers - will be filtered based on Settings
const allProviderOptions = [
    { value: 'lmstudio', label: 'LMStudio (Local)' },
    { value: 'openai', label: 'OpenAI (Cloud)' },
    { value: 'codex', label: 'Codex Subscription' },
    { value: 'anthropic', label: 'Anthropic Claude (Cloud)' }
];

// Current enabled providers - updated from Settings
let providerOptions = [...allProviderOptions];

// Track enabled provider settings
let enabledProviders = {
    lmstudio: true,  // LMStudio always available (local) when enabled
    openai: true,
    codex: false,
    anthropic: true
};

/** First enabled provider, or '' when none (e.g. LMStudio disabled, no API keys). */
function getDefaultProvider() {
    return (providerOptions[0]?.value || '').toString().trim().toLowerCase();
}

const providerDefaults = {
    openai: 'gpt-4o-mini',
    codex: 'gpt-5.6-luna',
    anthropic: 'claude-sonnet-4-5'
};

// Cache from /api/workflow/provider-options; undefined = not yet fetched, null = fetched but empty
let _cachedLMStudioModels;
// Flag: provider-options already loaded this page session (skip redundant catalog re-fetch)
let _workflowProviderOptionsLoaded = false;

// Fetch unified provider availability from the server
async function loadEnabledProviders() {
    try {
        const response = await fetch('/api/workflow/provider-options');
        if (!response.ok) {
            console.warn('Failed to fetch provider options, using all providers');
            return;
        }
        const data = await response.json();
        const providers = data.providers || {};

        enabledProviders = {
            lmstudio: !!(providers.lmstudio && providers.lmstudio.enabled),
            openai: !!(providers.openai && providers.openai.enabled),
            codex: !!(providers.codex && providers.codex.enabled),
            anthropic: !!(providers.anthropic && providers.anthropic.enabled),
        };

        // Filter providerOptions based on enabled settings
        providerOptions = allProviderOptions.filter(opt => enabledProviders[opt.value]);

        // Populate commercialModelCatalog from unified response (avoids second fetch)
        const newCatalog = {};
        ['openai', 'anthropic', 'codex'].forEach(p => {
            if (providers[p] && Array.isArray(providers[p].models) && providers[p].models.length > 0) {
                newCatalog[p] = providers[p].models;
            }
        });
        if (Object.keys(newCatalog).length > 0) {
            commercialModelCatalog = newCatalog;
            cacheProviderCatalog(newCatalog);
        }

        // Cache LM Studio models for the first loadLMStudioModels() call
        if (providers.lmstudio && Array.isArray(providers.lmstudio.models)) {
            _cachedLMStudioModels = providers.lmstudio.models;
        } else {
            _cachedLMStudioModels = null;
        }

        _workflowProviderOptionsLoaded = true;

        console.log('Enabled providers:', enabledProviders);
        console.log('Filtered provider options:', providerOptions);

        // Refresh all provider dropdowns
        refreshProviderDropdowns();
        // loadConfig can render before this live provider request completes.
        // Re-render now so Codex uses its populated model select, not its text fallback.
        if (typeof refreshAllProviderBlocks === 'function') {
            refreshAllProviderBlocks();
        }
    } catch (error) {
        console.error('Error loading provider options:', error);
    }
}

// Refresh all provider dropdowns with current enabled providers
function refreshProviderDropdowns() {
    // Update all hardcoded provider selects
    const providerSelects = document.querySelectorAll('select[id$="-provider"]');
    providerSelects.forEach(select => {
        const currentValue = select.value;
        const currentOptions = Array.from(select.options).map(opt => ({
            value: opt.value,
            selected: opt.selected
        }));
        
        // Clear and repopulate options
        select.innerHTML = '';
        providerOptions.forEach(opt => {
            const option = document.createElement('option');
            option.value = opt.value;
            option.textContent = opt.label;
            // Preserve selection if still available
            if (opt.value === currentValue) {
                option.selected = true;
            }
            select.appendChild(option);
        });
        
        // If current value is no longer available, select first option
        if (currentValue && !providerOptions.find(opt => opt.value === currentValue)) {
            if (select.options.length > 0) {
                const newValue = select.options[0].value;
                select.selectedIndex = 0;
                // Only trigger change event if value actually changed
                if (newValue !== currentValue) {
                    select.dispatchEvent(new Event('change'));
                }
            }
        } else if (currentValue && select.value !== currentValue) {
            // Restore selection if it was preserved but not set correctly
            select.value = currentValue;
        }
    });
}

// Allow-list style checks to keep provider dropdowns focused on valid models
const providerModelGuards = {
    openai: /^(gpt|o\d|text-|davinci|curie|babbage|ada|whisper|omni|turbo|codex)/i,
    codex: /^(gpt|o\d|codex)/i,
    anthropic: /^claude/i
};

function inferProviderFromModel(modelId) {
    if (!modelId || typeof modelId !== 'string') return null;
    const trimmed = modelId.trim();
    if (!trimmed) return null;
    if (providerModelGuards.openai && providerModelGuards.openai.test(trimmed)) return 'openai';
    if (providerModelGuards.codex && providerModelGuards.codex.test(trimmed)) return 'codex';
    if (providerModelGuards.anthropic && providerModelGuards.anthropic.test(trimmed)) return 'anthropic';
    return null;
}

function isModelAllowedForProvider(provider, modelId) {
    if (!modelId) return false;
    const guard = providerModelGuards[provider];
    if (!guard) {
        // For LMStudio, model should NOT match commercial provider patterns
        if (provider === 'lmstudio') {
            const trimmed = modelId.trim();
            // Reject if it matches OpenAI or Anthropic patterns
            if (providerModelGuards.openai && providerModelGuards.openai.test(trimmed)) return false;
            if (providerModelGuards.anthropic && providerModelGuards.anthropic.test(trimmed)) return false;
            return true;
        }
        return true;
    }
    return guard.test(modelId.trim());
}

// Patterns for non-chat OpenAI models
const NON_CHAT_MODEL_PATTERNS = [
    /-codex/i,
    /-audio/i,
    /-image/i,
    /-realtime/i,
    /-tts/i,
    /-transcribe/i,
    /-search/i,
    /^gpt-realtime/i,
    /^gpt-audio/i,
    /^gpt-image/i,
    /-deep-research/i,
    /^omni-moderation/i,
    /^text-davinci/i,
    /^davinci-/i,
    /^curie-/i,
    /^babbage-/i,
    /^ada-/i
];

// Valid base chat model patterns
const VALID_CHAT_BASE_PATTERNS = [
    /^gpt-5(\.\d+)?(-(pro|mini|nano))?$/i,
    /^gpt-4(\.\d+)?(-(mini|nano|turbo))?$/i,
    /^gpt-4o(-mini)?$/i,
    /^gpt-3\.5-turbo/i,
    /^o[134](-(pro|mini))?$/i
];

/**
 * Client-side validation for OpenAI chat models
 * @param {string} modelId - Model identifier
 * @returns {Object} - {valid: boolean, error?: string, suggestion?: string}
 */
function isValidOpenAIChatModel(modelId) {
    if (!modelId || typeof modelId !== 'string') {
        return {valid: false, error: 'Model ID is required'};
    }
    
    const trimmed = modelId.trim();
    if (!trimmed) {
        return {valid: false, error: 'Model ID cannot be empty'};
    }
    
    // Must match OpenAI pattern
    if (!providerModelGuards.openai || !providerModelGuards.openai.test(trimmed)) {
        return {valid: false, error: `Model "${trimmed}" does not match OpenAI patterns`};
    }
    
    // Exclude non-chat models
    for (const pattern of NON_CHAT_MODEL_PATTERNS) {
        if (pattern.test(trimmed)) {
            return {
                valid: false,
                error: `Model "${trimmed}" is not a chat completion model (specialized model detected)`,
                suggestion: 'Use a chat completion model like gpt-5.2-pro, gpt-4o, or gpt-4o-mini'
            };
        }
    }
    
    // Check if it matches a valid base pattern
    const baseModel = trimmed.replace(/-\d{4}-\d{2}-\d{2}(-preview)?$/, '')
                             .replace(/-latest$/, '')
                             .replace(/-preview$/, '');
    
    for (const pattern of VALID_CHAT_BASE_PATTERNS) {
        if (pattern.test(baseModel)) {
            // Dated snapshots (e.g. gpt-4o-2024-11-20) are valid; base names may be deprecated
            return {valid: true};
        }
    }
    
    // Check known valid base models
    const knownValidBases = [
        'gpt-5.2-pro', 'gpt-5.2', 'gpt-5.1', 'gpt-5', 'gpt-5-mini', 'gpt-5-nano',
        'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano',
        'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo',
        'o3', 'o3-pro', 'o3-mini', 'o4-mini', 'o1', 'o1-pro'
    ];
    
    if (knownValidBases.includes(baseModel.toLowerCase())) {
        return {valid: true};
    }
    
    // Date suffix but base not in known list
    if (/-\d{4}-\d{2}-\d{2}/.test(trimmed)) {
        return {
            valid: false,
            error: `Unrecognized dated model "${trimmed}"`,
            suggestion: 'Use a supported chat model (e.g. gpt-5.2-pro, gpt-4.1, or a dated snapshot)'
        };
    }
    
    // Fallback: allow if it starts with gpt- or o
    if (/^(gpt-|o)/i.test(trimmed)) {
        return {valid: true, warning: `Model "${trimmed}" is not explicitly validated`};
    }
    
    return {valid: false, error: `Unknown model format: "${trimmed}"`};
}

/**
 * Validates provider/model combination and shows error if invalid (synchronous client-side)
 * @param {string} agentPrefix - Agent prefix (e.g., 'rankagent')
 * @param {string} provider - Provider name
 * @param {string} modelId - Model identifier
 * @returns {boolean} - true if valid, false if invalid
 */
function validateProviderModelCombination(agentPrefix, provider, modelId) {
    if (!modelId || !modelId.trim()) {
        // Empty model is valid (will use fallback)
        clearProviderModelError(agentPrefix);
        return true;
    }
    
    const trimmed = modelId.trim();
    const normalizedProvider = (provider || getDefaultProvider()).toString().trim().toLowerCase();
    
    let isValid = true;
    let errorMessage = '';
    let suggestion = null;
    
    if (normalizedProvider === 'openai') {
        // First check pattern match
        if (!isModelAllowedForProvider('openai', trimmed)) {
            isValid = false;
            errorMessage = `Invalid model for OpenAI provider. Model "${trimmed}" does not match OpenAI patterns (gpt-*, o*, etc.).`;
        } else {
            // Then validate chat compatibility
            const validation = isValidOpenAIChatModel(trimmed);
            if (!validation.valid) {
                isValid = false;
                errorMessage = validation.error || `Model "${trimmed}" is not a valid chat completion model`;
                suggestion = validation.suggestion;
            }
        }
    } else if (normalizedProvider === 'codex') {
        if (!isModelAllowedForProvider('codex', trimmed)) {
            isValid = false;
            errorMessage = `Invalid model for Codex subscription. Model "${trimmed}" must be a Codex-available OpenAI model.`;
        }
    } else if (normalizedProvider === 'anthropic') {
        if (!isModelAllowedForProvider('anthropic', trimmed)) {
            isValid = false;
            errorMessage = `Invalid model for Anthropic provider. Model "${trimmed}" does not match Anthropic patterns (claude-*).`;
        }
    } else if (normalizedProvider === 'lmstudio') {
        // For LMStudio, reject commercial provider models
        if (providerModelGuards.openai && providerModelGuards.openai.test(trimmed)) {
            isValid = false;
            errorMessage = `Invalid model for LMStudio provider. Model "${trimmed}" appears to be an OpenAI model. Use an LMStudio model instead.`;
        } else if (providerModelGuards.anthropic && providerModelGuards.anthropic.test(trimmed)) {
            isValid = false;
            errorMessage = `Invalid model for LMStudio provider. Model "${trimmed}" appears to be an Anthropic model. Use an LMStudio model instead.`;
        }
    }
    
    if (!isValid) {
        const fullMessage = suggestion ? `${errorMessage} ${suggestion}` : errorMessage;
        showProviderModelError(agentPrefix, fullMessage);
    } else {
        clearProviderModelError(agentPrefix);
        // Optionally do async server-side validation for extra confidence (non-blocking)
        validateProviderModelCombinationAsync(agentPrefix, normalizedProvider, trimmed).catch(e => {
            console.warn('Async model validation failed:', e);
        });
    }
    
    return isValid;
}

/**
 * Async server-side validation (non-blocking, for extra confidence)
 */
async function validateProviderModelCombinationAsync(agentPrefix, provider, modelId) {
    if (provider !== 'openai') return; // Only validate OpenAI models server-side for now
    
    try {
        const response = await fetch('/api/validate-model', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({provider: provider, model: modelId})
        });
        const result = await response.json();
        if (!result.valid) {
            const errorMsg = result.suggestion 
                ? `${result.error} ${result.suggestion}` 
                : result.error;
            showProviderModelError(agentPrefix, errorMsg);
        }
    } catch (e) {
        // Silently fail - client-side validation is primary
        console.debug('Server-side model validation failed:', e);
    }
}

/**
 * Shows error message for invalid provider/model combination
 */
function showProviderModelError(agentPrefix, message) {
    // Find the model input container
    const config = getAgentConfig(agentPrefix);
    if (!config) return;
    
    const provider = getAgentProvider(agentPrefix) || getDefaultProvider();
    let modelContainer = null;
    
    if (provider === 'lmstudio') {
        modelContainer = document.getElementById(`${agentPrefix}-model-2`) || document.getElementById(`${agentPrefix}-model`);
    } else {
        modelContainer = document.getElementById(`${agentPrefix}-model-${provider}`);
    }
    
    if (!modelContainer) return;
    
    // Find or create error element
    let errorEl = document.getElementById(`${agentPrefix}-model-error`);
    if (!errorEl) {
        errorEl = document.createElement('p');
        errorEl.id = `${agentPrefix}-model-error`;
        errorEl.className = 'text-xs text-red-500 dark:text-red-400 mt-1';
        // Insert after the model input's parent container
        const parent = modelContainer.closest('[data-agent-prefix]') || modelContainer.parentElement;
        if (parent) {
            parent.appendChild(errorEl);
        }
    }
    
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
    
    // Add error styling to the input
    modelContainer.classList.add('border-red-500', 'dark:border-red-500');
    // Remove any gray border classes
    modelContainer.classList.remove('border-gray-300', 'border-gray-600', 'border-gray-700', 'dark:border-gray-300', 'dark:border-gray-600', 'dark:border-gray-700');
}

/**
 * Clears error message for provider/model combination
 */
function clearProviderModelError(agentPrefix) {
    const errorEl = document.getElementById(`${agentPrefix}-model-error`);
    if (errorEl) {
        errorEl.classList.add('hidden');
        errorEl.textContent = '';
    }
    
    // Remove error styling from inputs
    const provider = getAgentProvider(agentPrefix) || getDefaultProvider();
    let modelContainer = null;
    
    if (provider === 'lmstudio') {
        modelContainer = document.getElementById(`${agentPrefix}-model-2`) || document.getElementById(`${agentPrefix}-model`);
    } else {
        modelContainer = document.getElementById(`${agentPrefix}-model-${provider}`);
    }
    
    if (modelContainer) {
        modelContainer.classList.remove('border-red-500', 'dark:border-red-500');
        // Restore appropriate gray border classes based on input type
        // Check if it's a dark-themed input (has bg-panel-0 or similar)
        const isDarkInput = modelContainer.classList.contains('bg-panel-0') ||
                           modelContainer.closest('.bg-panel-0');
        if (isDarkInput) {
            modelContainer.classList.add('border-gray-700');
        } else {
            modelContainer.classList.add('border-gray-300', 'dark:border-gray-600');
        }
    }
}

// Curated model catalogs for commercial providers - kept client-side for quick selection
const defaultCommercialModelCatalog = {
    openai: [
        'gpt-4.1',
        'gpt-4.1-mini',
        'gpt-4.1-nano',
        'gpt-4.1-turbo',
        'gpt-4.1-realtime-preview',
        'gpt-4o',
        'gpt-4o-mini',
        'gpt-4o-realtime-preview-2024-12-17',
        'gpt-4o-mini-tts',
        'gpt-4o-mini-transcribe',
        'o4',
        'o4-mini',
        'o3-mini',
        'o3-mini-high',
        'o3-mini-low',
        'o1',
        'o1-mini',
        'o1-preview',
        'o1-lite'
    ],
    anthropic: [
        'claude-3.7-sonnet-latest',
        'claude-3.7-sonnet-20250219',
        'claude-3.7-haiku-latest',
        'claude-3.7-haiku-20250219',
        'claude-3.6-sonnet-20250108',
        'claude-3.6-haiku-20250108',
        'claude-3.5-sonnet-20241022',
        'claude-3.5-haiku-20241022',
        'claude-3.5-sonnet-latest',
        'claude-3.5-haiku-latest',
        'claude-3-opus-20240229',
        'claude-3-sonnet-20240229',
        'claude-3-haiku-20240307',
        'claude-2.1',
        'claude-2.0',
        'claude-instant-1.2'
    ]
};
// Cached catalog is only trusted for this long. The server re-renders the live
// catalog inline on every page load (window.initialCommercialModelCatalog) and
// refreshes the persisted file daily, so a stale localStorage copy must expire —
// otherwise newly-added models never surface until the user clears storage.
const PROVIDER_CATALOG_CACHE_TTL_MS = 6 * 60 * 60 * 1000; // 6 hours

function getCachedProviderCatalog() {
    if (typeof localStorage === 'undefined') return null;
    try {
        const cached = localStorage.getItem('providerModelCatalog');
        if (!cached) return null;
        const parsed = JSON.parse(cached);
        // Honor the stored TTL: ignore (and clear) a cache older than the window.
        if (parsed && typeof parsed.updatedAt === 'number' &&
            Date.now() - parsed.updatedAt > PROVIDER_CATALOG_CACHE_TTL_MS) {
            localStorage.removeItem('providerModelCatalog');
            return null;
        }
        if (parsed && typeof parsed.data === 'object') {
            return parsed.data;
        }
    } catch (error) {
        console.warn('Failed to parse cached provider catalog', error);
    }
    return null;
}

function cacheProviderCatalog(catalog) {
    if (!catalog || typeof localStorage === 'undefined') return;
    try {
        localStorage.setItem('providerModelCatalog', JSON.stringify({
            data: catalog,
            updatedAt: Date.now()
        }));
    } catch (error) {
        console.warn('Failed to store provider catalog', error);
    }
}

async function refreshCommercialModelCatalog() {
    // Skip network fetch if loadEnabledProviders() already populated the catalog this session.
    if (_workflowProviderOptionsLoaded) {
        return;
    }
    try {
        const response = await fetch('/api/provider-model-catalog');
        if (response.ok) {
            const data = await response.json();
            if (data.catalog) {
                commercialModelCatalog = data.catalog;
                cacheProviderCatalog(data.catalog);
            }
        }
    } catch (error) {
        console.warn('Unable to refresh provider model catalog', error);
    }
}

const cachedProviderCatalog = getCachedProviderCatalog();
// Prefer the server-rendered catalog (always current as of this page load) over the
// localStorage cache, so freshly-added models appear immediately. The cache is only a
// fallback for when the server didn't inline a catalog. Empty lists fall through too.
function _catalogHasModels(c) {
    return !!c && ((Array.isArray(c.openai) && c.openai.length > 0) ||
                   (Array.isArray(c.anthropic) && c.anthropic.length > 0));
}
let commercialModelCatalog =
    (_catalogHasModels(window.initialCommercialModelCatalog) && window.initialCommercialModelCatalog) ||
    (_catalogHasModels(cachedProviderCatalog) && cachedProviderCatalog) ||
    window.initialCommercialModelCatalog ||
    defaultCommercialModelCatalog;
// Keep the cache in sync with the fresh server catalog we just chose.
if (_catalogHasModels(window.initialCommercialModelCatalog)) {
    cacheProviderCatalog(window.initialCommercialModelCatalog);
}

// ============================================================================
// UNIFIED AGENT CONFIGURATION SYSTEM
// ============================================================================
// Single source of truth for all agent provider/model configuration
// Eliminates code duplication across main agents, sub-agents, and QA agents

/**
 * Agent configuration registry
 * Defines all agents with their properties for unified handling
 */
const AGENT_CONFIG = {
    // Main agents
    rankagent: {
        prefix: 'rankagent',
        providerKey: 'RankAgent_provider',
        modelKey: 'RankAgent',
        temperatureKey: 'RankAgent_temperature',
        topPKey: 'RankAgent_top_p',
        name: 'RankAgent',
        isSubAgent: false,
        isQA: false,
        hasFallback: false
    },
    extractagent: {
        prefix: 'extractagent',
        providerKey: 'ExtractAgent_provider',
        modelKey: 'ExtractAgent',
        temperatureKey: 'ExtractAgent_temperature',
        topPKey: 'ExtractAgent_top_p',
        name: 'ExtractAgent',
        isSubAgent: false,
        isQA: false,
        hasFallback: true  // Used as fallback for sub-agents
    },
    sigmaagent: {
        prefix: 'sigmaagent',
        providerKey: 'SigmaAgent_provider',
        modelKey: 'SigmaAgent',
        temperatureKey: 'SigmaAgent_temperature',
        topPKey: 'SigmaAgent_top_p',
        name: 'SigmaAgent',
        isSubAgent: false,
        isQA: false,
        hasFallback: false
    },
    // Extract sub-agents
    cmdlineextract: {
        prefix: 'cmdlineextract',
        providerKey: 'CmdlineExtract_provider',
        modelKey: 'CmdlineExtract_model',
        temperatureKey: 'CmdlineExtract_temperature',
        topPKey: 'CmdlineExtract_top_p',
        name: 'CmdlineExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
    proctreeextract: {
        prefix: 'proctreeextract',
        providerKey: 'ProcTreeExtract_provider',
        modelKey: 'ProcTreeExtract_model',
        temperatureKey: 'ProcTreeExtract_temperature',
        topPKey: 'ProcTreeExtract_top_p',
        name: 'ProcTreeExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
    huntqueriesextract: {
        prefix: 'huntqueriesextract',
        providerKey: 'HuntQueriesExtract_provider',
        modelKey: 'HuntQueriesExtract_model',
        temperatureKey: 'HuntQueriesExtract_temperature',
        topPKey: 'HuntQueriesExtract_top_p',
        name: 'HuntQueriesExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
    registryextract: {
        prefix: 'registryextract',
        providerKey: 'RegistryExtract_provider',
        modelKey: 'RegistryExtract_model',
        temperatureKey: 'RegistryExtract_temperature',
        topPKey: 'RegistryExtract_top_p',
        name: 'RegistryExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
    servicesextract: {
        prefix: 'servicesextract',
        providerKey: 'ServicesExtract_provider',
        modelKey: 'ServicesExtract_model',
        temperatureKey: 'ServicesExtract_temperature',
        topPKey: 'ServicesExtract_top_p',
        name: 'ServicesExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
    scheduledtasksextract: {
        prefix: 'scheduledtasksextract',
        providerKey: 'ScheduledTasksExtract_provider',
        modelKey: 'ScheduledTasksExtract_model',
        temperatureKey: 'ScheduledTasksExtract_temperature',
        topPKey: 'ScheduledTasksExtract_top_p',
        name: 'ScheduledTasksExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
    networkindicatorextract: {
        prefix: 'networkindicatorextract',
        providerKey: 'NetworkIndicatorExtract_provider',
        modelKey: 'NetworkIndicatorExtract_model',
        temperatureKey: 'NetworkIndicatorExtract_temperature',
        topPKey: 'NetworkIndicatorExtract_top_p',
        name: 'NetworkIndicatorExtract',
        isSubAgent: true,
        isQA: false,
        hasFallback: true,
        fallbackAgent: 'extractagent'
    },
};

/**
 * Get agent configuration by prefix
 */
function getAgentConfig(agentPrefix) {
    return AGENT_CONFIG[agentPrefix] || null;
}

/**
 * Get all agent configs matching criteria
 */
function getAgentConfigs(filter = {}) {
    return Object.values(AGENT_CONFIG).filter(config => {
        if (filter.isSubAgent !== undefined && config.isSubAgent !== filter.isSubAgent) return false;
        if (filter.isQA !== undefined && config.isQA !== filter.isQA) return false;
        if (filter.hasFallback !== undefined && config.hasFallback !== filter.hasFallback) return false;
        return true;
    });
}

const AGENT_UI_DISPLAY_LABELS = {
    rankagent: 'Rank Agent',
    extractagent: 'Extract Agents',
    sigmaagent: 'SIGMA Generator Agent',
    cmdlineextract: 'CmdlineExtract',
    proctreeextract: 'ProcTreeExtract',
    huntqueriesextract: 'HuntQueriesExtract',
    registryextract: 'RegistryExtract',
    servicesextract: 'ServicesExtract',
    scheduledtasksextract: 'ScheduledTasksExtract',
    networkindicatorextract: 'NetworkIndicatorExtract',
};

function getAgentUIDisplayLabel(agentPrefix) {
    if (AGENT_UI_DISPLAY_LABELS[agentPrefix]) {
        return AGENT_UI_DISPLAY_LABELS[agentPrefix];
    }
    const config = getAgentConfig(agentPrefix);
    if (config?.name) {
        return config.name.replace(/([a-z])([A-Z])/g, '$1 $2');
    }
    return agentPrefix.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getProviderLabel(provider) {
    const normalized = (provider || '').toString().trim().toLowerCase();
    return allProviderOptions.find(option => option.value === normalized)?.label || normalized || 'default provider';
}

function getConfiguredValue(agentModelsData, key) {
    const value = agentModelsData?.[key];
    return value === undefined || value === null ? '' : String(value).trim();
}

function getInheritedSubAgentModelInfo(config, agentModelsData = currentConfig?.agent_models || agentModels || {}) {
    if (!config?.isSubAgent || !config.fallbackAgent) return null;

    const fallbackConfig = getAgentConfig(config.fallbackAgent);
    if (!fallbackConfig) return null;

    const explicitProvider = getConfiguredValue(agentModelsData, config.providerKey);
    const explicitModel = getConfiguredValue(agentModelsData, config.modelKey);
    const inheritedProvider = getConfiguredValue(agentModelsData, fallbackConfig.providerKey) || getDefaultProvider();
    const inheritedModel = getConfiguredValue(agentModelsData, fallbackConfig.modelKey);

    if (explicitProvider && explicitModel) return null;

    return {
        missingProvider: !explicitProvider,
        missingModel: !explicitModel,
        inheritedProvider,
        inheritedModel
    };
}

function updateSubAgentInheritanceHints() {
    const agentModelsData = currentConfig?.agent_models || agentModels || {};
    getAgentConfigs({ isSubAgent: true, hasFallback: true }).forEach(config => {
        const providerSelect = document.getElementById(`${config.prefix}-provider`);
        if (!providerSelect) return;

        const wrapper = providerSelect.closest('.space-y-2') || providerSelect.parentElement;
        if (!wrapper) return;

        let hint = document.getElementById(`${config.prefix}-inheritance-hint`);
        if (!hint) {
            hint = document.createElement('p');
            hint.id = `${config.prefix}-inheritance-hint`;
            hint.className = 'text-[10px] text-gray-500 dark:text-gray-400';
            const grid = wrapper.querySelector('.grid.grid-cols-2') || providerSelect.closest('.grid');
            if (grid && grid.parentElement === wrapper) {
                grid.insertAdjacentElement('afterend', hint);
            } else {
                wrapper.appendChild(hint);
            }
        }

        const inherited = getInheritedSubAgentModelInfo(config, agentModelsData);
        if (!inherited) {
            hint.textContent = '';
            hint.classList.add('hidden');
            return;
        }

        const inheritedParts = [];
        if (inherited.missingProvider) {
            inheritedParts.push(`provider ${getProviderLabel(inherited.inheritedProvider)}`);
        }
        if (inherited.missingModel) {
            inheritedParts.push(`model ${inherited.inheritedModel || 'the Extract Agents default'}`);
        }
        hint.textContent = `Blank fields inherit ${inheritedParts.join(' and ')} from Extract Agents.`;
        hint.classList.remove('hidden');
    });
}

function getWorkflowConfigLabelText(el) {
    if (!el) return null;
    if (el.id) {
        const explicitLabel = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (explicitLabel) {
            return (explicitLabel.textContent || '').replace(/\s+/g, ' ').trim();
        }
    }
    const wrappingLabel = el.closest('label');
    if (wrappingLabel) {
        return (wrappingLabel.textContent || '').replace(/\s+/g, ' ').trim();
    }
    const ariaLabel = el.getAttribute('aria-label');
    return ariaLabel ? ariaLabel.trim() : null;
}

function normalizeWorkflowConfigControlBindings() {
    const form = document.getElementById('workflowConfigForm');
    if (!form) return;

    const setAttr = (el, attr, value) => {
        if (!el || value === undefined || value === null || value === '') return;
        el.setAttribute(attr, value);
    };

    Object.values(AGENT_CONFIG).forEach(config => {
        const labelBase = getAgentUIDisplayLabel(config.prefix);
        const providerEl = document.getElementById(`${config.prefix}-provider`);
        if (providerEl) {
            setAttr(providerEl, 'name', `agent_models[${config.providerKey}]`);
            setAttr(providerEl, 'data-config-key', config.providerKey);
            setAttr(providerEl, 'data-config-control-type', 'provider');
            setAttr(providerEl, 'aria-label', `${labelBase} Model Provider`);
        }

        [
            document.getElementById(`${config.prefix}-model`),
            document.getElementById(`${config.prefix}-model-2`),
            document.getElementById(`${config.prefix}-model-openai`),
            document.getElementById(`${config.prefix}-model-anthropic`)
        ].filter(Boolean).forEach(el => {
            setAttr(el, 'name', `agent_models[${config.modelKey}]`);
            setAttr(el, 'data-config-key', config.modelKey);
            setAttr(el, 'data-config-control-type', 'model');
            setAttr(el, 'aria-label', `${labelBase} Model`);
        });

        if (config.temperatureKey) {
            const tempEl = document.getElementById(`${config.prefix}-temperature`);
            if (tempEl) {
                setAttr(tempEl, 'data-config-key', config.temperatureKey);
                setAttr(tempEl, 'data-config-control-type', 'temperature');
                setAttr(tempEl, 'aria-label', `${labelBase} Temperature`);
            }
        }
        if (config.topPKey) {
            const topPEl = document.getElementById(`${config.prefix}-top-p`);
            if (topPEl) {
                setAttr(topPEl, 'data-config-key', config.topPKey);
                setAttr(topPEl, 'data-config-control-type', 'top_p');
                setAttr(topPEl, 'aria-label', `${labelBase} Top_P`);
            }
        }
    });

    const directBindings = {
        junkFilterThreshold: { key: 'junk_filter_threshold', label: 'Junk Filter Threshold' },
        rankingThreshold: { key: 'ranking_threshold', label: 'Ranking Threshold' },
        similarityThreshold: { key: 'similarity_threshold', label: 'Similarity Threshold' },
        'rank-agent-enabled': { key: 'rank_agent_enabled', label: 'Rank Agent Enabled' },
        'sigma-fallback-enabled': { key: 'sigma_fallback_enabled', label: 'Use Full Article Content (Minus Junk)' },
        'cmdline-attention-preprocessor-enabled': { key: 'cmdline_attention_preprocessor_enabled', label: 'Attention Preprocessor' },
        'proctree-attention-preprocessor-enabled': { key: 'proc_tree_attention_preprocessor_enabled', label: 'Attention Preprocessor' },
    };
    Object.entries(directBindings).forEach(([id, meta]) => {
        const el = document.getElementById(id);
        if (!el) return;
        setAttr(el, 'data-config-key', meta.key);
        setAttr(el, 'aria-label', meta.label);
        if (meta.name) setAttr(el, 'name', meta.name);
    });

    [
        { id: 'toggle-cmdlineextract-enabled', agent: 'CmdlineExtract' },
        { id: 'toggle-proctreeextract-enabled', agent: 'ProcTreeExtract' },
        { id: 'toggle-huntqueriesextract-enabled', agent: 'HuntQueriesExtract' },
        { id: 'toggle-registryextract-enabled', agent: 'RegistryExtract' },
        { id: 'toggle-servicesextract-enabled', agent: 'ServicesExtract' },
        { id: 'toggle-scheduledtasksextract-enabled', agent: 'ScheduledTasksExtract' },
        { id: 'toggle-networkindicatorextract-enabled', agent: 'NetworkIndicatorExtract' }
    ].forEach(item => {
        const el = document.getElementById(item.id);
        if (!el) return;
        setAttr(el, 'name', `extract_subagent_enabled[${item.agent}]`);
        setAttr(el, 'data-derived-persist-key', 'agent_prompts.ExtractAgentSettings.disabled_agents');
        setAttr(el, 'data-derived-binding-kind', 'inverse-disabled-list');
        setAttr(el, 'data-derived-agent', item.agent);
        setAttr(el, 'aria-label', `Enable ${item.agent}`);
    });

    form.querySelectorAll('textarea[id$="-prompt-system-2"], textarea[id$="-prompt-user-2"]').forEach(textarea => {
        const id = textarea.id || '';
        const isSystem = id.endsWith('-prompt-system-2');
        const agentId = id.replace(/-prompt-(system|user)-2$/, '');
        const promptAgentNameMap = {
            rankagent: 'RankAgent',
            extractagent: 'ExtractAgent',
            sigmaagent: 'SigmaAgent',
            osdetectionagent: 'OSDetectionAgent',
            cmdlineextract: 'CmdlineExtract',
            proctreeextract: 'ProcTreeExtract',
            huntqueriesextract: 'HuntQueriesExtract',
            registryextract: 'RegistryExtract',
            servicesextract: 'ServicesExtract',
            scheduledtasksextract: 'ScheduledTasksExtract',
            networkindicatorextract: 'NetworkIndicatorExtract',
        };
        const agentName = promptAgentNameMap[agentId] || agentId;
        setAttr(textarea, 'data-derived-persist-key', `agent_prompts.${agentName}.prompt`);
        setAttr(textarea, 'data-derived-binding-kind', isSystem ? 'prompt-system' : 'prompt-user');
        setAttr(textarea, 'aria-label', `${agentName} ${isSystem ? 'System' : 'User'} Prompt`);
    });
}

function getWorkflowConfigBindingAudit() {
    const form = document.getElementById('workflowConfigForm');
    if (!form) return { error: 'workflowConfigForm not found' };

    normalizeWorkflowConfigControlBindings();

    const controls = Array.from(form.querySelectorAll('input, select, textarea'))
        .filter(el => el.id !== 'import-preset-input')
        .map(el => {
            const type = el.tagName.toLowerCase() === 'input'
                ? ((el.getAttribute('type') || 'text').toLowerCase())
                : el.tagName.toLowerCase();
            const style = window.getComputedStyle(el);
            const visible = style.display !== 'none' && style.visibility !== 'hidden' && !el.closest('.hidden');
            const disabled = !!el.disabled;
            const name = el.getAttribute('name');
            const persistKey = el.getAttribute('data-config-key') || el.getAttribute('data-derived-persist-key') || name || null;
            return {
                id: el.id || null,
                name: name || null,
                type,
                visible,
                disabled,
                label: getWorkflowConfigLabelText(el),
                ariaLabel: el.getAttribute('aria-label') || null,
                persistKey,
                bindingKind: el.getAttribute('data-config-control-type') || el.getAttribute('data-derived-binding-kind') || null
            };
        });

    const visibleMutableControls = controls.filter(c => c.visible && !c.disabled && c.type !== 'hidden');
    const missingLabels = visibleMutableControls.filter(c => !(c.label || c.ariaLabel));
    const missingBindings = visibleMutableControls.filter(c => !c.persistKey);
    const promptPanelHeaders = Array.from(form.querySelectorAll('[data-collapsible-panel$="-prompt-panel"], [data-collapsible-panel$="-qa-prompt-panel"]'))
        .map(el => (el.textContent || '').replace(/\s+/g, ' ').trim());

    return {
        controls,
        counts: {
            totalControls: controls.length,
            visibleMutableControls: visibleMutableControls.length,
            missingLabels: missingLabels.length,
            missingBindings: missingBindings.length
        },
        missingLabels,
        missingBindings,
        promptPanelHeaders
    };
}

if (typeof window !== 'undefined') {
    window.normalizeWorkflowConfigControlBindings = normalizeWorkflowConfigControlBindings;
    window.getWorkflowConfigBindingAudit = getWorkflowConfigBindingAudit;
}

/**
 * Unified function to get agent provider value from DOM
 */
function getAgentProvider(agentPrefix) {
    const config = getAgentConfig(agentPrefix);
    if (!config) return getDefaultProvider();
    
    const providerSelect = document.getElementById(`${agentPrefix}-provider`);
    return (providerSelect?.value || getDefaultProvider()).toString().trim().toLowerCase();
}

/**
 * Unified function to get agent model value from DOM (respects provider)
 */
function getAgentModel(agentPrefix, provider = null) {
    const config = getAgentConfig(agentPrefix);
    if (!config) return null;
    
    const actualProvider = provider || getAgentProvider(agentPrefix);
    return getActiveAgentModelValue(agentPrefix, actualProvider);
}

/**
 * Unified function to set agent provider value in DOM
 */
function setAgentProvider(agentPrefix, provider) {
    const config = getAgentConfig(agentPrefix);
    if (!config) return false;
    
    const providerSelect = document.getElementById(`${agentPrefix}-provider`);
    if (!providerSelect) return false;
    
    const normalized = (provider || '').toString().trim().toLowerCase();
    if (!normalized) return false;
    
    // Ensure preset provider exists in dropdown (e.g. openai from preset when not yet in providerOptions)
    if (![...providerSelect.options].some(o => o.value === normalized)) {
        const label = allProviderOptions.find(o => o.value === normalized)?.label || normalized;
        const opt = document.createElement('option');
        opt.value = normalized;
        opt.textContent = label;
        providerSelect.appendChild(opt);
    }
    
    providerSelect.value = normalized;
    providerSelect.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}

/**
 * Unified function to set agent model value in DOM (respects provider)
 */
function setAgentModel(agentPrefix, model, provider = null) {
    const config = getAgentConfig(agentPrefix);
    if (!config) return false;
    
    const actualProvider = provider || getAgentProvider(agentPrefix);
    const val = (model || '').toString().trim();
    
    if (actualProvider === 'lmstudio') {
        const select = document.getElementById(`${agentPrefix}-model-2`) || document.getElementById(`${agentPrefix}-model`);
        if (select) {
            if (select.tagName === 'SELECT' && val && ![...select.options].some(o => o.value === val)) {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = val;
                select.appendChild(opt);
            }
            select.value = val;
            return true;
        }
    } else {
        const el = document.getElementById(`${agentPrefix}-model-${actualProvider}`);
        if (el) {
            if (el.tagName === 'SELECT' && val && ![...el.options].some(o => o.value === val)) {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = val;
                el.appendChild(opt);
            }
            el.value = val;
            return true;
        }
    }
    return false;
}

/**
 * Unified function to collect all agent provider/model values for saving
 */
function collectAllAgentConfigs(models = null) {
    const agentModelsData = models || agentModels || {};
    const collected = {};
    
    Object.values(AGENT_CONFIG).forEach(config => {
        // Get provider
        const provider = getAgentProvider(config.prefix);
        collected[config.providerKey] = provider;
        
        // Get model (respects provider)
        const model = getAgentModel(config.prefix, provider);
        // Always include model key, even if empty string (to clear fallback settings)
        // null/undefined means element not in DOM (e.g. config panel not rendered) — skip without warning
        if (model !== null && model !== undefined) {
            collected[config.modelKey] = model;
        }
        
        // Get temperature if applicable
        if (config.temperatureKey) {
            const tempInput = document.getElementById(`${config.prefix}-temperature`);
            if (tempInput) {
                const tempValue = parseFloat(tempInput.value);
                if (!isNaN(tempValue)) {
                    collected[config.temperatureKey] = tempValue;
                }
            }
        }
        
        // Get top_p if applicable
        if (config.topPKey) {
            const topPInput = document.getElementById(`${config.prefix}-top-p`);
            if (topPInput) {
                const topPValue = parseFloat(topPInput.value);
                if (!isNaN(topPValue)) {
                    collected[config.topPKey] = topPValue;
                }
            }
        }
    });
    
    return collected;
}

/**
 * Unified function to apply agent provider/model values from config
 * Sets agentModels so provider-change rebuilds (e.g. renderSubAgentCommercialInputs) see preset
 * values. Applies provider first, then refreshAllProviderBlocks, then model—so model is not
 * overwritten by rebuilds. setAgentModel adds missing <option> when preset model is not in catalog.
 */
function applyAgentConfigs(models = null) {
    const agentModelsData = models || agentModels || {};
    
    // So provider-change handlers and refreshAllProviderBlocks see preset when rebuilding inputs
    if (models && typeof models === 'object' && Object.keys(models).length > 0) {
        agentModels = { ...models };
    }
    
    // 1) Set provider, temperature, top_p only (provider change can rebuild model selects)
    Object.values(AGENT_CONFIG).forEach(config => {
        const provider = (agentModelsData[config.providerKey] || getDefaultProvider()).toString().trim().toLowerCase();
        setAgentProvider(config.prefix, provider);
        
        // Update temperature limit first based on provider
        updateTemperatureLimit(config.prefix, provider);
        
                if (config.temperatureKey && agentModelsData[config.temperatureKey] !== undefined) {
            const tempInput = document.getElementById(`${config.prefix}-temperature`);
            if (tempInput) {
                const tempValue = parseFloat(agentModelsData[config.temperatureKey]);
                if (!isNaN(tempValue)) {
                    // Clamp value to provider's max before setting
                    // LMStudio and Anthropic: max 1, OpenAI: max 2
                    const maxTemp = (provider === 'anthropic' || provider === 'lmstudio') ? 1 : 2;
                    const clampedValue = Math.min(Math.max(0, tempValue), maxTemp);
                    tempInput.value = clampedValue;
                    // If value was clamped, log a warning
                    if (tempValue !== clampedValue) {
                        console.warn(`Temperature value ${tempValue} clamped to ${clampedValue} for ${config.prefix} (provider: ${provider}, max: ${maxTemp})`);
                    }
                }
            }
        }
        if (config.topPKey && agentModelsData[config.topPKey] !== undefined) {
            const topPInput = document.getElementById(`${config.prefix}-top-p`);
            if (topPInput) topPInput.value = agentModelsData[config.topPKey];
        }
    });
    
    // 2) Refresh visibility and rebuild provider-specific blocks (can overwrite model fields)
    refreshAllProviderBlocks();
    
    // 3) Set model after rebuilds so preset provider+model are not overwritten
    Object.values(AGENT_CONFIG).forEach(config => {
        const provider = (agentModelsData[config.providerKey] || getDefaultProvider()).toString().trim().toLowerCase();
        const model = agentModelsData[config.modelKey] || '';
        if (model) setAgentModel(config.prefix, model, provider);
    });

    // 4) Update temp/top_p slider value displays
    Object.values(AGENT_CONFIG).forEach(config => {
        if (config.temperatureKey) updateThresholdDisplay(`${config.prefix}-temperature`);
        if (config.topPKey) updateThresholdDisplay(`${config.prefix}-top-p`);
    });
}

/**
 * Unified function to build provider/model selector UI for any agent
 */
function buildAgentProviderModelUI(agentPrefix, currentProvider = 'lmstudio', currentModel = '', lmstudioModels = [], options = {}) {
    const config = getAgentConfig(agentPrefix);
    if (!config) {
        console.warn(`buildAgentProviderModelUI: Unknown agent prefix: ${agentPrefix}`);
        return '';
    }
    
    const {
        showTemperature = false,
        temperatureDefault = 0.0,
        lmstudioPlaceholder = config.isSubAgent ? 'Inherit Extract Agents Model' : 'Select a model',
        sizeClass = config.isSubAgent ? 'text-xs' : 'text-sm',
        paddingClass = config.isSubAgent ? 'px-2 py-1.5' : 'px-3 py-2'
    } = options;
    
    // Build LMStudio model options
    const lmstudioOptions = lmstudioModels.map(modelId => {
        const isSelected = currentProvider === 'lmstudio' && currentModel === modelId ? 'selected' : '';
        return `<option value="${escapeHtml(modelId)}" ${isSelected}>${escapeHtml(modelId)}</option>`;
    }).join('');
    
    // Determine name attribute
    const nameAttr = `name="agent_models[${config.modelKey}]"`;
    
    // Build provider select
    const providerSelect = buildProviderSelect(agentPrefix, currentProvider);
    
    // Build LMStudio model select
    const lmstudioSelect = `
        <select id="${agentPrefix}-model${config.isSubAgent ? '' : '-2'}"
                ${nameAttr}
                data-config-key="${config.modelKey}"
                data-config-control-type="model"
                aria-label="${escapeHtml(getAgentUIDisplayLabel(agentPrefix))} Model"
                onchange="validateAgentModelOnChange('${agentPrefix}'); autoSaveModelChange()"
                class="w-full ${paddingClass} border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono ${sizeClass}">
            <option value="">${lmstudioPlaceholder}</option>
            ${lmstudioOptions}
        </select>
    `;
    
    // Build commercial provider inputs
    const openaiInput = buildCommercialProviderInput(agentPrefix, 'openai', currentProvider, currentModel);
    const codexInput = buildCommercialProviderInput(agentPrefix, 'codex', currentProvider, currentModel);
    const anthropicInput = buildCommercialProviderInput(agentPrefix, 'anthropic', currentProvider, currentModel);
    
    // Build temperature and top_p sliders on same row if needed
    const topPDefault = options.topPDefault !== undefined ? options.topPDefault : 0.9;
    const tempMax = (currentProvider === 'anthropic' || currentProvider === 'lmstudio') ? 1 : 2;
    const temperatureTopPRow = showTemperature && (config.temperatureKey || config.topPKey) ? `
        <div class="mt-3 flex gap-3">
            ${buildTempTopPSliderRow(agentPrefix, temperatureDefault, topPDefault, config.temperatureKey, config.topPKey, tempMax)}
        </div>
    ` : '';
    
    // Legacy separate inputs for backward compatibility (not used if temperatureTopPRow is set)
    const temperatureInput = '';
    const topPInput = '';
    
    return {
        providerSelect,
        lmstudioSelect,
        openaiInput,
        anthropicInput,
        temperatureTopPRow,
        html: `
            <div class="space-y-3">
                ${providerSelect}
                <div data-agent-prefix="${agentPrefix}" data-provider="lmstudio">
                    ${lmstudioSelect}
                </div>
                <div data-agent-prefix="${agentPrefix}" data-provider="openai" class="hidden">
                    ${openaiInput}
                </div>
                <div data-agent-prefix="${agentPrefix}" data-provider="codex" class="hidden">
                    ${codexInput}
                </div>
                <div data-agent-prefix="${agentPrefix}" data-provider="anthropic" class="hidden">
                    ${anthropicInput}
                </div>
                ${temperatureTopPRow}
            </div>
        `
    };
}

function getCommercialProviderModels(provider) {
    const catalog = commercialModelCatalog[provider];
    if (!Array.isArray(catalog)) {
        return null;
    }
    const uniqueModels = [...new Set(catalog.map(model => model.trim()).filter(Boolean))];
    return uniqueModels.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

function buildCommercialProviderInput(agentPrefix, provider, currentProvider, currentModel) {
    const placeholder = provider === 'openai'
        ? 'Select an OpenAI model'
        : provider === 'codex'
            ? 'Select a Codex model'
            : 'Select a Claude model';
    const baseClass = 'w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs';
    const fallbackValue = providerDefaults[provider] || '';
    const catalog = getCommercialProviderModels(provider);
    const eligibleCurrentModel = (currentProvider === provider && currentModel &&
        (provider === 'codex' && catalog ? catalog.includes(currentModel) : isModelAllowedForProvider(provider, currentModel)))
        ? currentModel
        : '';
    const selectedModel = eligibleCurrentModel || fallbackValue || '';
    const elementId = `${agentPrefix}-model-${provider}`;

    // Determine the name attribute for form submission using unified AGENT_CONFIG
    const config = getAgentConfig(agentPrefix);
    const nameAttr = config ? `name="agent_models[${config.modelKey}]"` : '';
    const dataKeyAttr = config ? `data-config-key="${config.modelKey}" data-config-control-type="model"` : '';
    const ariaLabel = `${escapeHtml(getAgentUIDisplayLabel(agentPrefix))} Model`;

    if (!catalog || catalog.length === 0) {
        return `
            <input type="text"
                   id="${elementId}"
                   ${nameAttr}
                   ${dataKeyAttr}
                   aria-label="${ariaLabel}"
                   class="${baseClass}"
                   value="${escapeHtml(eligibleCurrentModel || '')}"
                   placeholder="${provider === 'openai' ? 'gpt-4o-mini' : provider === 'codex' ? 'gpt-5.6-luna' : 'claude-sonnet-4-5'}"
                   oninput="validateAgentModelOnChange('${agentPrefix}'); autoSaveModelChange()"
                   onchange="validateAgentModelOnChange('${agentPrefix}'); autoSaveModelChange()">
        `;
    }

    const curatedSet = new Set(catalog);
    const extraModels = new Set();
    if (eligibleCurrentModel && !curatedSet.has(eligibleCurrentModel)) {
        curatedSet.add(eligibleCurrentModel);
        extraModels.add(eligibleCurrentModel);
    }
    if (fallbackValue && !curatedSet.has(fallbackValue)) {
        curatedSet.add(fallbackValue);
    }
    const sortedOptions = Array.from(curatedSet).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
    const options = sortedOptions.map(modelId => {
        const isSelected = selectedModel === modelId ? 'selected' : '';
        const isCurated = catalog.includes(modelId);
        const label = (isCurated || !extraModels.has(modelId)) ? modelId : `${modelId} (saved)`;
        return `<option value="${escapeHtml(modelId)}" ${isSelected}>${escapeHtml(label)}</option>`;
    }).join('');
    const placeholderSelected = selectedModel ? '' : 'selected';

    return `
        <select id="${elementId}"
                ${nameAttr}
                ${dataKeyAttr}
                aria-label="${ariaLabel}"
                onchange="validateAgentModelOnChange('${agentPrefix}'); autoSaveModelChange()"
                class="${baseClass}">
            <option value="" ${placeholderSelected}>${placeholder}</option>
            ${options}
        </select>
    `;
}

function buildProviderSelect(agentId, currentProvider) {
    const options = providerOptions.map(opt => {
        const selected = opt.value === (currentProvider || getDefaultProvider()) ? 'selected' : '';
        return `<option value="${escapeHtml(opt.value)}" ${selected}>${escapeHtml(opt.label)}</option>`;
    }).join('');

    const config = getAgentConfig(agentId);
    const nameAttr = config ? `name="agent_models[${config.providerKey}]"` : '';
    const dataKeyAttr = config ? `data-config-key="${config.providerKey}" data-config-control-type="provider"` : '';
    const ariaLabel = `${escapeHtml(getAgentUIDisplayLabel(agentId))} Model Provider`;

    return `
        <select id="${agentId}-provider"
                ${nameAttr}
                ${dataKeyAttr}
                aria-label="${ariaLabel}"
                onchange="onAgentProviderChange('${agentId}')"
                class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white text-xs">
            ${options}
        </select>
    `;
}

function updateAgentProviderVisibility(agentPrefix, provider) {
    const normalized = (provider || getDefaultProvider()).toString().trim().toLowerCase();
    const groups = document.querySelectorAll(`[data-agent-prefix="${agentPrefix}"]`);
    groups.forEach(group => {
        if (!group.dataset.provider) return;
        const groupProvider = group.dataset.provider.toString().trim().toLowerCase();
        if (groupProvider === normalized) {
            group.classList.remove('hidden');
            group.style.display = '';
        } else {
            group.classList.add('hidden');
            group.style.display = 'none';
        }
    });
}

function getActiveAgentModelValue(agentPrefix, provider) {
    // Handle LMStudio select variants (-model-2 is the current ID, plain -model is legacy)
    if (provider === 'lmstudio') {
        const lmstudioSelect = document.getElementById(`${agentPrefix}-model-2`) || document.getElementById(`${agentPrefix}-model`);
        if (!lmstudioSelect) return null;
        const value = lmstudioSelect.value?.trim() || '';
        return value;
    }
    const input = document.getElementById(`${agentPrefix}-model-${provider}`);
    if (!input) return null;
    const value = input.value?.trim() || '';
    // Return empty string if no value, null only if element doesn't exist
    return value;
}

let isLoadingLMStudioModels = false; // Guard to prevent multiple simultaneous loads
let _lmStudioModelsFetchedAt = 0;    // Timestamp of last successful fetch
let _lmStudioModelsFetchCache = null; // Result of last fetch (non-null after first fetch)
const LM_STUDIO_REFETCH_TTL = 15000; // Reuse result within 15s to avoid back-to-back probes

async function loadLMStudioModels() {
    // Prevent multiple simultaneous calls
    if (isLoadingLMStudioModels) {
        console.log('loadLMStudioModels already in progress, skipping duplicate call');
        return;
    }

    isLoadingLMStudioModels = true;
    try {
        let data;
        if (_cachedLMStudioModels !== undefined) {
            // Consume the cache populated by loadEnabledProviders() to avoid a redundant request.
            data = { success: (_cachedLMStudioModels !== null && _cachedLMStudioModels.length > 0), models: _cachedLMStudioModels || [] };
            _cachedLMStudioModels = undefined; // consume; next call fetches fresh
            _lmStudioModelsFetchedAt = Date.now();
            _lmStudioModelsFetchCache = data;
        } else if (_lmStudioModelsFetchCache !== null && (Date.now() - _lmStudioModelsFetchedAt) < LM_STUDIO_REFETCH_TTL) {
            // Reuse recent result to avoid back-to-back 5s LM Studio probes (e.g. repeated loadConfig calls)
            data = _lmStudioModelsFetchCache;
        } else {
            const response = await fetch('/api/lmstudio-models');
            data = await response.json();
            _lmStudioModelsFetchedAt = Date.now();
            _lmStudioModelsFetchCache = data;
        }
        
        if (data.success && data.models && data.models.length > 0) {
            const agents = ['RankAgent', 'OSDetectionAgent', 'ExtractAgent', 'SigmaAgent'];
            
            agents.forEach(agentName => {
                const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
                
                // Skip OSDetectionAgent (embedding-based, no LLM model select)
                if (agentName === 'OSDetectionAgent') {
                    return;
                }
                
                // Check for both -model-2 (current) and -model (legacy) variants
                const select = document.getElementById(`${agentId}-model-2`) || document.getElementById(`${agentId}-model`);
                if (!select) return;
                
                // Get current model from DOM first (preserves unsaved user selection), then fallback to config
                const currentModelFromDOM = select.value || '';
                const currentModelFromConfig = agentModels[agentName] || '';
                const currentModel = currentModelFromDOM || currentModelFromConfig;
                
                // Clear existing options except the placeholder
                const placeholderText = select.querySelector('option[value=""]')?.textContent || '-- Select model --';
                select.innerHTML = `<option value="">${placeholderText}</option>`;
                
                // Sort models alphabetically
                const sortedModels = [...data.models].sort();
                
                // Add all available models
                sortedModels.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    if (model === currentModel) {
                        option.selected = true;
                    }
                    select.appendChild(option);
                });
                
                // If current model is not in the list, add it as an option
                if (currentModel && !data.models.includes(currentModel)) {
                    const option = document.createElement('option');
                    option.value = currentModel;
                    option.textContent = `${currentModel} (not available)`;
                    option.selected = true;
                    option.style.color = 'orange';
                    select.appendChild(option);
                }
            });
        } else {
            // Show error message -- guard: agentModelsContainer absent on subpages
            const container = document.getElementById('agentModelsContainer');
            if (!container) return;
            container.innerHTML = `
                <div class="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4 border border-yellow-200 dark:border-yellow-700">
                    <p class="text-sm text-yellow-800 dark:text-yellow-300">
                        ⚠️ Could not load LMStudio models: ${data.message || 'Unknown error'}
                    </p>
                    <p class="text-xs text-amber-400 dark:text-yellow-400 mt-2">
                        Make sure LMStudio is running and accessible at the configured URL.
                    </p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading LMStudio models:', error);
        const container = document.getElementById('agentModelsContainer');
        if (!container) return;
        container.innerHTML = `
            <div class="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 border border-red-200 dark:border-red-700">
                <p class="text-sm text-red-800 dark:text-red-300">
                    ❌ Error loading LMStudio models: ${error.message}
                </p>
            </div>
        `;
    } finally {
        isLoadingLMStudioModels = false;
    }

}

// Generate providerSelections from unified AGENT_CONFIG
const providerSelections = Object.values(AGENT_CONFIG).map(config => ({
    prefix: config.prefix,
    key: config.providerKey,
    modelKey: config.modelKey
}));

function applyProviderSelections(models) {
    const activeModels = models || agentModels || {};
    // Update global agentModels to ensure renderSubAgentCommercialInputs has access to latest values
    agentModels = activeModels;
    let providerAdjusted = false;

    Object.values(AGENT_CONFIG).forEach(config => {
        const storedProvider = (activeModels && activeModels[config.providerKey]) || '';
        const storedModel = config.modelKey ? activeModels?.[config.modelKey] : null;
        const inferredProvider = inferProviderFromModel(storedModel);

        let provider = storedProvider || inferredProvider || getDefaultProvider();
        if (storedProvider === 'lmstudio' && inferredProvider && inferredProvider !== 'lmstudio') {
            provider = inferredProvider;
        }
        if (!storedProvider && inferredProvider && inferredProvider !== 'lmstudio') {
            providerAdjusted = true;
        }

        const select = document.getElementById(`${config.prefix}-provider`);
        const prevProvider = select?.value?.toString().trim().toLowerCase() || getDefaultProvider();
        
        if (select) {
            select.value = provider;
        }
        
        // If provider changed, clear model fields that don't match new provider
        if (prevProvider !== provider) {
            const modelSelect = document.getElementById(`${config.prefix}-model-2`) || document.getElementById(`${config.prefix}-model`);
            const modelInputs = [
                document.getElementById(`${config.prefix}-model-openai`),
                document.getElementById(`${config.prefix}-model-anthropic`)
            ].filter(Boolean);
            
            if (provider === 'lmstudio') {
                // Clear commercial provider inputs
                modelInputs.forEach(input => input.value = '');
            } else {
                // Clear LMStudio model dropdown if switching away from LMStudio
                if (modelSelect) {
                    const currentValue = modelSelect.value;
                    // Only clear if value looks like LMStudio model
                    if (currentValue && !currentValue.match(/^(gpt|o[13]|text-|davinci|curie|babbage|ada|whisper|omni|turbo|claude)/i)) {
                        modelSelect.value = '';
                    }
                }
            }
        }
        
        updateAgentProviderVisibility(config.prefix, provider);
        if (typeof window.renderSubAgentCommercialInputs === 'function') {
            window.renderSubAgentCommercialInputs(config.prefix);
        }
        
        // Ensure model value is set for the selected provider
        if (storedModel) {
            if (provider === 'lmstudio') {
                // For LMStudio, set the model dropdown value
                const modelSelect = document.getElementById(`${config.prefix}-model-2`) || document.getElementById(`${config.prefix}-model`);
                if (modelSelect && modelSelect.value !== storedModel) {
                    modelSelect.value = storedModel;
                }
            } else {
                // For commercial providers, set the model input value
                const modelInput = document.getElementById(`${config.prefix}-model-${provider}`);
                if (modelInput && modelInput.value !== storedModel) {
                    modelInput.value = storedModel;
                }
            }
        }
        
        // Set temperature if applicable
        if (config.temperatureKey && activeModels[config.temperatureKey] !== undefined) {
            const tempInput = document.getElementById(`${config.prefix}-temperature`);
            if (tempInput) {
                tempInput.value = activeModels[config.temperatureKey];
            }
        }
    });

    if (providerAdjusted && typeof window.autoSaveModelChange === 'function') {
        setTimeout(() => window.autoSaveModelChange(), 0);
    }
    
    // Populate sub-agent LMStudio model dropdowns after provider selections are applied
    // This ensures dropdowns are populated even when provider is already set to LMStudio
    const subAgentMap = {
        'cmdlineextract': 'CmdlineExtract',
        'proctreeextract': 'ProcTreeExtract'
    };
    
    Object.entries(subAgentMap).forEach(([prefix, agentName]) => {
        const providerSelect = document.getElementById(`${prefix}-provider`);
        if (providerSelect) {
            const provider = (providerSelect.value || getDefaultProvider()).toString().trim().toLowerCase();
            if (provider === 'lmstudio' && typeof repopulateSubAgentModelDropdown === 'function') {
                repopulateSubAgentModelDropdown(prefix, agentName);
            }
        }
    });

    updateSubAgentInheritanceHints();
    
    // Update config display to reflect current UI state
    if (typeof updateConfigDisplay === 'function') {
        updateConfigDisplay();
    }
}

function syncProviderVisibilityAndInputs() {
    Object.values(AGENT_CONFIG).forEach(config => {
        const select = document.getElementById(`${config.prefix}-provider`);
        if (!select) return;
        const provider = (select.value || getDefaultProvider()).toString().trim().toLowerCase();
        updateAgentProviderVisibility(config.prefix, provider);
        if (typeof window.renderSubAgentCommercialInputs === 'function') {
            window.renderSubAgentCommercialInputs(config.prefix);
        }
    });
}

// Generate subAgentCommercialMap from unified AGENT_CONFIG
const subAgentCommercialMap = {};
Object.values(AGENT_CONFIG).forEach(config => {
    if (config.isSubAgent || config.isQA) {
        subAgentCommercialMap[config.prefix] = { modelKey: config.modelKey };
    }
});

// Define and export globally so inline handlers can always reach it
if (typeof window !== 'undefined') {
    window.renderSubAgentCommercialInputs = function(agentPrefix) {
        const mapEntry = subAgentCommercialMap[agentPrefix];
        if (!mapEntry) return;
        const providerSelect = document.getElementById(`${agentPrefix}-provider`);
        const provider = (providerSelect?.value || getDefaultProvider()).toString().trim().toLowerCase();

        ['openai', 'codex', 'anthropic'].forEach(p => {
            const container = document.querySelector(`[data-agent-prefix="${agentPrefix}"][data-provider="${p}"]`);
            if (!container) return;

            // Preserve unsaved DOM selection before replacing container content
            const existingInput = document.getElementById(`${agentPrefix}-model-${p}`);
            const currentModelFromDOM = existingInput?.value || '';
            const currentModelFromConfig = agentModels?.[mapEntry.modelKey] || '';
            const currentModel = currentModelFromDOM || currentModelFromConfig;

            container.innerHTML = buildCommercialProviderInput(agentPrefix, p, provider, currentModel);
        });
    };
}

function onAgentProviderChange(agentPrefix) {
    const select = document.getElementById(`${agentPrefix}-provider`);
    if (!select) return;
    const provider = (select.value || getDefaultProvider()).toString().trim().toLowerCase();
    // __dbgLog('H3', 'onAgentProviderChange', { agentPrefix, provider });
    updateAgentProviderVisibility(agentPrefix, provider);
    
    // Update temperature max based on provider (Anthropic: 1, others: 2)
    updateTemperatureLimit(agentPrefix, provider);
    
    // Clear model dropdowns/inputs when provider changes to ensure alignment
    const modelSelect = document.getElementById(`${agentPrefix}-model-2`) || document.getElementById(`${agentPrefix}-model`);
    const modelInputs = [
        document.getElementById(`${agentPrefix}-model-openai`),
        document.getElementById(`${agentPrefix}-model-codex`),
        document.getElementById(`${agentPrefix}-model-anthropic`)
    ].filter(Boolean);
    
    if (provider === 'lmstudio') {
        // Clear commercial provider inputs
        modelInputs.forEach(input => input.value = '');
        
        // Repopulate LMStudio model dropdown for main agents (RankAgent, ExtractAgent, SigmaAgent)
        const mainAgentMap = {
            'rankagent': 'RankAgent',
            'extractagent': 'ExtractAgent',
            'sigmaagent': 'SigmaAgent'
        };
        const mainAgentName = mainAgentMap[agentPrefix];
        if (mainAgentName && typeof loadLMStudioModels === 'function') {
            // Repopulate main agent dropdown by reloading all LMStudio models
            loadLMStudioModels();
        }
        
        // Repopulate LMStudio model dropdown for sub-agents
        const subAgentMap = {
            'cmdlineextract': 'CmdlineExtract',
            'proctreeextract': 'ProcTreeExtract'
        };
        const agentName = subAgentMap[agentPrefix];
        if (agentName && typeof repopulateSubAgentModelDropdown === 'function') {
            repopulateSubAgentModelDropdown(agentPrefix, agentName);
        }
    } else {
        // Clear LMStudio model dropdown only if switching away from LMStudio
        if (modelSelect) {
            // Only clear if current value might be from wrong provider
            // Check if value looks like LMStudio model (not common OpenAI/Anthropic patterns)
            const currentValue = modelSelect.value;
            if (currentValue && !currentValue.match(/^(gpt|o[13]|text-|davinci|curie|babbage|ada|whisper|omni|turbo|claude)/i)) {
                modelSelect.value = '';
            }
        }
        // Clear commercial inputs when switching away from them
        modelInputs.forEach(input => {
            if (provider !== input.id.split('-').pop()) {
                input.value = '';
            }
        });
    }
    
    // Validate current model against new provider
    const currentModel = getActiveAgentModelValue(agentPrefix, provider);
    if (currentModel) {
        validateProviderModelCombination(agentPrefix, provider, currentModel);
    } else {
        clearProviderModelError(agentPrefix);
    }
    updateTemperatureCapabilityUI(agentPrefix);
    
    if (typeof window.renderSubAgentCommercialInputs === 'function') {
        window.renderSubAgentCommercialInputs(agentPrefix);
    }
    if (typeof normalizeWorkflowConfigControlBindings === 'function') {
        normalizeWorkflowConfigControlBindings();
    }
    updateSubAgentInheritanceHints();
    autoSaveModelChange();
}
// Keep a reference the stub can call even if overwritten order varies
window._onAgentProviderChangeImpl = onAgentProviderChange;
window.onAgentProviderChange = onAgentProviderChange;

// Global refresh to enforce correct provider visibility/inputs across all provider selects
function refreshAllProviderBlocks() {
    const selects = document.querySelectorAll('select[id$="-provider"]');
    selects.forEach(select => {
        const prefix = select.id.replace(/-provider$/, '');
        const provider = (select.value || getDefaultProvider()).toString().trim().toLowerCase();
        // __dbgLog('H4', 'refreshAllProviderBlocks iterate', { prefix, provider });
        updateAgentProviderVisibility(prefix, provider);
        // Update temperature limit based on provider
        updateTemperatureLimit(prefix, provider);
        if (typeof window.renderSubAgentCommercialInputs === 'function') {
            window.renderSubAgentCommercialInputs(prefix);
        } else {
            // Last-resort visibility only
            const lm = document.querySelector(`[data-agent-prefix="${prefix}"][data-provider="lmstudio"]`);
            const openai = document.querySelector(`[data-agent-prefix="${prefix}"][data-provider="openai"]`);
            const codex = document.querySelector(`[data-agent-prefix="${prefix}"][data-provider="codex"]`);
            const anthropic = document.querySelector(`[data-agent-prefix="${prefix}"][data-provider="anthropic"]`);
            [lm, openai, codex, anthropic].forEach(el => {
                if (!el || !el.dataset.provider) return;
                const gp = el.dataset.provider.toString().trim().toLowerCase();
                if (gp === provider) {
                    el.classList.remove('hidden');
                    el.style.display = '';
                } else {
                    el.classList.add('hidden');
                    el.style.display = 'none';
                }
            });
        }
    });
    if (typeof normalizeWorkflowConfigControlBindings === 'function') {
        normalizeWorkflowConfigControlBindings();
    }
}
if (typeof window !== 'undefined') {
    window.refreshAllProviderBlocks = refreshAllProviderBlocks;
}

// Ensure current dropdown selections drive visibility/inputs even if agentModels default to LMStudio
syncProviderVisibilityAndInputs();


// REMOVED: Duplicate loadAgentPrompts function - using the one at line 5599 instead

async function bootstrapPromptsFromFiles() {
    if (!await ModalManager.confirm('Import default prompts from files into database? This will create a new config version with all default prompts loaded.', { title: 'Import Prompts', confirmText: 'Import', confirmClass: 'bg-purple-600 hover:bg-purple-700', cancelText: 'Cancel' })) {
        return;
    }

    try {
        const response = await fetch('/api/workflow/config/prompts/bootstrap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.ok) {
            const result = await response.json();
            showNotification('Successfully imported ' + result.prompts_loaded.length + ' prompts', 'success');
            // Reload prompts and config
            await loadAgentPrompts();
            await loadConfig();
        } else {
            const error = await response.json();
            showNotification('Error importing prompts: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error bootstrapping prompts:', error);
        showNotification('Error importing prompts from files', 'error');
    }
}

let editingPrompts = {}; // Track which prompts are being edited

// SigmaAgent and RankAgent intentionally excluded -- they don't use the
// extraction-agent envelope (task/json_example/instructions); they only
// need {system, user}, matching what their backend readers
// (parse_sigma_agent_prompt_data / _parse_rank_prompt) expect.
const LOCKED_EXTRACTOR_AGENTS = [
    'CmdlineExtract',
    'ProcTreeExtract',
    'HuntQueriesExtract',
    'RegistryExtract',
    'ServicesExtract',
    'ScheduledTasksExtract',
    'NetworkIndicatorExtract',
];

// SigmaAgent and RankAgent: user scaffold is code-owned (locked) but the save path is
// canonical {system, user}, not the extraction-agent envelope. Keeping them separate from
// LOCKED_EXTRACTOR_AGENTS avoids mis-routing their saves through the
// JSON-envelope branch in saveAgentPrompt2.
const LOCKED_CANONICAL_AGENTS = ['SigmaAgent', 'RankAgent'];

function isLockedCanonicalPrompt(agentName) {
    return LOCKED_CANONICAL_AGENTS.includes(agentName);
}

const LOCKED_EXTRACTION_USER_TEMPLATE = 'Title: {title}\nURL: {url}\n\nContent:\n{content}\n\n{instructions}';
const LOCKED_RANK_USER_TEMPLATE = 'Article Title: {title}\nSource: {source}\nURL: {url}\n\nContent:\n{content}';
// Mirrors src/prompts/sigma_generate_multi.txt — SigmaAgent's user message template. The backend
// formats this with {title}, {source}, {url}, {content}, {observables_section}.
const LOCKED_SIGMA_USER_TEMPLATE = [
    'Generate Sigma detection rules from the following threat intelligence. Produce multiple rules if the behaviors differ.',
    '',
    'Threat Intel Input:',
    '- title: {title}',
    '- source: {source}',
    '- url: {url}',
    '- content: {content}',
    '{observables_section}',
    '',
    'Objectives:',
    '- Extract every distinct behavioral TTP (command execution, process lineage, persistence, defense evasion, system modification).',
    '- Create 1 rule per behavior when possible.',
    '- Extract all command-line patterns with arguments; include all unique process-creation observables.',
    '',
    'Structural Requirements (YAML Syntax):',
    '- Output ONLY valid YAML document structure.',
    '- Use --- (three dashes) as separator between multiple rules.',
    '- NO prose, explanations, comments, or narrative text of any kind.',
    '- NO code fences.',
    '- Start your response immediately with title: - nothing before it.',
    '- 2-space indentation only; no tabs.',
    '- All field names lowercase.',
    '',
    'CRITICAL: Your response will be parsed as YAML. If you include ANY narrative text before or within the YAML, parsing will fail. Output ONLY the YAML rule structure(s).',
    '',
    'Required Structure (per rule):',
    'title: [descriptive rule title]',
    'id: [UUID]',
    'description: [behavior detected]',
    'observables_used: [list of 0-based indices from the Observables list above that this rule uses; omit if no observables provided]',
    'logsource:',
    '  category: [process_creation/network_connection/registry_event/file_event/powershell/wmi]',
    '  product: [windows/linux/macos]',
    'detection:',
    '  selection:',
    '    [criteria]',
    '  condition: selection',
    'level: [low/medium/high/critical]',
    'tags:',
    '  - attack.[technique]',
    'references:',
    '  - {url}',
    '',
    'Behavioral Extraction Rules:',
    '- For process creation TTPs: include all command-line patterns with args; include parent-child relationships when inferable; include LOLBin/scripting abuse.',
    '- For system modification: include registry, services, scheduled tasks.',
    '- For defense evasion: include AV disablement, AMSI bypass, obfuscation flags.',
    '- For network activity: include C2 connections, lateral movement, data exfiltration.',
    '',
    'Final Instruction:',
    'Generate all applicable SIGMA rules from the threat intelligence above. Use --- to separate multiple rules. Output ONLY YAML starting with title:.'
].join('\n');

function isLockedExtractorPrompt(agentName) {
    return LOCKED_EXTRACTOR_AGENTS.includes(agentName);
}

function getLockedUserTemplate(agentName) {
    if (agentName === 'RankAgent') return LOCKED_RANK_USER_TEMPLATE;
    if (agentName === 'SigmaAgent') return LOCKED_SIGMA_USER_TEMPLATE;
    if (isLockedExtractorPrompt(agentName)) return LOCKED_EXTRACTION_USER_TEMPLATE;
    return '';
}

// ── Effective-prompt preview ────────────────────────────────────────────────
// Users can edit the system message, but the backend also appends a hard-coded
// "user message" template (the LOCKED_*_USER_TEMPLATE constants above). This
// preview shows the *full* message pair that will be sent to the LLM, with
// {placeholders} highlighted so the user understands what gets filled in at
// runtime. No backend call required — the templates are code-owned and live
// right here in the JS.
const EFFECTIVE_PROMPT_PLACEHOLDER_DOCS = {
    title: 'Article title',
    url: 'Article URL',
    source: 'Article source (feed / publisher)',
    content: 'Full article body text',
    instructions: "Extraction instructions (from the agent's DB prompt config)",
    observables_section: 'Optional "Observables" block — present only when behaviors were extracted upstream',
    objective: 'QA task objective',
    task: "The original extractor's task string",
    extraction_instructions: "Paired extractor's instructions",
    extraction_output_format: "Paired extractor's JSON output schema",
    article_content: 'Full article body text (same as {content})',
    extracted_commands: 'JSON output from the paired extractor',
    evaluation_criteria: 'QA evaluation criteria'
};

function _effEscape(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Only the user template is .format()-ed at runtime. The system message is
// sent verbatim, so a string like "{payload}" in the system prose is literal
// documentation (e.g. CmdlineExtract tells the LLM to ignore such patterns)
// and must not be highlighted as a substitution.
function _effHighlightPlaceholdersInUserTemplate(text) {
    const escaped = _effEscape(text);
    return escaped.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_m, name) => {
        const doc = EFFECTIVE_PROMPT_PLACEHOLDER_DOCS[name] || 'Filled at runtime by the backend (unknown placeholder)';
        return `<span class="eff-placeholder" data-ph="${_effEscape(name)}" title="${_effEscape(doc)}">{${_effEscape(name)}}</span>`;
    });
}

function _effCollectUserPlaceholders(text) {
    const seen = new Set();
    (text || '').replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_m, name) => { seen.add(name); return _m; });
    return Array.from(seen);
}

function _effReadCurrentSystem(agentName) {
    const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
    const ta = document.getElementById(`${agentId}-prompt-system`)
            || document.getElementById(`${agentId}-prompt-system-2`);
    if (ta && typeof ta.value === 'string') return ta.value;
    const promptData = (typeof agentPrompts !== 'undefined' && agentPrompts) ? agentPrompts[agentName] : null;
    const raw = promptData ? (promptData.prompt || '') : '';
    const parts = (typeof parsePromptParts === 'function') ? parsePromptParts(raw) : { system: raw, user: '' };
    // Plain-text prompts land in parts.user; structured (JSON) prompts land in parts.system.
    return parts.system || parts.user || '';
}

function _effReadCurrentUserTemplate(agentName) {
    // Locked (code-owned) template wins — that's what the backend actually
    // concatenates before hitting the LLM. If the agent has no locked template,
    // fall back to whatever the user has in the DB (editable user textarea).
    const locked = getLockedUserTemplate(agentName);
    if (locked) return { text: locked, source: 'locked' };
    const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
    const ta = document.getElementById(`${agentId}-prompt-user`)
            || document.getElementById(`${agentId}-prompt-user-2`);
    if (ta && typeof ta.value === 'string') return { text: ta.value, source: 'db' };
    const promptData = (typeof agentPrompts !== 'undefined' && agentPrompts) ? agentPrompts[agentName] : null;
    const raw = promptData ? (promptData.prompt || '') : '';
    const parts = (typeof parsePromptParts === 'function') ? parsePromptParts(raw) : { system: '', user: raw };
    return { text: parts.user || '', source: 'db' };
}

function showEffectivePrompt(agentName) {
    const existing = document.getElementById('effectivePromptModal');
    if (existing) existing.remove();

    const system = _effReadCurrentSystem(agentName);
    const userTpl = _effReadCurrentUserTemplate(agentName);
    // Only the user template is .format()-ed at runtime — the system message
    // is sent verbatim. Braces in the system prose (e.g. "{payload}" as an
    // example pattern the LLM should ignore) are NOT substitutions.
    const placeholders = _effCollectUserPlaceholders(userTpl.text);

    const userSourceBadge = userTpl.source === 'locked'
        ? '<span class="inline-block ml-2 px-2 py-0.5 text-[10px] rounded bg-amber-200 text-amber-900 font-semibold" title="This template is hard-coded in the backend and cannot be edited from the UI">LOCKED · code-owned</span>'
        : '<span class="inline-block ml-2 px-2 py-0.5 text-[10px] rounded bg-green-200 text-green-900 font-semibold">editable · from DB</span>';

    const placeholderLegendHtml = placeholders.length === 0
        ? '<div class="text-xs text-gray-500 dark:text-gray-400">No placeholders detected — the prompt is sent verbatim.</div>'
        : `<ul class="text-xs text-gray-700 dark:text-gray-300 space-y-1 list-none pl-0">${
            placeholders.map(p => `<li><code class="px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-pink-700 dark:text-pink-300">{${_effEscape(p)}}</code> → ${_effEscape(EFFECTIVE_PROMPT_PLACEHOLDER_DOCS[p] || 'Filled at runtime by the backend')}</li>`).join('')
          }</ul>`;

    const safeAgentAttr = _effEscape(agentName);

    const modal = document.createElement('div');
    modal.id = 'effectivePromptModal';
    modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50';
    modal.innerHTML = `
      <style>
        #effectivePromptModal .eff-placeholder {
          background: rgba(236, 72, 153, 0.18);
          color: #be185d;
          border: 1px dashed rgba(236, 72, 153, 0.5);
          border-radius: 3px;
          padding: 0 2px;
          font-weight: 600;
        }
        .dark #effectivePromptModal .eff-placeholder {
          color: #f9a8d4;
          background: rgba(236, 72, 153, 0.14);
        }
      </style>
      <div class="relative top-10 mx-auto p-5 w-11/12 md:w-3/4 lg:w-2/3 shadow-lg rounded-md bg-gray-800 border border-gray-700 max-h-[90vh] overflow-y-auto">
        <div class="flex justify-between items-start mb-4">
          <div>
            <h3 class="text-xl font-bold text-gray-900 dark:text-white">Effective Prompt: ${_effEscape(agentName)}</h3>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">This is the complete message pair the backend sends to the model. Pink tokens like <code class="eff-placeholder">{title}</code> are filled at runtime.</p>
          </div>
          <button type="button" onclick="closeEffectivePromptModal()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" aria-label="Close">✕</button>
        </div>

        <div class="mb-4 p-3 rounded-md border border-gray-700" style="background: var(--panel-bg-5, #111827);">
          <div class="text-xs font-semibold mb-2 text-gray-200">Placeholders in this prompt</div>
          ${placeholderLegendHtml}
        </div>

        <div class="space-y-4">
          <div>
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <span>System message</span>
                <span class="inline-block px-2 py-0.5 text-[10px] rounded bg-blue-200 text-blue-900 font-semibold">editable · from DB</span>
              </div>
              <button type="button" onclick="copyEffectivePromptSection('eff-system-raw')" class="px-2 py-0.5 text-[11px] rounded bg-gray-600 hover:bg-gray-700 text-white">Copy</button>
            </div>
            <pre id="eff-system-raw" data-raw="${_effEscape(system || '')}" class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border-l-4 border-blue-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto text-gray-800 dark:text-gray-200 leading-relaxed">${system ? _effEscape(system) : '<span class="italic text-gray-400">(empty)</span>'}</pre>
          </div>

          <div>
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <span>User message template</span>
                ${userSourceBadge}
              </div>
              <button type="button" onclick="copyEffectivePromptSection('eff-user-raw')" class="px-2 py-0.5 text-[11px] rounded bg-gray-600 hover:bg-gray-700 text-white">Copy</button>
            </div>
            <pre id="eff-user-raw" data-raw="${_effEscape(userTpl.text || '')}" class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border-l-4 border-green-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md whitespace-pre-wrap break-words max-h-[40vh] overflow-y-auto text-gray-800 dark:text-gray-200 leading-relaxed">${userTpl.text ? _effHighlightPlaceholdersInUserTemplate(userTpl.text) : '<span class="italic text-gray-400">(empty)</span>'}</pre>
          </div>
        </div>

        <div class="mt-4 flex justify-end gap-2">
          <button type="button" onclick="copyEffectivePromptJSON('${safeAgentAttr}')" class="px-3 py-1.5 text-xs rounded bg-indigo-600 hover:bg-indigo-700 text-white">Copy chat JSON</button>
          <button type="button" onclick="closeEffectivePromptModal()" class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-gray-200">Close</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeEffectivePromptModal(); });
    const onEsc = (e) => {
        if (e.key === 'Escape') {
            closeEffectivePromptModal();
            document.removeEventListener('keydown', onEsc);
        }
    };
    document.addEventListener('keydown', onEsc);
}

function closeEffectivePromptModal() {
    const m = document.getElementById('effectivePromptModal');
    if (m) m.remove();
}

function copyEffectivePromptSection(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const text = el.getAttribute('data-raw') || el.textContent || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
            () => { if (typeof showNotification === 'function') showNotification('Copied to clipboard', 'success'); },
            () => { if (typeof showNotification === 'function') showNotification('Copy failed', 'error'); }
        );
    }
}

function copyEffectivePromptJSON(agentName) {
    const system = _effReadCurrentSystem(agentName);
    const userTpl = _effReadCurrentUserTemplate(agentName);
    const payload = [
        { role: 'system', content: system || '' },
        { role: 'user', content: userTpl.text || '' }
    ];
    const text = JSON.stringify(payload, null, 2);
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
            () => { if (typeof showNotification === 'function') showNotification('Chat JSON copied', 'success'); },
            () => { if (typeof showNotification === 'function') showNotification('Copy failed', 'error'); }
        );
    }
}

// Global function to parse prompts into system/user parts
function stripOuterCodeFence(rawPrompt) {
    const trimmed = (rawPrompt || '').trim();
    const m = trimmed.match(/^```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```$/);
    return m ? m[1].trim() : rawPrompt;
}

function tryParseJsonMaybeDoubleEncoded(rawPrompt) {
    try {
        const first = JSON.parse(rawPrompt);
        if (typeof first === 'string') {
            try {
                return JSON.parse(first);
            } catch (_) {
                return first;
            }
        }
        return first;
    } catch (e) {
        return null;
    }
}

function extractJsonStringField(rawPrompt, fieldName) {
    if (!rawPrompt) return null;
    const re = new RegExp('"' + fieldName + '"\\s*:\\s*("(?:\\\\\\\\.|[^"\\\\\\\\])*")', 'm');
    const m = rawPrompt.match(re);
    if (!m) return null;
    try {
        return JSON.parse(m[1]);
    } catch (e) {
        return null;
    }
}

// Returns {system, user, isTemplateFormat?, templateData?} for an agent's
// stored prompt data, handling both the canonical {system, user} outer-dict
// shape (post-migration) and legacy shapes via parsePromptParts(prompt).
//
// Canonical detection: outer dict has 'system' or 'user' keys AND no 'prompt'
// key. Legacy records always have 'prompt' (a JSON-encoded string or raw text).
function getAgentPromptParts(agentName) {
    const data = (typeof agentPrompts !== 'undefined' && agentPrompts && agentPrompts[agentName]) || {};
    const hasCanonicalKeys = ('system' in data) || ('user' in data);
    const hasLegacyPrompt = ('prompt' in data) && data.prompt !== '';
    if (hasCanonicalKeys && !hasLegacyPrompt) {
        return {
            system: (typeof data.system === 'string' ? data.system : '') || '',
            user: (typeof data.user === 'string' ? data.user : '') || '',
            isTemplateFormat: false,
            templateData: {}
        };
    }
    return parsePromptParts(data.prompt || '');
}

function parsePromptParts(rawPrompt) {
        let system = '';
        let user = rawPrompt || '';
        let isTemplateFormat = false;
        let templateData = {};
        
        try {
            const cleaned = stripOuterCodeFence(rawPrompt);
            const parsed = tryParseJsonMaybeDoubleEncoded(cleaned);
            if (parsed && typeof parsed === 'object') {
                // Check if it's the new template format (extraction agents)
                if (parsed.user_template) {
                    isTemplateFormat = true;
                    // Some older rows mistakenly store the *entire* template JSON as a string in `role`.
                    // If that happens, parse the nested JSON and use its `role`/`user_template`.
                    let templateObj = parsed;
                    if (typeof parsed.role === 'string') {
                        const roleTrim = parsed.role.trim();
                        if (roleTrim.startsWith('{') && roleTrim.endsWith('}')) {
                            const nested = tryParseJsonMaybeDoubleEncoded(roleTrim);
                            if (nested && typeof nested === 'object' && nested.user_template) {
                                templateObj = nested;
                            }
                        }
                    }

                    system = templateObj.system || templateObj.role || '';
                    user = templateObj.user_template || '';
                    templateData = {
                        role: templateObj.system || templateObj.role || '',
                        user_template: templateObj.user_template || '',
                        task: templateObj.task || templateObj.objective || '',
                        json_example: typeof templateObj.json_example === 'string' ? templateObj.json_example : JSON.stringify(templateObj.json_example || {}, null, 2),
                        instructions: templateObj.instructions || ''
                    };
                } else if (parsed.system || parsed.user) {
                    // Legacy simple format
                    system = parsed.system || '';
                    user = parsed.user || parsed.prompt || '';
                } else if (parsed.system || parsed.role || parsed.objective) {
                    // Standard Extractor Contract: system/task/json_example/instructions (no user_template).
                    // Expose the full config JSON as the editable system content -- the backend
                    // extracts system/task/instructions from this object at runtime.
                    system = rawPrompt;
                    user = '';
                    isTemplateFormat = true;
                    templateData = {
                        role: parsed.system || parsed.role || '',
                        user_template: '',
                        task: parsed.task || parsed.objective || '',
                        json_example: typeof parsed.json_example === 'string' ? parsed.json_example : JSON.stringify(parsed.json_example || {}, null, 2),
                        instructions: parsed.instructions || ''
                    };
                } else {
                    // Fallback: treat as user content
                    user = rawPrompt;
                }
            }
        } catch (e) {
            // fallback: treat entire prompt as user content
        }

        // Heuristic salvage path: if the prompt is almost-JSON (often due to a single
        // invalid escape inside a large json_example), try to extract key string fields
        // without requiring a full JSON.parse().
        if (!system && user) {
            const cleaned = stripOuterCodeFence(rawPrompt || '');
            const role = extractJsonStringField(cleaned, 'role');
            const objective = extractJsonStringField(cleaned, 'objective');
            const userTemplate = extractJsonStringField(cleaned, 'user_template');
            const sys = extractJsonStringField(cleaned, 'system');
            const usr = extractJsonStringField(cleaned, 'user') || extractJsonStringField(cleaned, 'prompt');

            if (role !== null || objective !== null || userTemplate !== null) {
                isTemplateFormat = true;
                system = role || objective || '';
                user = userTemplate || '';
                templateData = {
                    role: system,
                    user_template: user,
                    task: extractJsonStringField(cleaned, 'task') || '',
                    json_example: extractJsonStringField(cleaned, 'json_example') || '',
                    instructions: extractJsonStringField(cleaned, 'instructions') || ''
                };
            } else if (sys !== null || usr !== null) {
                system = sys || '';
                user = usr || '';
            }
        }
        return { system, user, isTemplateFormat, templateData };
}

function cancelEditPrompt(agentName) {
    editingPrompts[agentName] = false;
    renderAgentPrompts();
    // Reload prompts to restore original values
    loadAgentPrompts();
}

function validateAgentPrompt(agentName) {
    const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
    // Support both the agent-prompts tab (no suffix) and per-agent panels (-2 suffix)
    const resultDiv = document.getElementById(`${agentId}-validate-result`)
                   || document.getElementById(`${agentId}-validate-result-2`);
    if (!resultDiv) return;

    // Prefer the live textarea (edit mode); fall back to stored prompt when the
    // panel is collapsed/read-only so Validate works before clicking Edit.
    const systemTextarea = document.getElementById(`${agentId}-prompt-system`)
                        || document.getElementById(`${agentId}-prompt-system-2`);
    let systemVal;
    if (systemTextarea) {
        systemVal = (systemTextarea.value || '').trim();
    } else {
        const parts = getAgentPromptParts(agentName);
        // Plain-text prompts land in parts.user; structured (JSON) prompts land in parts.system.
        systemVal = (parts.system || parts.user || '').trim();
    }

    const issues = _collectPromptIssues(agentName, systemVal);
    _renderValidateResult(resultDiv, issues);
}

async function saveAgentPrompt(agentName) {
    const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
    const promptSystemElement = document.getElementById(`${agentId}-prompt-system`);
    const promptUserElement = document.getElementById(`${agentId}-prompt-user`);
    const lockedScaffold = isLockedExtractorPrompt(agentName) || isLockedCanonicalPrompt(agentName);
    if (!promptSystemElement || (!promptUserElement && !lockedScaffold)) {
        showNotification('Prompt elements not found', 'error');
        return;
    }
    isSavingPrompt = true;
    if (autoSaveTimeout) { clearTimeout(autoSaveTimeout); autoSaveTimeout = null; }
    const systemVal = promptSystemElement.value || "";
    const userVal = promptUserElement ? promptUserElement.value || "" : "";

    const isExtractionAgent = isLockedExtractorPrompt(agentName);
    const current = agentPrompts[agentName]?.prompt || '';
    let parsed = {};
    try { parsed = current ? JSON.parse(current) : {}; } catch (_) {}
    let combinedPrompt;
    let instructions = null;
    if (isExtractionAgent) {
        // If systemVal is a full JSON config object (user edited the full envelope),
        // use it directly. Otherwise treat it as a plain role persona string.
        let parsedSystem = null;
        try { parsedSystem = JSON.parse(systemVal); } catch (_) {}
        let merged;
        if (parsedSystem && typeof parsedSystem === 'object' && ('system' in parsedSystem || 'role' in parsedSystem)) {
            // Full JSON config edited -- use as-is, but normalize legacy role key.
            merged = { ...parsedSystem };
            if (merged.role && !merged.system) { merged.system = merged.role; }
        } else {
            // Plain system persona string -- preserve existing envelope fields
            merged = {
                ...parsed,
                system: systemVal,
                task: parsed.task || "",
                json_example: parsed.json_example || "{}",
                instructions: parsed.instructions || ""
            };
        }
        delete merged.user;
        delete merged.role;  // remove legacy key from any spread of old DB records
        delete merged.prompt;
        delete merged.user_template;  // not read by backend; keep JSON clean
        combinedPrompt = JSON.stringify(merged);
        instructions = merged.instructions || null;
    } else {
        // Canonical write path: send {system, user} as separate fields so the
        // API stores them at the outer dict level (post-migration shape).
        combinedPrompt = null;
    }

    const promptData = combinedPrompt === null
        ? {
            agent_name: agentName,
            system: systemVal,
            user: userVal,
            instructions: instructions,
            change_description: null
          }
        : {
            agent_name: agentName,
            prompt: combinedPrompt,
            instructions: instructions,
            change_description: null
          };

    try {
        const response = await fetch('/api/workflow/config/prompts', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(promptData)
        });

        if (response.ok) {
            const result = await response.json();
            console.log('Save successful:', result);
            editingPrompts[agentName] = false;
            // Apply saved prompt immediately so UI shows latest without refetch (avoids stale data)
            if (!agentPrompts) agentPrompts = {};
            const savedPrompt = result.prompt !== undefined ? result.prompt : promptData.prompt;
            const savedInstructions = result.instructions !== undefined ? result.instructions : (promptData.instructions || '');
            agentPrompts[agentName] = {
                ...(agentPrompts[agentName] || {}),
                prompt: savedPrompt,
                instructions: savedInstructions
            };
            if (currentConfig) {
                if (!currentConfig.agent_prompts) currentConfig.agent_prompts = {};
                currentConfig.agent_prompts[agentName] = agentPrompts[agentName];
            }
            renderAgentPrompts();
            lastPromptSaveAt = Date.now();
            lastSavedPromptAgent = agentName;
            console.log(`✅ Agent prompt updated successfully for ${agentName}`);
            if (currentConfig) {
                if (!currentConfig.agent_prompts) currentConfig.agent_prompts = {};
                currentConfig.agent_prompts[agentName] = agentPrompts[agentName];
            }
            resetOriginalConfigStateFromCurrent();
            updateSaveButtonState();
            isSavingPrompt = false;
            // Do NOT call loadConfig - it can overwrite display with stale fetched data
        } else {
            isSavingPrompt = false;
            const error = await response.json();
            showNotification('Error updating agent prompt: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        isSavingPrompt = false;
        console.error('Error saving agent prompt:', error);
        showNotification('Error saving agent prompt', 'error');
    }
}

async function showPromptHistory(agentName) {
    try {
        const response = await fetch(`/api/workflow/config/prompts/${encodeURIComponent(agentName)}/versions`);
        if (!response.ok) {
            showNotification('Error loading prompt history', 'error');
            return;
        }
        
        const data = await response.json();
        showPromptHistoryModal(agentName, data.versions);
    } catch (error) {
        console.error('Error loading prompt history:', error);
        showNotification('Error loading prompt history', 'error');
    }
}

async function showPromptHistoryModal(agentName, versions) {
    // Clean up existing modal
    const existingModal = document.getElementById('promptHistoryModal');
    if (existingModal) {
        if (window.ModalManager) {
            // Properly close modal through ModalManager to unregister handlers
            window.ModalManager.close('promptHistoryModal');
        }
        existingModal.remove();
        await new Promise(resolve => setTimeout(resolve, 50));
    }
    
    const modal = document.createElement('div');
    modal.id = 'promptHistoryModal';
    modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50';
    modal.innerHTML = `
        <div class="card relative top-20 mx-auto p-5 w-11/12 md:w-3/4 lg:w-2/3 shadow-lg max-h-[90vh]">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-bold text-gray-900 dark:text-white"><svg class="w-5 h-5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg> Version History: ${agentName}</h3>
                <button onclick="closePromptHistoryModal()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">&#x2715;</button>
            </div>
            <div class="space-y-4 max-h-[70vh] overflow-y-auto">
                ${versions.length === 0 ? 
                    '<div class="text-center text-gray-500 dark:text-gray-400 py-4">No version history available</div>' :
                    versions.map(v => {
                        const promptParts = parsePromptParts(v.prompt || '');
                        // When system IS the raw JSON envelope (Extractor Contract format),
                        // instructions are already embedded -- skip the separate display to
                        // avoid rendering the same text twice.
                        const isFullJsonDisplay = promptParts.system === (v.prompt || '');
                        const showInstructionsSeparately = v.instructions && !isFullJsonDisplay;
                        const systemLabel = isFullJsonDisplay ? 'Prompt Config (JSON):' : 'System Prompt:';
                        return `
                        <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                            <div class="flex justify-between items-start mb-2">
                                <div>
                                    <span class="font-semibold text-gray-900 dark:text-white">Version ${v.version}</span>
                                    <span class="text-sm text-gray-500 dark:text-gray-400 ml-2">
                                        (Workflow Config v${v.workflow_config_version})
                                    </span>
                                </div>
                                <button onclick="rollbackPrompt('${agentName}', ${v.id})"
                                        class="px-3 py-1 bg-orange-600 hover:bg-orange-700 text-white text-sm rounded-md transition-colors">
                                    🔄 Rollback
                                </button>
                            </div>
                            <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                                ${new Date(v.created_at).toLocaleString()}
                                ${v.change_description ? ` | ${v.change_description}` : ''}
                            </div>
                            ${showInstructionsSeparately ? `
                                <div class="mb-4">
                                    <div class="text-sm font-semibold" style="color: var(--text-secondary) !important; mb-2">Instructions:</div>
                                    <div class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto text-gray-800 dark:text-gray-200 leading-relaxed">${escapeHtml(v.instructions)}</div>
                                </div>
                            ` : ''}
                            ${(promptParts.system || promptParts.user) ? `
                                        <div class="space-y-3">
                                            ${promptParts.system ? `
                                                <div>
                                                    <div class="text-sm font-semibold flex items-center gap-2 mb-2" style="color: var(--text-secondary) !important;">
                                                        <span><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17l-5.648 5.648a2.477 2.477 0 01-3.5-3.5l5.648-5.648m2.56-1.06l2.56 2.56m5.35-8.076a3.375 3.375 0 00-4.773-4.773L9.563 6.96l4.773 4.773 5.434-5.557z"/></svg></span>
                                                        <span>${systemLabel}</span>
                                                    </div>
                                                    <div class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border-l-4 border-blue-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto text-gray-800 dark:text-gray-200 leading-relaxed">${escapeHtml(promptParts.system)}</div>
                                                </div>
                                            ` : ''}
                                            ${promptParts.user ? `
                                                <div>
                                                    <div class="text-sm font-semibold flex items-center gap-2 mb-2" style="color: var(--text-secondary) !important;">
                                                        <span><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/></svg></span>
                                                        <span>User Prompt:</span>
                                                    </div>
                                                    <div class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border-l-4 border-green-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto text-gray-800 dark:text-gray-200 leading-relaxed">${escapeHtml(promptParts.user)}</div>
                                                </div>
                                            ` : ''}
                                        </div>
                            ` : `
                            <div>
                                <div class="text-sm font-semibold" style="color: var(--text-secondary) !important; mb-2">Prompt:</div>
                                <div class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto text-gray-800 dark:text-gray-200 leading-relaxed">${escapeHtml(v.prompt)}</div>
                            </div>
                            `}
                        </div>
                    `;}).join('')
                }
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Ensure modal is visible
    modal.classList.remove('hidden');
    
    // Register and open with ModalManager
    if (window.ModalManager) {
        setTimeout(() => {
            // Register the new dynamic modal (will update registration if already exists)
            window.ModalManager.register('promptHistoryModal', {
                isDynamic: true,
                hasInput: false
            });
            window.ModalManager.open('promptHistoryModal');
            modal.classList.remove('hidden');
        }, 100);
    }
}

function closePromptHistoryModal() {
    if (window.ModalManager) {
        window.ModalManager.close('promptHistoryModal');
    } else {
        const modal = document.getElementById('promptHistoryModal');
        if (modal) {
            modal.remove();
        }
    }
}

async function rollbackPrompt(agentName, versionId) {
    if (!await ModalManager.confirm(`Are you sure you want to rollback ${agentName} to this version?`, { title: 'Rollback Prompt', confirmText: 'Rollback', confirmClass: 'bg-orange-600 hover:bg-orange-700', cancelText: 'Cancel' })) {
        return;
    }
    
    try {
        const response = await fetch(`/api/workflow/config/prompts/${encodeURIComponent(agentName)}/rollback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version_id: versionId })
        });
        
        if (response.ok) {
            const result = await response.json();
            showNotification('Rolled back ' + agentName + ' successfully', 'success');
            closePromptHistoryModal();
            // Apply rolled-back prompt immediately from response (avoids race/cache with follow-up fetches)
            if (result.prompt !== undefined) {
                if (!agentPrompts) agentPrompts = {};
                agentPrompts[agentName] = {
                    ...(agentPrompts[agentName] || {}),
                    prompt: result.prompt,
                    instructions: result.instructions || ''
                };
                if (currentConfig) {
                    if (!currentConfig.agent_prompts) currentConfig.agent_prompts = {};
                    currentConfig.agent_prompts[agentName] = agentPrompts[agentName];
                }
                lastPromptSaveAt = Date.now();
                lastSavedPromptAgent = agentName;
                renderAgentPrompts();
            }
            // Skip loadAgentPrompts - we have the prompt from the response; loadConfig syncs the rest
            await loadConfig(true);
        } else {
            const error = await response.json();
            showNotification('Error rolling back: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error rolling back prompt:', error);
        showNotification('Error rolling back prompt', 'error');
    }
}

// Build temperature + top_p slider pair HTML (for dynamic agent model rows). tempMax defaults to 2.
function buildTempTopPSliderRow(prefix, tempVal, topPVal, tempKey, topPKey, tempMax) {
    const t = typeof tempVal === 'number' ? tempVal : parseFloat(tempVal) || 0;
    const p = typeof topPVal === 'number' ? topPVal : parseFloat(topPVal) || 0.9;
    const maxT = tempMax !== undefined ? tempMax : 2;
    return `
    <div class="flex-1 threshold-slider">
        <div class="flex justify-between items-center mb-1">
            <label for="${prefix}-temperature" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Temperature</label>
            <span id="${prefix}-temperature-value" class="text-purple-400 font-medium">${t}</span>
        </div>
        <input type="range" id="${prefix}-temperature" name="agent_models[${tempKey}]" min="0" max="${maxT}" step="0.1" value="${t}"
               class="threshold-slider-input w-full" oninput="updateThresholdDisplay('${prefix}-temperature'); autoSaveModelChange()">
        <div class="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 mt-1"><span>0</span><span>${maxT}</span></div>
    </div>
    <div class="flex-1 threshold-slider">
        <div class="flex justify-between items-center mb-1">
            <label for="${prefix}-top-p" class="block text-xs font-semibold" style="color: var(--text-primary) !important;">Top_P</label>
            <span id="${prefix}-top-p-value" class="text-purple-400 font-medium">${p}</span>
        </div>
        <input type="range" id="${prefix}-top-p" name="agent_models[${topPKey}]" min="0" max="1" step="0.01" value="${p}"
               class="threshold-slider-input w-full" oninput="updateThresholdDisplay('${prefix}-top-p'); autoSaveModelChange()">
        <div class="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 mt-1"><span>0.0</span><span>1.0</span></div>
    </div>`;
}

// Update threshold slider value display (call on input and when loading config)
function updateThresholdDisplay(inputId) {
    const input = document.getElementById(inputId);
    const valueSpan = document.getElementById(inputId + '-value');
    if (!input || !valueSpan) return;
    const v = parseFloat(input.value);
    valueSpan.textContent = Number.isInteger(v) ? String(v) : v.toFixed(v < 1 ? 2 : 1);
}

// Validation function for thresholds
function validateThreshold(input, min, max) {
    const value = parseFloat(input.value);
    const errorElement = document.getElementById(input.id + '-error');
    
    // Clear previous error
    if (errorElement) {
        errorElement.classList.add('hidden');
        input.classList.remove('border-red-500', 'dark:border-red-500');
    }
    
    // Validate
    if (isNaN(value)) {
        if (errorElement) {
            errorElement.textContent = 'Please enter a valid number';
            errorElement.classList.remove('hidden');
            input.classList.add('border-red-500', 'dark:border-red-500');
        }
        return false;
    }
    
    if (value < min || value > max) {
        if (errorElement) {
            errorElement.textContent = `Value must be between ${min} and ${max}`;
            errorElement.classList.remove('hidden');
            input.classList.add('border-red-500', 'dark:border-red-500');
        }
        return false;
    }
    
    return true;
}

// Configuration Functions (variables declared above)

function toggleCollapsible(panelId) {
    const content = document.getElementById(`${panelId}-content`);
    const toggle = document.getElementById(`${panelId}-toggle`);
    
    if (content && toggle) {
        const isHidden = content.classList.contains('hidden');
        if (isHidden) {
            content.classList.remove('hidden');
            toggle.textContent = '▲';
            toggle.style.transform = 'rotate(0deg)';
        } else {
            content.classList.add('hidden');
            toggle.textContent = '▼';
            toggle.style.transform = 'rotate(0deg)';
        }
    }
}


async function loadConfig(skipPromptReload = false) {
    // Set initialization flag to prevent autosave during config loading
    const wasInitializing = isInitializing;
    if (!skipPromptReload) {
        isInitializing = true;
        window.isInitializing = true;
    }
    
    try {
        // Always bypass cache here so refreshes reflect the newest saved workflow config.
        // Browser-cached responses can otherwise rehydrate the form with a stale toggle state.
        const configUrl = '/api/workflow/config?' + new Date().getTime();
        const response = await fetch(configUrl, {
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache' }
        });
        if (response.ok) {
            const fetchedConfig = await response.json();

            // Always use fetched config from database (source of truth)
            currentConfig = fetchedConfig;

            // When skipPromptReload: agentPrompts was just updated by loadAgentPrompts() (post-save/rollback).
            // Sync currentConfig.agent_prompts so auto-save and other logic use fresh prompt data.
            if (skipPromptReload && agentPrompts && Object.keys(agentPrompts).length > 0) {
                currentConfig.agent_prompts = { ...(currentConfig.agent_prompts || {}), ...agentPrompts };
            }

            // Populate form fields
            if (currentConfig.ranking_threshold !== undefined) {
                document.getElementById('rankingThreshold').value = currentConfig.ranking_threshold;
            }
            if (currentConfig.junk_filter_threshold !== undefined) {
                document.getElementById('junkFilterThreshold').value = currentConfig.junk_filter_threshold;
            }
            if (currentConfig.similarity_threshold !== undefined) {
                document.getElementById('similarityThreshold').value = currentConfig.similarity_threshold;
            }
            ['junkFilterThreshold', 'rankingThreshold', 'similarityThreshold'].forEach(updateThresholdDisplay);

            // Don't update config display here - wait until models are loaded
        } else {
            // Config API failed - still try to render agent models with empty config
            console.warn('Config API failed, using empty config');
            currentConfig = { agent_models: {} };
        }

        // Always load agent models and prompts, even if config API failed
        await refreshCommercialModelCatalog();
        await loadAgentModels();
        if (!skipPromptReload) {
            await loadAgentPrompts();
        }
        refreshAllProviderBlocks();
        
        // CRITICAL: Apply agent configs (models, providers, temperatures) from saved config
        // This ensures extractor LLM settings survive refresh after save
        if (currentConfig && currentConfig.agent_models) {
            applyAgentConfigs(currentConfig.agent_models);
        }
        
        // Validate and clamp all temperature inputs after config is loaded
        // This fixes any invalid values (e.g., 2.5 when max is 2) that might have been saved
        validateAllTemperatureInputs();
        
        // Update config display after models are loaded
        updateConfigDisplay();
        
        // Sync extract agent toggles
        // Suppress events during initialization to prevent triggering autosave
        syncExtractAgentTogglesFromConfig(true);
        
        // Load SIGMA fallback setting
        const sigmaFallbackCheckbox = document.getElementById('sigma-fallback-enabled');
        if (sigmaFallbackCheckbox && currentConfig.sigma_fallback_enabled !== undefined) {
            sigmaFallbackCheckbox.checked = currentConfig.sigma_fallback_enabled;
        }
        const rankAgentEnabledCheckbox = document.getElementById('rank-agent-enabled');
        if (rankAgentEnabledCheckbox && currentConfig.rank_agent_enabled !== undefined) {
            rankAgentEnabledCheckbox.checked = currentConfig.rank_agent_enabled;
        } else if (rankAgentEnabledCheckbox) {
            // Default to true if not specified
            rankAgentEnabledCheckbox.checked = true;
        }
        const cmdlineAttentionPreprocessorCheckbox = document.getElementById('cmdline-attention-preprocessor-enabled');
        if (cmdlineAttentionPreprocessorCheckbox && currentConfig.cmdline_attention_preprocessor_enabled !== undefined) {
            cmdlineAttentionPreprocessorCheckbox.checked = currentConfig.cmdline_attention_preprocessor_enabled;
        } else if (cmdlineAttentionPreprocessorCheckbox) {
            cmdlineAttentionPreprocessorCheckbox.checked = true;
        }
        const proctreeAttentionPreprocessorCheckbox = document.getElementById('proctree-attention-preprocessor-enabled');
        if (proctreeAttentionPreprocessorCheckbox && currentConfig.proc_tree_attention_preprocessor_enabled !== undefined) {
            proctreeAttentionPreprocessorCheckbox.checked = currentConfig.proc_tree_attention_preprocessor_enabled;
        } else if (proctreeAttentionPreprocessorCheckbox) {
            proctreeAttentionPreprocessorCheckbox.checked = true;
        }
        // Update badge to reflect initial state
        if (typeof updateRankEnabledBadge === 'function') {
            updateRankEnabledBadge();
        }
        
        // Initialize change tracking after config is loaded
        initializeChangeTracking();
        
        // Load sub-agent temperature values and clamp to provider limits
        const agentModels = currentConfig?.agent_models || {};
        const subAgents = [
            { name: 'RankAgent', id: 'rankagent-temperature', prefix: 'rankagent' },
            { name: 'CmdlineExtract', id: 'cmdlineextract-temperature', prefix: 'cmdlineextract' },
            { name: 'ProcTreeExtract', id: 'proctreeextract-temperature', prefix: 'proctreeextract' },
            { name: 'HuntQueriesExtract', id: 'huntqueriesextract-temperature', prefix: 'huntqueriesextract' },
            { name: 'RegistryExtract', id: 'registryextract-temperature', prefix: 'registryextract' },
            { name: 'ServicesExtract', id: 'servicesextract-temperature', prefix: 'servicesextract' },
            { name: 'ScheduledTasksExtract', id: 'scheduledtasksextract-temperature', prefix: 'scheduledtasksextract' },
            { name: 'NetworkIndicatorExtract', id: 'networkindicatorextract-temperature', prefix: 'networkindicatorextract' },
        ];
        subAgents.forEach(subAgent => {
            const tempInput = document.getElementById(subAgent.id);
            if (tempInput) {
                const tempKey = `${subAgent.name}_temperature`;
                const tempValue = agentModels[tempKey];
                if (tempValue !== undefined) {
                    // Get provider for this agent to determine max
                    const provider = getAgentProvider(subAgent.prefix) || getDefaultProvider();
                    // LMStudio and Anthropic: max 1, OpenAI: max 2
                    const maxTemp = (provider === 'anthropic' || provider === 'lmstudio') ? 1 : 2;
                    const clampedValue = Math.min(Math.max(0, parseFloat(tempValue) || 0), maxTemp);
                    tempInput.value = clampedValue;
                    // Update max attribute
                    tempInput.setAttribute('max', maxTemp);
                    // If value was clamped, log a warning
                    if (parseFloat(tempValue) !== clampedValue) {
                        console.warn(`Temperature value ${tempValue} clamped to ${clampedValue} for ${subAgent.name} (provider: ${provider}, max: ${maxTemp})`);
                    }
                }
                // Ensure onChange handler is set
                if (!tempInput.getAttribute('onchange')) {
                    tempInput.setAttribute('onchange', 'autoSaveModelChange()');
                }
            }
        });
        
        // Normalize runtime-generated control attributes (names/aria/binding metadata)
        if (typeof normalizeWorkflowConfigControlBindings === 'function') {
            normalizeWorkflowConfigControlBindings();
        }
        
        // Clear initialization flag after all config is loaded and applied
        // This allows autosave to work for user changes
        if (!skipPromptReload) {
            // Use setTimeout to ensure all change events from initialization have fired
            setTimeout(() => {
                isInitializing = false;
                window.isInitializing = false;
                console.log('Initialization complete, autosave enabled');
                // Reset original state after initialization to clear any false "unsaved changes"
                resetOriginalConfigStateFromCurrent();
                updateSaveButtonState();
                // Scroll to top when page was opened with #config (override any scroll from loadConfig)
                if (window._workflowScrollToTopOnLoad) {
                    window._workflowScrollToTopOnLoad = false;
                    requestAnimationFrame(function () {
                        window.scrollTo(0, 0);
                        if (document.documentElement) document.documentElement.scrollTop = 0;
                        if (document.body) document.body.scrollTop = 0;
                    });
                }
            }, 100);
        } else {
            // If skipping prompt reload, restore previous initialization state
            isInitializing = wasInitializing;
            window.isInitializing = wasInitializing;
        }
    } catch (error) {
        console.error('Error loading config:', error);
        // Even on error, try to render agent models with empty config
        currentConfig = { agent_models: {} };
        await loadAgentModels().catch(err => console.error('Error loading agent models:', err));
        
        // Clear initialization flag even on error
        if (!skipPromptReload) {
            if (window._workflowScrollToTopOnLoad) {
                window._workflowScrollToTopOnLoad = false;
                requestAnimationFrame(function () {
                    window.scrollTo(0, 0);
                    if (document.documentElement) document.documentElement.scrollTop = 0;
                    if (document.body) document.body.scrollTop = 0;
                });
            }
            setTimeout(() => {
                isInitializing = false;
                window.isInitializing = false;
                console.log('Initialization complete (with errors), autosave enabled');
                resetOriginalConfigStateFromCurrent();
                updateSaveButtonState();
            }, 100);
        } else {
            isInitializing = wasInitializing;
            window.isInitializing = wasInitializing;
        }
    }
}

async function loadAgentModels() {
    // Prevent multiple simultaneous calls
    if (isLoadingAgentModels) {
        console.log('loadAgentModels already in progress, skipping duplicate call');
        return;
    }
    
    isLoadingAgentModels = true;
    try {
        // Check if any agent uses LMStudio before calling the API
        const agentModelsToCheck = currentConfig?.agent_models || agentModels || {};
        const hasLMStudioProvider = getAgentConfigs().some(config => {
            const storedProvider = agentModelsToCheck[config.providerKey] || getDefaultProvider();
            return storedProvider === 'lmstudio';
        });
        
        // Only call LMStudio API if at least one agent uses LMStudio
        if (hasLMStudioProvider) {
        const response = await fetch('/api/lmstudio-models');
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.models) {
                agentModels = currentConfig?.agent_models || {};
                renderAgentModels(data.models);
                applyProviderSelections(agentModels);
            } else {
                // API succeeded but returned no models - still render containers with empty model list
                agentModels = currentConfig?.agent_models || {};
                renderAgentModels([]);
                applyProviderSelections(agentModels);
            }
        } else {
            // API call failed - still render containers with empty model list
                agentModels = currentConfig?.agent_models || {};
                renderAgentModels([]);
                applyProviderSelections(agentModels);
            }
        } else {
            // No LMStudio providers - render UI with empty model list
            agentModels = currentConfig?.agent_models || {};
            renderAgentModels([]);
            applyProviderSelections(agentModels);
        }
    } catch (error) {
        console.error('Error loading agent models:', error);
        // Even on error, render containers with empty model list so UI structure is visible
        agentModels = currentConfig?.agent_models || {};
        renderAgentModels([]);
        applyProviderSelections(agentModels);
    } finally {
        isLoadingAgentModels = false;
    }
}

// Cache model lists for repopulating dropdowns when provider changes
let cachedSortedModelIds = [];
let cachedAvailableModelIds = [];
let isLoadingAgentModels = false; // Guard to prevent multiple simultaneous loads

function repopulateSubAgentModelDropdown(agentPrefix, agentName) {
    /**Repopulate a single sub-agent's model dropdown when provider changes to LMStudio.*/
    const select = document.getElementById(`${agentPrefix}-model`);
    if (!select) {
        console.warn(`Model select not found for ${agentPrefix}`);
        return;
    }
    
    // Get current model from DOM first (preserves unsaved user selection), then fallback to config
    const currentModelFromDOM = select.value || '';
    const agentModels = currentConfig?.agent_models || {};
    const currentModelFromConfig = agentModels[`${agentName}_model`] || '';
    const currentModel = currentModelFromDOM || currentModelFromConfig;
    
    if (cachedSortedModelIds.length === 0) {
        // No cached models - try to reload, but only if not already loading
        if (!isLoadingAgentModels) {
            isLoadingAgentModels = true;
            loadAgentModels()
                .catch(err => console.error('Error reloading models:', err))
                .finally(() => {
                    isLoadingAgentModels = false;
                });
        }
        return;
    }
    
    // Normalize model IDs
    const normalizeModelId = (modelId) => {
        if (typeof modelId !== 'string') return modelId;
        return modelId.replace(/:\d+$/, '');
    };
    
    const normalizedCurrent = currentModel ? normalizeModelId(currentModel) : null;
    const isLMStudioModel = !currentModel || !currentModel.match(/^(gpt|o[13]|text-|davinci|curie|babbage|ada|whisper|omni|turbo|claude)/i);
    const allModelIds = [...new Set([
        ...cachedSortedModelIds, 
        ...(currentModel && isLMStudioModel && !cachedSortedModelIds.some(m => normalizeModelId(m) === normalizedCurrent) ? [currentModel] : [])
    ])].sort();
    
    const modelOptions = allModelIds.map(modelId => {
        const isSelected = currentModel === modelId ? 'selected' : '';
        const isUnavailable = !cachedAvailableModelIds.includes(modelId) ? ' (not in LM Studio)' : '';
        return `<option value="${escapeHtml(modelId)}" ${isSelected}>${escapeHtml(modelId)}${isUnavailable}</option>`;
    }).join('');
    select.innerHTML = '<option value="">Inherit Extract Agents Model</option>' + modelOptions;
}

function renderAgentModels(lmstudioModels) {
    const agentMappings = {
        'os-detection': {
            container: 'os-detection-model-container',
            agentName: 'OSDetectionAgent',
            labels: { main: 'Platform Detection' }
        },
        'extract-agent': {
            container: 'extract-agent-model-container',
            agentName: 'ExtractAgent',
            labels: { main: 'Extract Agents' }
        },
        'sigma-agent': {
            container: 'sigma-agent-model-container',
            agentName: 'SigmaAgent',
            labels: { main: 'SIGMA Generator Agent' }
        }
    };
    
    // Normalize model IDs by removing numbered suffixes (:2, :3, etc.) for deduplication
    // LMStudio may return the same model multiple times with different instance numbers
    const normalizeModelId = (modelId) => {
        if (typeof modelId !== 'string') return modelId;
        // Remove :2, :3, etc. suffixes that indicate multiple instances of the same model
        return modelId.replace(/:\d+$/, '');
    };
    
    const availableModelIds = lmstudioModels.map(m => typeof m === 'string' ? m : m.id);
    
    // Cache model lists for repopulating dropdowns
    cachedAvailableModelIds = availableModelIds;
    
    // Create a map of normalized -> original (prefer base model without suffix)
    const modelMap = new Map();
    for (const modelId of availableModelIds) {
        const normalized = normalizeModelId(modelId);
        // Prefer base model (without suffix) over numbered instances
        if (!modelMap.has(normalized) || !modelId.includes(':')) {
            modelMap.set(normalized, modelId);
        }
    }
    
    // Get unique models (using normalized deduplication)
    const uniqueModelIds = Array.from(modelMap.values()).sort();
    const sortedModelIds = uniqueModelIds;
    
    // Cache sorted model IDs for repopulating dropdowns
    cachedSortedModelIds = sortedModelIds;

    const buildOptions = (currentModel, placeholder) => {
        // Normalize current model for comparison
        const normalizedCurrent = currentModel ? normalizeModelId(currentModel) : null;
        const allModelIds = [...new Set([...sortedModelIds, ...(currentModel && !sortedModelIds.some(m => normalizeModelId(m) === normalizedCurrent) ? [currentModel] : [])])];
        
        // If no models available and no current model, show a helpful message
        if (allModelIds.length === 0 && !currentModel) {
            return `<option value="">${placeholder}</option><option value="" disabled>⚠️ LM Studio not available - no models loaded</option>`;
        }
        
        return [
            `<option value="">${placeholder}</option>`,
            ...allModelIds.map(modelId => {
                const isSelected = currentModel === modelId ? 'selected' : '';
                const isUnavailable = !availableModelIds.includes(modelId) ? ' (not in LM Studio)' : '';
                return `<option value="${escapeHtml(modelId)}" ${isSelected}>${escapeHtml(modelId)}${isUnavailable}</option>`;
            })
        ].join('');
    };

    // Helper function to safely get container even if parent is hidden
    // Containers are always in the DOM, but parent panels may be collapsed (hidden)
    // We need to ensure we can render to them regardless of visibility state
    const getContainer = (containerId) => {
        const container = document.getElementById(containerId);
        if (!container) {
            console.warn(`Container ${containerId} not found`);
            return null;
        }
        // Containers exist in DOM even when parent is hidden, so we can always render
        // The issue was that innerHTML was being set but content wasn't visible when panel expanded
        // This is now fixed by ensuring we always render content regardless of parent visibility
        return container;
    };

    // Render Rank Agent Model
    const rankContainer = getContainer('rank-agent-model-container');
    if (rankContainer) {
        // Get current model from DOM first (preserves unsaved user selection), then fallback to config
        const rankSelect = document.getElementById('rankagent-model-2');
        const currentModelFromDOM = rankSelect?.value || '';
        const currentModelFromConfig = agentModels['RankAgent'] || '';
        const currentModel = currentModelFromDOM || currentModelFromConfig;
        const currentTemperature = agentModels['RankAgent_temperature'] !== undefined ? agentModels['RankAgent_temperature'] : 0.0;
        // Clamp top_p to valid range (0-1) if it comes from config with invalid value
        let currentTopP = agentModels['RankAgent_top_p'] !== undefined ? agentModels['RankAgent_top_p'] : 0.9;
        currentTopP = Math.max(0, Math.min(1, currentTopP));
        // Get current provider from DOM first (preserves unsaved user selection), then fallback to config
        const rankProviderSelect = document.getElementById('rankagent-provider');
        const currentProviderFromDOM = rankProviderSelect?.value || '';
        const currentProviderFromConfig = (agentModels && agentModels['RankAgent_provider']) || getDefaultProvider();
        const currentProvider = currentProviderFromDOM || currentProviderFromConfig;
        // Only use currentModel for LMStudio dropdown if provider is lmstudio
        const lmstudioModel = currentProvider === 'lmstudio' ? currentModel : '';
        const modelOptions = buildOptions(lmstudioModel, 'Select a model (required)');
        rankContainer.innerHTML = `
            <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 space-y-3" style="background: var(--panel-bg-5) !important;">
                <div class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    <span>Rank Agent Model</span>
                    <button type="button" 
                            onclick="showHelp('rankAgent')"
                            class="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 focus:outline-none"
                            title="Help">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>
                        </svg>
                    </button>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Provider</label>
                        ${buildProviderSelect('rankagent', currentProvider)}
                    </div>
                    <div>
                        <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Model</label>
                        <div data-agent-prefix="rankagent" data-provider="lmstudio">
                            <select id="rankagent-model-2"
                                    name="agent_models[RankAgent]"
                                    onchange="autoSaveModelChange()"
                                    class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs">
                                ${modelOptions}
                            </select>
                        </div>
                        <div data-agent-prefix="rankagent" data-provider="openai" class="hidden">
                            ${buildCommercialProviderInput('rankagent', 'openai', currentProvider, currentModel)}
                        </div>
                        <div data-agent-prefix="rankagent" data-provider="codex" class="hidden">
                            ${buildCommercialProviderInput('rankagent', 'codex', currentProvider, currentModel)}
                        </div>
                        <div data-agent-prefix="rankagent" data-provider="anthropic" class="hidden">
                            ${buildCommercialProviderInput('rankagent', 'anthropic', currentProvider, currentModel)}
                        </div>
                    </div>
                </div>
                ${enabledProviders.lmstudio && currentProvider === 'lmstudio' && sortedModelIds.length === 0 ? '<p class="text-xs text-orange-500 dark:text-orange-400 mt-1">⚠️ LM Studio is not available. Start LM Studio to load models.</p>' : ''}
                <div class="mt-3 flex gap-3">
                    ${buildTempTopPSliderRow('rankagent', currentTemperature, currentTopP, 'RankAgent_temperature', 'RankAgent_top_p')}
                </div>
            </div>
        `;
        ['rankagent-temperature', 'rankagent-top-p'].forEach(updateThresholdDisplay);
    }
    
    // Render OS Detection Model
    const osContainer = getContainer('os-detection-model-container');
    if (osContainer) {
        osContainer.innerHTML = `
            <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700" style="background: var(--panel-bg-5) !important;">
                <label class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Platform Detection
                    <button type="button" 
                            onclick="showHelp('osDetectionAgent')"
                            class="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 focus:outline-none"
                            title="Help">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>
                        </svg>
                    </button>
                </label>
                <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">
                    Deterministic keyword-registry detection, with an LLM fallback for the inconclusive tail — no model to configure.
                </p>
            </div>
        `;
    }
    
    // Render Extract Agents Fallback Model
    const extractContainer = getContainer('extract-agent-model-container');
    if (extractContainer) {
        // Get current model from DOM first (preserves unsaved user selection), then fallback to config
        const extractSelect = document.getElementById('extractagent-model-2');
        const currentModelFromDOM = extractSelect?.value || '';
        const currentModelFromConfig = agentModels['ExtractAgent'] || '';
        const currentModel = currentModelFromDOM || currentModelFromConfig;
        const currentTemperature = agentModels['ExtractAgent_temperature'] !== undefined ? agentModels['ExtractAgent_temperature'] : 0.0;
        let currentTopP = agentModels['ExtractAgent_top_p'] !== undefined ? agentModels['ExtractAgent_top_p'] : 0.9;
        currentTopP = Math.max(0, Math.min(1, currentTopP));
        // Get current provider from DOM first (preserves unsaved user selection), then fallback to config
        const extractProviderSelect = document.getElementById('extractagent-provider');
        const currentProviderFromDOM = extractProviderSelect?.value || '';
        const currentProviderFromConfig = (agentModels && agentModels['ExtractAgent_provider']) || getDefaultProvider();
        const currentProvider = currentProviderFromDOM || currentProviderFromConfig;
        // Only use currentModel for LMStudio dropdown if provider is lmstudio
        const lmstudioModel = currentProvider === 'lmstudio' ? currentModel : '';
        // Use deduplicated sorted models
        const modelOptions = sortedModelIds.map(modelId => {
            return `<option value="${escapeHtml(modelId)}" ${lmstudioModel === modelId ? 'selected' : ''}>${escapeHtml(modelId)}</option>`;
        }).join('');
        extractContainer.innerHTML = `
            <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 space-y-3" style="background: var(--panel-bg-5) !important;">
                <div class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    <span>Extract Agents Fallback Model</span>
                    <button type="button" 
                            onclick="showHelp('extractAgent')"
                            class="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 focus:outline-none"
                            title="Help">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>
                        </svg>
                    </button>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Provider</label>
                        ${buildProviderSelect('extractagent', currentProvider)}
                    </div>
                    <div>
                        <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Model</label>
                        <div data-agent-prefix="extractagent" data-provider="lmstudio">
                            <select id="extractagent-model-2"
                                    name="agent_models[ExtractAgent]"
                                    onchange="autoSaveModelChange()"
                                    class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs">
                                <option value="">Use default from Settings</option>
                                ${modelOptions}
                            </select>
                        </div>
                        <div data-agent-prefix="extractagent" data-provider="openai" class="hidden">
                            ${buildCommercialProviderInput('extractagent', 'openai', currentProvider, currentModel)}
                        </div>
                        <div data-agent-prefix="extractagent" data-provider="codex" class="hidden">
                            ${buildCommercialProviderInput('extractagent', 'codex', currentProvider, currentModel)}
                        </div>
                        <div data-agent-prefix="extractagent" data-provider="anthropic" class="hidden">
                            ${buildCommercialProviderInput('extractagent', 'anthropic', currentProvider, currentModel)}
                        </div>
                    </div>
                </div>
                 ${enabledProviders.lmstudio && currentProvider === 'lmstudio' && sortedModelIds.length === 0 ? '<p class="text-xs text-orange-500 dark:text-orange-400 mt-1">⚠️ LM Studio is not available. Start LM Studio to load models.</p>' : ''}
                 <div class="mt-3 flex gap-3">
                     ${buildTempTopPSliderRow('extractagent', currentTemperature, currentTopP, 'ExtractAgent_temperature', 'ExtractAgent_top_p')}
                 </div>
             </div>
        `;
        ['extractagent-temperature', 'extractagent-top-p'].forEach(updateThresholdDisplay);
    }
    
    // Render SIGMA Agent Model
    const sigmaContainer = getContainer('sigma-agent-model-container');
    if (sigmaContainer) {
        const currentModel = agentModels['SigmaAgent'] || '';
        const currentTemperature = agentModels['SigmaAgent_temperature'] !== undefined ? agentModels['SigmaAgent_temperature'] : 0.0;
        // Clamp top_p to valid range (0-1) if it comes from config with invalid value
        let currentTopP = agentModels['SigmaAgent_top_p'] !== undefined ? agentModels['SigmaAgent_top_p'] : 0.9;
        currentTopP = Math.max(0, Math.min(1, currentTopP));
        const currentProvider = (agentModels && agentModels['SigmaAgent_provider']) || getDefaultProvider();
        // Only use currentModel for LMStudio dropdown if provider is lmstudio
        const lmstudioModel = currentProvider === 'lmstudio' ? currentModel : '';
        // Use deduplicated sorted models
        const modelOptions = sortedModelIds.map(modelId => {
            return `<option value="${escapeHtml(modelId)}" ${lmstudioModel === modelId ? 'selected' : ''}>${escapeHtml(modelId)}</option>`;
        }).join('');
        sigmaContainer.innerHTML = `
            <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 space-y-3" style="background: var(--panel-bg-5) !important;">
                <div class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    <span>SIGMA Generator Agent Model</span>
                    <button type="button" 
                            onclick="showHelp('sigmaAgent')"
                            class="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 focus:outline-none"
                            title="Help">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>
                        </svg>
                    </button>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Provider</label>
                        ${buildProviderSelect('sigmaagent', currentProvider)}
                    </div>
                    <div>
                        <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Model</label>
                        <div data-agent-prefix="sigmaagent" data-provider="lmstudio">
                            <select id="sigmaagent-model-2"
                                    name="agent_models[SigmaAgent]"
                                    onchange="autoSaveModelChange()"
                                    class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs">
                                <option value="">Use default from Settings</option>
                                ${modelOptions}
                            </select>
                        </div>
                        <div data-agent-prefix="sigmaagent" data-provider="openai" class="hidden">
                            ${buildCommercialProviderInput('sigmaagent', 'openai', currentProvider, currentModel)}
                        </div>
                        <div data-agent-prefix="sigmaagent" data-provider="codex" class="hidden">
                            ${buildCommercialProviderInput('sigmaagent', 'codex', currentProvider, currentModel)}
                        </div>
                        <div data-agent-prefix="sigmaagent" data-provider="anthropic" class="hidden">
                            ${buildCommercialProviderInput('sigmaagent', 'anthropic', currentProvider, currentModel)}
                        </div>
                    </div>
                </div>
                 <div class="mt-3 flex gap-3">
                     ${buildTempTopPSliderRow('sigmaagent', currentTemperature, currentTopP, 'SigmaAgent_temperature', 'SigmaAgent_top_p')}
                 </div>
             </div>
        `;
        ['sigmaagent-temperature', 'sigmaagent-top-p'].forEach(updateThresholdDisplay);
    }
    
    // Populate sub-agent model dropdowns using unified system
    const subAgentConfigs = getAgentConfigs({ isSubAgent: true, hasFallback: true });
    
    subAgentConfigs.forEach(config => {
        const select = document.getElementById(`${config.prefix}-model`);
        const providerSelect = document.getElementById(`${config.prefix}-provider`);
        
        if (!select) {
            console.warn(`Model select element not found for ${config.name}: ${config.prefix}-model`);
            return;
        }
        
        if (!providerSelect) {
            console.warn(`Provider select element not found for ${config.name}: ${config.prefix}-provider`);
            // Still try to populate with default provider (lmstudio)
            // Get current model from DOM first (preserves unsaved user selection), then fallback to config
            const currentModelFromDOM = select.value || '';
            const currentModelFromConfig = agentModels[config.modelKey] || '';
            const currentModel = currentModelFromDOM || currentModelFromConfig;
            const normalizedCurrent = currentModel ? normalizeModelId(currentModel) : null;
            const isLMStudioModel = !currentModel || !currentModel.match(/^(gpt|o[13]|text-|davinci|curie|babbage|ada|whisper|omni|turbo|claude)/i);
            const allModelIds = [...new Set([
                ...sortedModelIds, 
                ...(currentModel && isLMStudioModel && !sortedModelIds.some(m => normalizeModelId(m) === normalizedCurrent) ? [currentModel] : [])
            ])].sort();
            
            const modelOptions = allModelIds.map(modelId => {
                const isSelected = currentModel === modelId ? 'selected' : '';
                const isUnavailable = !availableModelIds.includes(modelId) ? ' (not in LM Studio)' : '';
                return `<option value="${escapeHtml(modelId)}" ${isSelected}>${escapeHtml(modelId)}${isUnavailable}</option>`;
            }).join('');
            select.innerHTML = '<option value="">Inherit Extract Agents Model</option>' + modelOptions;
            if (!select.getAttribute('onchange')) {
                select.setAttribute('onchange', 'autoSaveConfig()');
            }
            return;
        }
        
        const currentProvider = (providerSelect.value || getDefaultProvider()).toString().trim().toLowerCase();
        // Get current model from DOM first (preserves unsaved user selection), then fallback to config
        const currentModelFromDOM = select.value || '';
        const currentModelFromConfig = agentModels[config.modelKey] || '';
        const currentModel = currentModelFromDOM || currentModelFromConfig;
        
        // Only populate LMStudio models if provider is LMStudio
        if (currentProvider === 'lmstudio') {
            // Use deduplicated sorted models, ensure current model is in the list (if it's an LMStudio model)
            const normalizedCurrent = currentModel ? normalizeModelId(currentModel) : null;
            // Only include currentModel if it looks like an LMStudio model
            const isLMStudioModel = !currentModel || !currentModel.match(/^(gpt|o[13]|text-|davinci|curie|babbage|ada|whisper|omni|turbo|claude)/i);
            const allModelIds = [...new Set([
                ...sortedModelIds, 
                ...(currentModel && isLMStudioModel && !sortedModelIds.some(m => normalizeModelId(m) === normalizedCurrent) ? [currentModel] : [])
            ])].sort();
            
            const modelOptions = allModelIds.map(modelId => {
                const isSelected = currentModel === modelId ? 'selected' : '';
                const isUnavailable = !availableModelIds.includes(modelId) ? ' (not in LM Studio)' : '';
                return `<option value="${escapeHtml(modelId)}" ${isSelected}>${escapeHtml(modelId)}${isUnavailable}</option>`;
            }).join('');
            select.innerHTML = '<option value="">Inherit Extract Agents Model</option>' + modelOptions;
        } else {
            // Provider is not LMStudio - clear dropdown (commercial provider inputs will be visible)
            select.innerHTML = '<option value="">Inherit Extract Agents Model</option>';
        }
        // Add onChange handler if not already present
        if (!select.getAttribute('onchange')) {
            select.setAttribute('onchange', 'autoSaveModelChange()');
        }
    });

    // Populate QA agent model dropdowns using unified system
    const qaConfigs = getAgentConfigs({ isQA: true });
    
    qaConfigs.forEach(config => {
        const selectEl = document.getElementById(`${config.prefix}-model`);
        const providerSelect = document.getElementById(`${config.prefix}-provider`);
        
        if (!selectEl) {
            console.warn(`QA model select element not found for ${config.name}: ${config.prefix}-model`);
            return;
        }
        
        if (!providerSelect) {
            console.warn(`QA provider select element not found for ${config.name}: ${config.prefix}-provider`);
            return;
        }
        
        const currentProvider = (providerSelect.value || getDefaultProvider()).toString().trim().toLowerCase();
        const currentModel = agentModels[config.modelKey] || '';
        
        const placeholder = 'Use Extract Agents model';
        
        // Only populate LMStudio models if provider is LMStudio
        if (currentProvider === 'lmstudio') {
            // Only include currentModel if it looks like an LMStudio model
            const isLMStudioModel = !currentModel || !currentModel.match(/^(gpt|o[13]|text-|davinci|curie|babbage|ada|whisper|omni|turbo|claude)/i);
            const modelToUse = isLMStudioModel ? currentModel : '';
            selectEl.innerHTML = buildOptions(modelToUse, placeholder);
        } else {
            // Provider is not LMStudio - clear dropdown (commercial provider inputs will be visible)
            selectEl.innerHTML = buildOptions('', placeholder);
        }
        
        // Load QA temperature
        if (config.temperatureKey) {
            const tempInput = document.getElementById(`${config.prefix}-temperature`);
            if (tempInput && agentModels[config.temperatureKey] !== undefined) {
                tempInput.value = agentModels[config.temperatureKey];
            }
        }
    });

    // Update provider visibility for dynamically-rendered main agents
    // Use setTimeout to ensure DOM is fully updated after innerHTML changes
    setTimeout(() => {
        const mainAgents = [
            { prefix: 'rankagent', key: 'RankAgent_provider' },
            { prefix: 'extractagent', key: 'ExtractAgent_provider' },
            { prefix: 'sigmaagent', key: 'SigmaAgent_provider' }
        ];

        mainAgents.forEach(agent => {
            const provider = (agentModels && agentModels[agent.key]) || getDefaultProvider();
            // Set the provider dropdown value
            const providerSelect = document.getElementById(`${agent.prefix}-provider`);
            if (providerSelect) {
                providerSelect.value = provider;
            }
            // Update visibility of provider sections
            updateAgentProviderVisibility(agent.prefix, provider);
        });
        if (typeof normalizeWorkflowConfigControlBindings === 'function') {
            normalizeWorkflowConfigControlBindings();
        }
    }, 0);
}

// Test Sub-Agent Modal
let testModal = null;

function showTestModal(agentName, articleId) {
    if (!testModal) {
        testModal = document.createElement('div');
        testModal.id = 'test-subagent-modal';
        testModal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center hidden';
        testModal.innerHTML = `
            <div class="card max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
                <div class="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
                    <h3 class="text-lg font-semibold text-gray-500 dark:text-gray-400" id="test-modal-title">Testing Agent</h3>
                    <button onclick="closeTestModal()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">✕</button>
                </div>
                <div class="flex-1 overflow-y-auto p-4">
                    <div id="test-modal-progress" class="mb-4">
                        <div class="flex items-center gap-2 mb-2">
                            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                            <span class="text-sm text-gray-500 dark:text-gray-400">Dispatching to worker...</span>
                        </div>
                    </div>
                    <div id="test-modal-results" class="hidden">
                        <h4 class="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-2">Results:</h4>
                        <pre id="test-modal-results-content" class="bg-gray-50 dark:bg-gray-900 p-3 rounded border border-gray-200 dark:border-gray-700 text-xs overflow-x-auto text-gray-500 dark:text-gray-400"></pre>
                    </div>
                </div>
                <div class="p-4 border-t border-gray-200 dark:border-gray-700">
                    <div id="test-modal-actions" class="flex gap-2">
                        <button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(testModal);
        
        // Register with ModalManager for proper Escape key handling
        if (window.ModalManager) {
            window.ModalManager.register('test-subagent-modal', {
                isDynamic: true,
                hasInput: false
            });
        }
        
        // Close on backdrop click
        testModal.addEventListener('click', (e) => {
            if (e.target === testModal) {
                closeTestModal();
            }
        });
    }
    
    const titleEl = document.getElementById('test-modal-title');
    if (!titleEl) {
        testModal = null;
        showTestModal(agentName, articleId);
        return;
    }
    titleEl.textContent = `Testing ${agentName} on Article ${articleId}`;
    const progressEl = document.getElementById('test-modal-progress');
    const resultsEl = document.getElementById('test-modal-results');
    if (progressEl) progressEl.classList.remove('hidden');
    if (resultsEl) resultsEl.classList.add('hidden');
    
    // Open via ModalManager for proper stack management
    if (window.ModalManager) {
        window.ModalManager.open('test-subagent-modal');
    } else {
        testModal.classList.remove('hidden');
    }
}

function closeTestModal() {
    if (window.ModalManager && testModal && testModal.id) {
        window.ModalManager.close(testModal.id);
    } else if (testModal) {
        testModal.classList.add('hidden');
    }
}

// Poll test status until complete
async function pollTestStatus(taskId, agentName, articleId) {
    const maxAttempts = 120; // 10 minutes max (5s intervals)
    let attempts = 0;
    
    const pollInterval = setInterval(async () => {
        attempts++;
        
        try {
            const response = await fetch(`/api/workflow/config/test-status/${taskId}`);
            const data = await response.json();
            
            if (data.status === 'completed') {
                clearInterval(pollInterval);
                
                // Hide progress, show results
                document.getElementById('test-modal-progress').classList.add('hidden');
                const resultsDiv = document.getElementById('test-modal-results');
                resultsDiv.classList.remove('hidden');
                
                const resultsContent = document.getElementById('test-modal-results-content');
                
                if (data.result && data.result.success) {
                    const payload = data.result.result || data.result;
                    let displayText = '';
                    
                    // Special handling for SigmaAgent - extract LLM response from conversation log
                    if (agentName === 'SigmaAgent' && payload && typeof payload === 'object') {
                        if (payload.metadata && payload.metadata.conversation_log && Array.isArray(payload.metadata.conversation_log)) {
                            // Get the last conversation log entry (most recent attempt)
                            const lastEntry = payload.metadata.conversation_log[payload.metadata.conversation_log.length - 1];
                            if (lastEntry && lastEntry.llm_response) {
                                displayText = lastEntry.llm_response.trim();
                            }
                        }
                    }
                    
                    // Fallback to standard extraction for other agents or if SigmaAgent extraction failed
                    if (!displayText && payload && typeof payload === 'object') {
                        if (payload.llm_response) {
                            displayText = payload.llm_response.trim();
                        } else if (typeof payload._llm_response === 'string') {
                            displayText = payload._llm_response.trim();
                        } else if (payload.raw_response) {
                            displayText = payload.raw_response.trim();
                        }
                    }
                    
                    // Last resort: show full JSON only if no LLM response found
                    if (!displayText) {
                        displayText = JSON.stringify(payload, null, 2);
                    }

                    // Pretty-print for readability: extractors return compact, single-line
                    // JSON strings in llm_response/raw_response. Re-indent if it parses as JSON;
                    // leave non-JSON responses (e.g. SigmaAgent YAML/prose) untouched.
                    try {
                        displayText = JSON.stringify(JSON.parse(displayText), null, 2);
                    } catch (e) {
                        // Not JSON — keep the original text as-is.
                    }

                    resultsContent.textContent = displayText;
                    resultsContent.className = 'bg-green-50 dark:bg-green-900/20 p-3 rounded border border-green-200 dark:border-green-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
                } else {
                    const errorMsg = data.result?.error || data.error || 'Unknown error';
                    resultsContent.textContent = `Error: ${errorMsg}`;
                    resultsContent.className = 'bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-200 dark:border-red-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
                }
                
                document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
                
            } else if (data.status === 'failed') {
                clearInterval(pollInterval);
                
                document.getElementById('test-modal-progress').classList.add('hidden');
                const resultsDiv = document.getElementById('test-modal-results');
                resultsDiv.classList.remove('hidden');
                const resultsContent = document.getElementById('test-modal-results-content');
                resultsContent.textContent = `Error: ${data.error || 'Test failed'}`;
                resultsContent.className = 'bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-200 dark:border-red-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
                document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
                
            } else if (data.status === 'pending') {
                // Still running, update progress message
                const progressDiv = document.getElementById('test-modal-progress');
                const progressText = progressDiv.querySelector('span');
                if (progressText) {
                    progressText.textContent = `Test is running in worker... (${attempts * 5}s)`;
                }
            }
            
            // Timeout after max attempts
            if (attempts >= maxAttempts) {
                clearInterval(pollInterval);
                document.getElementById('test-modal-progress').classList.add('hidden');
                const resultsDiv = document.getElementById('test-modal-results');
                resultsDiv.classList.remove('hidden');
                const resultsContent = document.getElementById('test-modal-results-content');
                resultsContent.textContent = `Error: Test timed out after ${maxAttempts * 5} seconds. The task may still be running in the worker.`;
                resultsContent.className = 'bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded border border-yellow-200 dark:border-yellow-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
                document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
            }
            
        } catch (error) {
            clearInterval(pollInterval);
            document.getElementById('test-modal-progress').classList.add('hidden');
            const resultsDiv = document.getElementById('test-modal-results');
            resultsDiv.classList.remove('hidden');
            const resultsContent = document.getElementById('test-modal-results-content');
            resultsContent.textContent = `Error polling status: ${error.message}`;
            resultsContent.className = 'bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-200 dark:border-red-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
            document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
        }
    }, 5000); // Poll every 5 seconds
}

async function promptForArticleId(defaultId = 2155) {
    const articleId = await ModalManager.prompt('Enter article ID to test with:', defaultId.toString(), { title: 'Test Article', confirmText: 'Test', placeholder: 'Article ID' });
    if (articleId === null) return null; // User cancelled
    const parsedId = parseInt(articleId, 10);
    if (isNaN(parsedId) || parsedId <= 0) {
        showNotification('Please enter a valid article ID (positive number)', 'error');
        return null;
    }
    return parsedId;
}

async function promptAndTestSubAgent(agentName) {
    const articleId = await promptForArticleId();
    if (articleId !== null) {
        await testSubAgent(agentName, articleId);
    }
}

async function promptAndTestRankAgent() {
    const articleId = await promptForArticleId();
    if (articleId !== null) {
        await testRankAgent(articleId);
    }
}

async function promptAndTestSigmaAgent() {
    const articleId = await promptForArticleId();
    if (articleId !== null) {
        await testSigmaAgent(articleId);
    }
}

function getContentFilterSettings() {
    const junkFilterThreshold = parseFloat(document.getElementById('junkFilterThreshold')?.value || '0.8');
    // Content filter is enabled by default, check if there's a toggle (if not, assume enabled)
    const useJunkFilter = true; // Always use content filter based on user's request
    return {
        use_junk_filter: useJunkFilter,
        junk_filter_threshold: junkFilterThreshold
    };
}

async function testSubAgent(agentName, articleId) {
    showTestModal(agentName, articleId);
    
    const filterSettings = getContentFilterSettings();
    
    try {
        // Dispatch test task to worker
        const response = await fetch('/api/workflow/config/test-subagent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_name: agentName,
                article_id: articleId,
                use_junk_filter: filterSettings.use_junk_filter,
                junk_filter_threshold: filterSettings.junk_filter_threshold
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to start test');
        }
        
        const data = await response.json();
        const taskId = data.task_id;
        
        if (!taskId) {
            throw new Error('No task ID returned from server');
        }
        
        // Poll for results
        await pollTestStatus(taskId, agentName, articleId);
        
    } catch (error) {
        document.getElementById('test-modal-progress').classList.add('hidden');
        const resultsDiv = document.getElementById('test-modal-results');
        resultsDiv.classList.remove('hidden');
        const resultsContent = document.getElementById('test-modal-results-content');
        resultsContent.textContent = `Error: ${error.message}`;
        resultsContent.className = 'bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-200 dark:border-red-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
        document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
    }
}

async function testRankAgent(articleId) {
    showTestModal('RankAgent', articleId);
    
    const filterSettings = getContentFilterSettings();
    
    try {
        // Dispatch test task to worker
        const response = await fetch('/api/workflow/config/test-rankagent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                article_id: articleId,
                use_junk_filter: filterSettings.use_junk_filter,
                junk_filter_threshold: filterSettings.junk_filter_threshold
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to start test');
        }
        
        const data = await response.json();
        const taskId = data.task_id;
        
        if (!taskId) {
            throw new Error('No task ID returned from server');
        }
        
        // Poll for results
        await pollTestStatus(taskId, 'RankAgent', articleId);
        
    } catch (error) {
        document.getElementById('test-modal-progress').classList.add('hidden');
        const resultsDiv = document.getElementById('test-modal-results');
        resultsDiv.classList.remove('hidden');
        const resultsContent = document.getElementById('test-modal-results-content');
        resultsContent.textContent = `Error: ${error.message}`;
        resultsContent.className = 'bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-200 dark:border-red-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
        document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
    }
}

async function testSigmaAgent(articleId) {
    showTestModal('SigmaAgent', articleId);

    const filterSettings = getContentFilterSettings();

    try {
        // Get SigmaAgent model from config
        const configAgentModels = currentConfig?.agent_models || agentModels || {};
        const sigmaModel = configAgentModels['SigmaAgent'];
        const sigmaProvider = configAgentModels['SigmaAgent_provider'] || getDefaultProvider();
        
        // If using LMStudio, check if model is loaded and load it if needed
        if (sigmaProvider === 'lmstudio' && sigmaModel) {
            try {
                // Try a quick test request to check if model is loaded
                const testResponse = await fetch('http://localhost:1234/v1/chat/completions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        model: sigmaModel,
                        messages: [{ role: 'user', content: 'test' }],
                        max_tokens: 5,
                        temperature: 0
                    }),
                    signal: AbortSignal.timeout(5000) // 5 second timeout
                });
                
                if (testResponse.status !== 200) {
                    const errorData = await testResponse.json().catch(() => ({}));
                    const errorMsg = errorData?.error?.message || '';
                    
                    // Check if error indicates model not loaded
                    if (errorMsg.toLowerCase().includes('no models loaded') || 
                        errorMsg.toLowerCase().includes('model') && errorMsg.toLowerCase().includes('not loaded')) {
                        console.log(`Model ${sigmaModel} not loaded, loading now...`);
                        
                        // Update modal to show loading status
                        const progressDiv = document.getElementById('test-modal-progress');
                        if (progressDiv) {
                            progressDiv.innerHTML = '<p class="text-sm text-gray-600 dark:text-gray-400">Loading model... This may take a moment.</p>';
                        }
                        
                        // Load the model
                        const loadResponse = await fetch('/api/load-lmstudio-model', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                model_name: sigmaModel,
                                context_length: 16384 // Default context length for SIGMA
                            })
                        });
                        
                        if (!loadResponse.ok) {
                            const loadError = await loadResponse.json();
                            throw new Error(`Failed to load model: ${loadError.detail || 'Unknown error'}`);
                        }
                        
                        const loadData = await loadResponse.json();
                        console.log(`Model loaded: ${loadData.message}`);
                        
                        // Wait a moment for model to be ready
                        await new Promise(resolve => setTimeout(resolve, 2000));
                    }
                }
            } catch (testError) {
                // If test request fails (timeout, connection error, etc.), try loading anyway
                if (testError.name === 'TimeoutError' || testError.name === 'TypeError') {
                    console.log(`Could not verify model status, attempting to load ${sigmaModel}...`);
                    
                    const progressDiv = document.getElementById('test-modal-progress');
                    if (progressDiv) {
                        progressDiv.innerHTML = '<p class="text-sm text-gray-600 dark:text-gray-400">Loading model... This may take a moment.</p>';
                    }
                    
                    const loadResponse = await fetch('/api/load-lmstudio-model', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            model_name: sigmaModel,
                            context_length: 16384
                        })
                    });
                    
                    if (!loadResponse.ok) {
                        const loadError = await loadResponse.json();
                        throw new Error(`Failed to load model: ${loadError.detail || 'Unknown error'}`);
                    }
                    
                    await new Promise(resolve => setTimeout(resolve, 2000));
                } else {
                    // Other errors (like network issues) - log but continue
                    console.warn('Could not check model status:', testError);
                }
            }
        }
        
        // Dispatch test task to worker
        const response = await fetch('/api/workflow/config/test-sigmaagent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                article_id: articleId,
                use_junk_filter: filterSettings.use_junk_filter,
                junk_filter_threshold: filterSettings.junk_filter_threshold
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to start test');
        }

        const data = await response.json();
        const taskId = data.task_id;
        
        if (!taskId) {
            throw new Error('No task ID returned from server');
        }
        
        // Poll for results
        await pollTestStatus(taskId, 'SigmaAgent', articleId);
        
    } catch (error) {
        document.getElementById('test-modal-progress').classList.add('hidden');
        const resultsDiv = document.getElementById('test-modal-results');
        resultsDiv.classList.remove('hidden');
        const resultsContent = document.getElementById('test-modal-results-content');
        resultsContent.textContent = `Error: ${error.message}`;
        resultsContent.className = 'bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-200 dark:border-red-800 text-xs overflow-x-auto text-gray-500 dark:text-gray-400';
        document.getElementById('test-modal-actions').innerHTML = '<button onclick="closeTestModal()" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md text-sm">Close</button>';
    }
}

// Auto-save model changes immediately
// Unified autosave function for all config changes (except prompts which require manual save)
window.autoSaveConfig = async function autoSaveConfig() {
    // Skip autosave during page initialization to prevent version jumps
    if (isInitializing) {
        console.log('Skipping autosave during initialization');
        return;
    }
    // Skip autosave during prompt save - prevents overwriting freshly saved prompt
    if (isSavingPrompt) {
        console.log('Skipping autosave during prompt save');
        return;
    }
    
    // Debounce autosave to prevent too many requests
    if (autoSaveTimeout) {
        clearTimeout(autoSaveTimeout);
    }
    
    // Return a promise that resolves when the debounced save completes
    return new Promise((resolve, reject) => {
        autoSaveTimeout = setTimeout(async () => {
            try {
                await performAutoSave();
                resolve();
            } catch (error) {
                reject(error);
            }
        }, 300); // 300ms debounce
    });
}

// Actual autosave implementation (separated for debouncing)
async function performAutoSave() {
    try {
        // Validate all provider/model combinations before saving.
        // Only block if a model was NEWLY changed to an invalid value -- a pre-existing
        // invalid model in the DB (e.g. from a prior session) must not block unrelated
        // threshold/toggle autosaves.
        let hasValidationErrors = false;
        // Only run the validation check when we have a loaded baseline config.
        // If currentConfig is null (server restarted, config not yet loaded) we
        // cannot distinguish "newly changed" from "pre-existing" -- skip the block
        // and let the save proceed; the backend enforces its own validation on PUT.
        if (currentConfig && currentConfig.agent_models) {
            Object.values(AGENT_CONFIG).forEach(config => {
                const provider = getAgentProvider(config.prefix) || getDefaultProvider();
                const model = getAgentModel(config.prefix, provider);
                if (model && !validateProviderModelCombination(config.prefix, provider, model)) {
                    // Only block if this model value differs from what is already stored.
                    // If it matches, the error is pre-existing -- let the save proceed.
                    const storedModel = currentConfig.agent_models[config.modelKey];
                    if (model !== storedModel) {
                        hasValidationErrors = true;
                    }
                }
            });
        }

        // If validation errors exist, don't save (throttle warn to avoid console spam)
        if (hasValidationErrors) {
            const now = Date.now();
            if (!isInitializing && (now - lastValidationWarnAt) >= VALIDATION_WARN_THROTTLE_MS) {
                lastValidationWarnAt = now;
                console.warn('Auto-save skipped: Invalid provider/model combinations detected');
            }
            return;
        }

        // Get current config to preserve other settings
        if (!currentConfig) {
            // Load config first if not available
            const configResponse = await fetch('/api/workflow/config');
            if (configResponse.ok) {
                currentConfig = await configResponse.json();
            } else {
                console.error('Failed to load current config for auto-save');
                return;
            }
        }
        
        // Collect all agent configs using unified system
        const collectedAgentConfigs = collectAllAgentConfigs();
        
        const agentModelsData = {
            ...collectedAgentConfigs,
            OSDetectionAgent_selected_os: ['Windows']
        };
        
        // Remove null/empty string values (but keep 0.0 for temperature)
        // CRITICAL: RankAgent must be included if it has a value (even if empty string, to override env var)
        const cleanedAgentModels = {};
        // Get RankAgent value from collected configs, with fallback to direct form read
        let rankModelValue = collectedAgentConfigs.RankAgent;
        if (rankModelValue === undefined || rankModelValue === null) {
            // Fallback: read directly from form element
            const rankProvider = getAgentProvider('rankagent') || getDefaultProvider();
            rankModelValue = getAgentModel('rankagent', rankProvider);
        }
        
        for (const [key, value] of Object.entries(agentModelsData)) {
            // Always include RankAgent if it has a value (non-null, even if empty string)
            if (key === 'RankAgent') {
                // Prefer rankModelValue if it's a valid string, otherwise use value from agentModelsData
                // Empty string is valid (means clear/use fallback), but null/undefined means not set
                const finalRankValue = (rankModelValue !== null && rankModelValue !== undefined) 
                    ? rankModelValue 
                    : (value !== null && value !== undefined ? value : null);
                // Include RankAgent if we have a value (including empty string to clear it)
                if (finalRankValue !== null && finalRankValue !== undefined) {
                    cleanedAgentModels[key] = finalRankValue;
                } else if (currentConfig?.agent_models?.RankAgent) {
                    // Preserve existing value if form field is empty but config has a value
                    // This prevents accidentally clearing the model when form hasn't loaded yet
                    cleanedAgentModels[key] = currentConfig.agent_models.RankAgent;
                }
            } else if (value !== null && value !== '') {
                cleanedAgentModels[key] = value;
            }
        }

        // Collect thresholds (only if valid)
        const junkFilterInput = document.getElementById('junkFilterThreshold');
        const rankingInput = document.getElementById('rankingThreshold');
        const similarityInput = document.getElementById('similarityThreshold');
        
        // Only save thresholds if they're valid (to avoid saving invalid intermediate values)
        let junkFilterThreshold = currentConfig.junk_filter_threshold ?? 0.8;
        let rankingThreshold = currentConfig.ranking_threshold ?? 6.0;
        let similarityThreshold = currentConfig.similarity_threshold ?? 0.5;
        
        if (junkFilterInput && validateThreshold(junkFilterInput, 0, 1)) {
            junkFilterThreshold = parseFloat(junkFilterInput.value);
        }
        if (rankingInput && validateThreshold(rankingInput, 0, 10)) {
            rankingThreshold = parseFloat(rankingInput.value);
        }
        if (similarityInput && validateThreshold(similarityInput, 0, 1)) {
            similarityThreshold = parseFloat(similarityInput.value);
        }
        
        const rankAgentEnabled = document.getElementById('rank-agent-enabled')?.checked ?? true;

        // Collect disabled extract agents
        const disabledFromDOM = [];
        EXTRACT_SUB_AGENTS.forEach(agentName => {
            const checkbox = document.getElementById(`toggle-${agentName.toLowerCase()}-enabled`);
            if (checkbox && !checkbox.checked) {
                disabledFromDOM.push(agentName);
            }
        });
        disabledExtractAgents = new Set(disabledFromDOM);
        
        // Collect other toggles
        const sigmaFallbackEnabled = document.getElementById('sigma-fallback-enabled')?.checked || false;
        const cmdlineAttentionPreprocessorEnabled = document.getElementById('cmdline-attention-preprocessor-enabled')?.checked !== false;
        const procTreeAttentionPreprocessorEnabled = document.getElementById('proctree-attention-preprocessor-enabled')?.checked !== false;
        
        // Merge agent_prompts and include disabled extract agents
        const promptsSource = {
            ...(currentConfig?.agent_prompts || {}),
            ...(agentPrompts || {})
        };
        const promptsCopy = JSON.parse(JSON.stringify(promptsSource || {}));
        // Strip the per-agent 'model' sibling -- model selection lives in
        // agent_models.X and duplicating it inside agent_prompts.X produces
        // shape-5 records that confuse parse_sigma_agent_prompt_data and
        // the rank/sigma readers. Skip ExtractAgentSettings (its 'model'
        // semantic differs -- it's a settings container, not a prompt).
        for (const key of Object.keys(promptsCopy)) {
            if (key === 'ExtractAgentSettings') continue;
            if (promptsCopy[key] && typeof promptsCopy[key] === 'object' && 'model' in promptsCopy[key]) {
                delete promptsCopy[key].model;
            }
        }
        const extractSettings = promptsCopy.ExtractAgentSettings ? { ...promptsCopy.ExtractAgentSettings } : {};
        extractSettings.disabled_agents = disabledFromDOM;
        promptsCopy.ExtractAgentSettings = extractSettings;
        
        // Build update payload with all config fields
        const updateData = {
            min_hunt_score: currentConfig.min_hunt_score ?? 97.0,
            ranking_threshold: rankingThreshold,
            similarity_threshold: similarityThreshold,
            junk_filter_threshold: junkFilterThreshold,
            description: currentConfig.description || null,
            agent_models: (Object.keys(cleanedAgentModels).length > 0 || cleanedAgentModels.RankAgent !== undefined) ? cleanedAgentModels : null,
            sigma_fallback_enabled: sigmaFallbackEnabled,
            rank_agent_enabled: rankAgentEnabled,
            cmdline_attention_preprocessor_enabled: cmdlineAttentionPreprocessorEnabled,
            proc_tree_attention_preprocessor_enabled: procTreeAttentionPreprocessorEnabled,
            agent_prompts: promptsCopy
        };
        
        const response = await fetch('/api/workflow/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });
        
        if (response.ok) {
            const updatedConfig = await response.json();
            
            currentConfig = updatedConfig;
            agentModels = updatedConfig.agent_models || {};
            agentPrompts = updatedConfig.agent_prompts || agentPrompts || {};
            
            // Update disabledExtractAgents from response, but DON'T sync toggles from config
            // The DOM state is already correct (user just changed it), and syncing would overwrite it
            // Only update the internal state to match what was saved
            const savedDisabledAgents = getDisabledExtractAgentsFromConfig(updatedConfig);
            disabledExtractAgents = new Set(savedDisabledAgents);
            
            // Don't call syncExtractAgentTogglesFromConfig() here - it would overwrite user's toggle state
            // The DOM checkboxes are already in the correct state from the user's action
            
            console.log('✅ Config auto-saved successfully');
            
            // Sync dirty-tracking baseline to the new config so the save button disables again
            resetOriginalConfigStateFromCurrent();
            updateSaveButtonState();
            
            // Refresh prompt displays to show updated model values
            if (agentPrompts && Object.keys(agentPrompts).length > 0) {
                renderAgentPrompts();
            }
            
            // Update config display to show current UI state
            if (typeof updateConfigDisplay === 'function') {
                updateConfigDisplay();
            }
        } else {
            const error = await response.json();
            const errorMessage = error.detail || 'Unknown error';
            console.error('❌ Failed to auto-save config:', errorMessage);
            console.error('Response status:', response.status);
            console.error('Response body:', error);
            // Don't throw - just log the error to avoid breaking the UI
            // The user can still manually save if autosave fails
        }
    } catch (error) {
        console.error('Error auto-saving config:', error);
        // Don't throw - just log the error to avoid breaking the UI
    }
}

// Legacy function name for backward compatibility
/**
 * Updates temperature input max value based on provider
 * Anthropic: max 1, LMStudio: max 1, OpenAI: max 2
 */
function updateTemperatureLimit(agentPrefix, provider) {
    const temperatureInput = document.getElementById(`${agentPrefix}-temperature`);
    if (!temperatureInput) return;
    
    // LMStudio and Anthropic both have max 1.0, OpenAI has max 2.0
    const maxTemp = (provider === 'anthropic' || provider === 'lmstudio') ? 1 : 2;
    const currentValue = parseFloat(temperatureInput.value) || 0;
    
    temperatureInput.setAttribute('max', maxTemp);
    
    // Clamp value if it exceeds new max
    if (currentValue > maxTemp) {
        temperatureInput.value = maxTemp;
        // Only trigger save if not initializing (to avoid save loops during page load)
        if (!isInitializing && typeof autoSaveModelChange === 'function') {
            autoSaveModelChange();
        }
    }
    
    // Update help text if present
    const helpText = temperatureInput.parentElement?.querySelector('p.text-xs');
    if (helpText) {
        const range = maxTemp === 1 ? '0.0-1.0' : '0.0-2.0';
        helpText.textContent = helpText.textContent.replace(/0\.0-\d+\.\d+/, range);
    }
}

/**
 * Validates and clamps all temperature inputs based on their provider
 * Called on page load to fix any invalid values
 */
function validateAllTemperatureInputs() {
    // Check all agents in AGENT_CONFIG
    Object.values(AGENT_CONFIG).forEach(config => {
        if (config.temperatureKey) {
            const provider = getAgentProvider(config.prefix) || getDefaultProvider();
            updateTemperatureLimit(config.prefix, provider);
        }
    });
    
    // Check sub-agents
    const subAgents = ['cmdlineextract', 'proctreeextract', 'huntqueriesextract', 'registryextract', 'servicesextract', 'scheduledtasksextract', 'networkindicatorextract'];

    subAgents.forEach(prefix => {
        const provider = getAgentProvider(prefix) || getDefaultProvider();
        updateTemperatureLimit(prefix, provider);
    });
}

// OpenAI reasoning models that reject variable temperature -- mirrors _OPENAI_REASONING_PREFIXES in model_validation.py.
const OPENAI_REASONING_PREFIXES = ['o1', 'o3', 'o4-mini', 'o4-', 'o4', 'gpt-5'];

function isOpenAIReasoningModel(modelName) {
    if (!modelName) return false;
    const m = modelName.trim().toLowerCase();
    return OPENAI_REASONING_PREFIXES.some(p => m.startsWith(p));
}

/**
 * Disables or enables the temperature slider for an agent based on whether the
 * currently selected model supports variable temperature. For reasoning models
 * (o1/o3/o4/gpt-5.x) the slider is locked at 0 and a hint is shown.
 */
function updateTemperatureCapabilityUI(agentPrefix) {
    const provider = getAgentProvider(agentPrefix) || getDefaultProvider();
    const model = getAgentModel(agentPrefix, provider);
    const slider = document.getElementById(`${agentPrefix}-temperature`);
    if (!slider) return;

    const isReasoning = provider === 'openai' && isOpenAIReasoningModel(model);
    const hintId = `${agentPrefix}-temperature-reasoning-hint`;
    let hint = document.getElementById(hintId);

    if (isReasoning) {
        slider.disabled = true;
        slider.value = '0';
        slider.style.opacity = '0.4';
        slider.style.cursor = 'not-allowed';
        const valueSpan = document.getElementById(`${agentPrefix}-temperature-value`);
        if (valueSpan) valueSpan.textContent = '0';
        if (!hint) {
            hint = document.createElement('p');
            hint.id = hintId;
            hint.className = 'text-[10px] text-amber-500 dark:text-amber-400 mt-1';
            hint.textContent = 'Temperature not supported for reasoning models';
            slider.parentElement && slider.parentElement.appendChild(hint);
        }
        hint.classList.remove('hidden');
    } else {
        slider.disabled = false;
        slider.style.opacity = '';
        slider.style.cursor = '';
        if (hint) hint.classList.add('hidden');
    }
}

/**
 * Validates model for a specific agent and provides immediate feedback
 * Can be called from model input onchange/oninput handlers
 */
function validateAgentModelOnChange(agentPrefix) {
    const provider = getAgentProvider(agentPrefix) || getDefaultProvider();
    const model = getAgentModel(agentPrefix, provider);
    updateTemperatureCapabilityUI(agentPrefix);
    return validateProviderModelCombination(agentPrefix, provider, model);
}

/**
 * Validates and saves model changes. Debounced to avoid repeated validation/warns on every input.
 * Wraps autoSaveConfig with validation.
 */
window.autoSaveModelChange = function() {
    if (autoSaveModelChangeTimeout) clearTimeout(autoSaveModelChangeTimeout);
    return new Promise((resolve) => {
        autoSaveModelChangeTimeout = setTimeout(() => {
            autoSaveModelChangeTimeout = null;
            if (isInitializing) {
                resolve();
                return;
            }
            updateSubAgentInheritanceHints();
            // Validate agent models before saving.
            // Only block if a model was NEWLY changed to an invalid value -- a pre-existing
            // invalid model in the DB must not block unrelated parameter autosaves.
            // When currentConfig is not yet loaded, skip validation (no baseline to compare).
            let hasErrors = false;
            if (currentConfig && currentConfig.agent_models) {
                Object.values(AGENT_CONFIG).forEach(config => {
                    const provider = getAgentProvider(config.prefix) || getDefaultProvider();
                    const model = getAgentModel(config.prefix, provider);
                    if (model && !validateProviderModelCombination(config.prefix, provider, model)) {
                        const storedModel = currentConfig.agent_models[config.modelKey];
                        if (model !== storedModel) {
                            hasErrors = true;
                        }
                    }
                });
            }
            if (!hasErrors) {
                window.autoSaveConfig().then(resolve).catch(() => resolve());
            } else {
                const now = Date.now();
                if ((now - lastValidationWarnAt) >= VALIDATION_WARN_THROTTLE_MS) {
                    lastValidationWarnAt = now;
                    console.warn('Model change validation failed - not saving');
                }
                resolve();
            }
        }, 400);
    });
};

async function loadAgentPrompts() {
    try {
        console.log('🔄 Loading agent prompts from API...');
        // Add cache-busting to ensure fresh data
        const response = await fetch('/api/workflow/config/prompts?' + new Date().getTime(), {
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache'
            }
        });
        if (response.ok) {
            const data = await response.json();
            const oldPrompts = JSON.stringify(agentPrompts);
            const fetched = data.prompts || {};
            // CRITICAL: If we just saved a prompt, a stale loadAgentPrompts (from initial load) may
            // complete after our save and overwrite with pre-save data. Preserve our saved agent.
            if (lastSavedPromptAgent && (Date.now() - lastPromptSaveAt) < 3000) {
                agentPrompts = { ...fetched, [lastSavedPromptAgent]: agentPrompts[lastSavedPromptAgent] };
            } else {
                agentPrompts = fetched;
            }
            const newPrompts = JSON.stringify(agentPrompts);
            console.log('📥 Loaded prompts:', {
                agent_count: Object.keys(agentPrompts).length,
                has_cmdline: !!agentPrompts['CmdlineExtract'],
                cmdline_prompt_length: agentPrompts['CmdlineExtract']?.prompt?.length || 0,
                data_changed: oldPrompts !== newPrompts
            });
            if (agentPrompts['CmdlineExtract']) {
                const prompt = agentPrompts['CmdlineExtract'].prompt || '';
                console.log('📝 CmdlineExtract prompt preview:', prompt.substring(0, 150));
                try {
                    const parsed = JSON.parse(prompt);
                    console.log('📝 CmdlineExtract User (user_template):', parsed.user_template?.substring(0, 50) || 'empty');
                } catch (e) {
                    console.log('📝 CmdlineExtract prompt (not JSON):', prompt.substring(0, 100));
                }
            }
            // Wait for containers to exist before rendering
            const waitForContainers = (retries = 10) => {
                const container = document.getElementById('cmdlineextract-agent-prompt-container');
                if (container || retries === 0) {
            renderAgentPrompts();
                    console.log('✅ Prompts rendered to UI');
                } else {
                    setTimeout(() => waitForContainers(retries - 1), 100);
                }
            };
            waitForContainers();
        } else {
            console.error('❌ Failed to load prompts:', response.status, response.statusText);
        }
    } catch (error) {
        console.error('❌ Error loading agent prompts:', error);
    }
}

function renderAgentPrompts() {
    // Render Rank Agent Prompt
    const rankPromptContainer = document.getElementById('rank-agent-prompt-container');
    if (rankPromptContainer) {
        const promptData = getOrCreatePromptData('RankAgent');
        rankPromptContainer.innerHTML = renderSinglePrompt('RankAgent', promptData, 'rank-agent');
        setTimeout(() => {
            if (typeof initCollapsiblePanels === 'function') {
                initCollapsiblePanels(rankPromptContainer);
            }
        }, 0);
    }

    // Render Sub-Agent Prompts
    const subAgents = [
        { name: 'CmdlineExtract', container: 'cmdlineextract-agent-prompt-container', prefix: 'cmdlineextract-agent' },
        { name: 'ProcTreeExtract', container: 'proctreeextract-agent-prompt-container', prefix: 'proctreeextract-agent' },
        { name: 'HuntQueriesExtract', container: 'huntqueriesextract-agent-prompt-container', prefix: 'huntqueriesextract-agent' },
        { name: 'RegistryExtract', container: 'registryextract-agent-prompt-container', prefix: 'registryextract-agent' },
        { name: 'ServicesExtract', container: 'servicesextract-agent-prompt-container', prefix: 'servicesextract-agent' },
        { name: 'ScheduledTasksExtract', container: 'scheduledtasksextract-agent-prompt-container', prefix: 'scheduledtasksextract-agent' },
        { name: 'NetworkIndicatorExtract', container: 'networkindicatorextract-agent-prompt-container', prefix: 'networkindicatorextract-agent' }
    ];

    subAgents.forEach(subAgent => {
        const container = document.getElementById(subAgent.container);
        // Always re-render if container exists (even if prompt data is missing)
        // This ensures the prompt editor is always available
        if (container) {
            // Get current model from UI as fallback
            const currentModelFromUI = getCurrentModelForAgent(subAgent.name);
            const defaultModel = currentModelFromUI || 'Not configured';
            const promptData = agentPrompts[subAgent.name] || { prompt: '', instructions: '', model: defaultModel };
            if (subAgent.name === 'CmdlineExtract') {
                console.log(`🎨 Rendering ${subAgent.name} with prompt data:`, {
                    prompt_length: promptData.prompt?.length || 0,
                    prompt_preview: promptData.prompt?.substring(0, 100) || 'empty',
                    is_editing: editingPrompts[subAgent.name] || false,
                    container_exists: !!container,
                    container_id: subAgent.container
                });
                // Parse and log the actual values being rendered
                if (promptData.prompt) {
                    try {
                        const parsed = JSON.parse(promptData.prompt);
                        console.log(`🎨 ${subAgent.name} parsed User (user_template):`, parsed.user_template?.substring(0, 50) || 'empty');
                    } catch (e) {
                        console.log(`🎨 ${subAgent.name} prompt (not JSON):`, promptData.prompt.substring(0, 100));
                    }
                }
            }
            const renderedHTML = renderSinglePrompt(subAgent.name, promptData, subAgent.prefix);
            container.innerHTML = renderedHTML;
            // Verification code removed - no longer needed
            // Re-initialize collapsible panels after rendering
            setTimeout(() => {
                if (typeof initCollapsiblePanels === 'function') {
                    initCollapsiblePanels(container);
                }
            }, 0);
        } else {
            console.warn(`⚠️ Container not found for ${subAgent.name}:`, subAgent.container);
        }
    });
    
    // Render SIGMA Agent Prompt (always render when container exists, same as Extract/sub-agents)
    const sigmaPromptContainer = document.getElementById('sigma-agent-prompt-container');
    if (sigmaPromptContainer) {
        const promptData = getOrCreatePromptData('SigmaAgent');
        sigmaPromptContainer.innerHTML = renderSinglePrompt('SigmaAgent', promptData, 'sigma-agent');
        setTimeout(() => {
            if (typeof initCollapsiblePanels === 'function') {
                initCollapsiblePanels(sigmaPromptContainer);
            }
        }, 0);
    }
    
    // Re-initialize collapsible panels for dynamically added prompt panels
    if (typeof initCollapsiblePanels === 'function') {
        initCollapsiblePanels();
    }
    if (typeof normalizeWorkflowConfigControlBindings === 'function') {
        normalizeWorkflowConfigControlBindings();
    }
    setTimeout(function () {
        if (typeof initWorkflowConfigAgentAccordion === 'function') {
            initWorkflowConfigAgentAccordion();
        }
    }, 50);
}

function getCurrentModelForAgent(agentName) {
    // Map agent names to ID prefixes used for model inputs
    const agentPrefixMap = {
        'RankAgent': 'rankagent',
        'ExtractAgent': 'extractagent',
        'SigmaAgent': 'sigmaagent',
        'CmdlineExtract': 'cmdlineextract',
        'ProcTreeExtract': 'proctreeextract',
        'HuntQueriesExtract': 'huntqueriesextract',
        'RegistryExtract': 'registryextract',
        'ServicesExtract': 'servicesextract',
        'ScheduledTasksExtract': 'scheduledtasksextract',
        'NetworkIndicatorExtract': 'networkindicatorextract',
        'OSDetectionAgent': 'osdetectionagent'
    };

    const providerSelectMap = {
        'RankAgent': 'rankagent-provider',
        'ExtractAgent': 'extractagent-provider',
        'SigmaAgent': 'sigmaagent-provider',
        'CmdlineExtract': 'cmdlineextract-provider',
        'ProcTreeExtract': 'proctreeextract-provider',
        'HuntQueriesExtract': 'huntqueriesextract-provider',
        'RegistryExtract': 'registryextract-provider',
        'ServicesExtract': 'servicesextract-provider',
        'ScheduledTasksExtract': 'scheduledtasksextract-provider',
        'NetworkIndicatorExtract': 'networkindicatorextract-provider'
    };
    
    const agentPrefix = agentPrefixMap[agentName];
    if (!agentPrefix) return null;
    
    const providerSelectId = providerSelectMap[agentName];
    const provider = providerSelectId ? (document.getElementById(providerSelectId)?.value || getDefaultProvider()) : 'lmstudio';
    
    // Primary: read from the active input for the selected provider
    const activeModel = getActiveAgentModelValue(agentPrefix, provider);
    if (activeModel) return activeModel;
    
    // Sub-agents inherit ExtractAgent model when empty
    const subAgentNames = [...EXTRACT_SUB_AGENTS];
    if (subAgentNames.includes(agentName)) {
        const extractProvider = document.getElementById('extractagent-provider')?.value || getDefaultProvider();
        const extractModel = getActiveAgentModelValue('extractagent', extractProvider);
        if (extractModel) return extractModel;
    }
    
    // OS Detection is deterministic (entity/keyword registry) — no model to report.
    if (agentName === 'OSDetectionAgent') {
        return null;
    }
    
    return null;
}

// Render the parsed fields of a Standard Extractor Contract prompt as readable,
// line-broken labeled blocks for the read-only System Prompt view. The templateData
// values are the PARSED strings (real newlines), unlike the raw config JSON stored in
// promptParts.system where newlines are escaped (\n) and never break under
// whitespace-pre-wrap. Each field is escaped; empty fields are omitted.
function renderExtractorConfigFields(templateData) {
    const td = templateData || {};
    const sections = [
        ['Role', td.role],
        ['Task', td.task],
        ['JSON Example', td.json_example],
        ['Instructions', td.instructions],
    ];
    const blocks = sections
        .filter(([, value]) => value && String(value).trim())
        .map(([label, value]) => `
            <div>
                <div class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">${escapeHtml(label)}</div>
                <div class="font-mono whitespace-pre-wrap break-words text-gray-800 dark:text-gray-200">${escapeHtml(String(value))}</div>
            </div>
        `);
    return blocks.length ? blocks.join('') : '<span class="text-gray-400 italic">(empty)</span>';
}

function renderSinglePrompt(agentName, promptData, prefix) {
    const prompt = promptData.prompt || '';
    const instructions = promptData.instructions || '';
    // Get current model from dropdown first, fall back to promptData.model
    const currentModelFromDropdown = getCurrentModelForAgent(agentName);
    const model = currentModelFromDropdown || promptData.model || 'Not configured';
    const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
    const isEditing = editingPrompts[agentName] || false;
    const panelId = `${prefix}-prompt-panel`;

    // Use the canonical-aware helper so {system, user} outer-dict records
    // (post-migration) hydrate correctly. Legacy records still flow through
    // parsePromptParts on the inner JSON string.
    const promptParts = getAgentPromptParts(agentName);
    const isTemplateFormat = promptParts.isTemplateFormat;
    const templateData = promptParts.templateData || {};

    // One-time migration: for agents whose user scaffold is now locked, if the DB has empty
    // role/system but non-empty user content, treat the user content as the persona. This
    // surfaces misplaced persona text in the editable System Prompt field so the user can
    // save it back into the correct slot. Only applies when role/system is truly empty so
    // we never overwrite legitimate persona content.
    const userLooksLikeJson = (typeof promptParts.user === 'string')
        && promptParts.user.trim().startsWith('{')
        && promptParts.user.trim().endsWith('}');
    if (isLockedExtractorPrompt(agentName)
        && !promptParts.system
        && promptParts.user
        && !userLooksLikeJson
        && promptParts.user !== getLockedUserTemplate(agentName)) {
        promptParts.system = promptParts.user;
        promptParts.user = '';
    }
    
    // Debug logging for prompt parsing
    if (agentName === 'CmdlineExtract') {
        console.log(`🔍 [renderSinglePrompt] ${agentName}:`, {
            prompt_length: prompt.length,
            prompt_preview: prompt.substring(0, 100),
            parsed_system: promptParts.system?.substring(0, 50) || 'empty',
            parsed_system_length: promptParts.system?.length || 0,
            parsed_user: promptParts.user?.substring(0, 50) || 'empty',
            parsed_user_length: promptParts.user?.length || 0,
            is_template: isTemplateFormat,
            is_editing: isEditing,
            will_display_system: !isEditing ? (promptParts.system || '(empty)') : 'N/A (editing)',
            will_display_user: !isEditing ? (promptParts.user || '(empty)') : 'N/A (editing)'
        });
    }
    
    // Check if this is one of the locked extractor prompts
    const isExtractionAgent = isLockedExtractorPrompt(agentName);
    const isLockedScaffoldAgent = isExtractionAgent || isLockedCanonicalPrompt(agentName);

    // Standard Extractor Contract prompts (CmdlineExtract, ProcTreeExtract, ...) store the
    // raw config JSON in promptParts.system so Save round-trips it verbatim. Rendering that
    // raw JSON read-only produces a wall of text (escaped \n never break under
    // whitespace-pre-wrap). When viewing (not editing) such a prompt, render the parsed
    // templateData fields instead. The edit textarea and save path are untouched.
    const systemIsConfigJson = typeof promptParts.system === 'string'
        && promptParts.system.trim().startsWith('{');
    const showReadableExtractorConfig = !isEditing && isTemplateFormat && systemIsConfigJson;
    const systemDisplayHtml = showReadableExtractorConfig
        ? `<div id="${agentId}-prompt-system-display-2" class="text-sm space-y-4 bg-gray-50 dark:bg-gray-900 border-l-4 border-blue-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md max-h-96 overflow-y-auto leading-relaxed text-gray-800 dark:text-gray-200">${renderExtractorConfigFields(templateData)}</div>`
        : `<div id="${agentId}-prompt-system-display-2" class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border-l-4 border-blue-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto leading-relaxed ${!promptParts.system ? 'text-gray-400 italic' : 'text-gray-800 dark:text-gray-200'}">${escapeHtml(promptParts.system || '(empty)')}</div>`;

    return `
        <div id="${panelId}-root" class="border border-gray-200 dark:border-gray-700 rounded-lg">
            <div data-collapsible-panel="${panelId}" class="w-full flex items-center justify-between p-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700 rounded-t-lg transition-colors cursor-pointer" style="background-color: var(--panel-header);">
                <div class="flex items-center gap-3">
                    <h4 class="text-sm font-semibold" style="color: var(--text-primary) !important;">${escapeHtml(agentName)} Prompt</h4>
                    <span class="text-xs text-gray-500 dark:text-gray-400">Model: <span class="font-mono">${escapeHtml(model)}</span></span>
                </div>
                <span id="${panelId}-toggle" class="text-gray-700 dark:text-gray-200 text-sm font-medium transform transition-transform" aria-hidden="true">${isEditing ? '▲' : '▼'}</span>
            </div>
            <div id="${panelId}-content" class="${isEditing ? '' : 'hidden'} p-4 border-t border-gray-200 dark:border-gray-700">
                <div class="bg-gray-50 rounded-lg p-4 border border-gray-200 dark:border-gray-700" style="background: var(--panel-bg-5) !important;">
                    <div class="flex items-center justify-between mb-3">
                        <div>
                            <p class="text-xs text-gray-500 dark:text-gray-400">Model: <span class="font-mono">${escapeHtml(model)}</span></p>
                        </div>
                        <div class="flex gap-2">
                            <button type="button" onclick="openExpandedPromptEditor('${agentName}')"
                                    class="btn-toggle"
                                    title="Expand to full-page editor">
                                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5"/></svg>
                                Expand
                            </button>
                            <button type="button" onclick="validateAgentPrompt('${agentName}')"
                                    class="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 text-white text-sm rounded-md transition-colors"
                                    title="Validate prompt structure against runtime requirements">
                                Validate
                            </button>
                            ${isEditing ? `
                                <button type="button" onclick="cancelEditPrompt2('${agentName}')"
                                        class="px-3 py-1 text-sm border border-gray-600 hover:bg-gray-800 text-gray-300 rounded-md">
                                    Cancel
                                </button>
                                <button type="button" onclick="showEffectivePrompt('${agentName}')"
                                        class="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-md transition-colors"
                                        style="display: none;"
                                        title="Preview the full message pair (system + hard-coded user template) that will be sent to the LLM">
                                    👁️ Effective Prompt
                                </button>
                                <button type="button" onclick="saveAgentPrompt2('${agentName}')"
                                        class="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-md transition-colors">
                                    Save
                                </button>
                            ` : `
                                <button type="button" onclick="showPromptHistory('${agentName}')"
                                        class="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-md transition-colors">
                                    History
                                </button>
                                <button type="button" onclick="showEffectivePrompt('${agentName}')"
                                        class="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-md transition-colors"
                                        style="display: none;"
                                        title="Preview the full message pair (system + hard-coded user template) that will be sent to the LLM">
                                    👁️ Effective Prompt
                                </button>
                                <button type="button" onclick="editPrompt('${agentName}')"
                                        class="px-3 py-1 btn-workflow text-white text-sm rounded-md transition-colors">
                                    Edit
                                </button>
                            `}
                        </div>
                    </div>
                        <!-- System and User prompt only -->
                        <div class="space-y-6">
                            <div class="border-l-4 border-blue-500 pl-4">
                                <label class="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                                    <span class="inline-flex items-center gap-2">
                                        <span><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17l-5.648 5.648a2.477 2.477 0 01-3.5-3.5l5.648-5.648m2.56-1.06l2.56 2.56m5.35-8.076a3.375 3.375 0 00-4.773-4.773L9.563 6.96l4.773 4.773 5.434-5.557z"/></svg></span>
                                        <span>System Prompt</span>
                                    </span>
                                </label>
                                <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">Defines the agent's role, behavior, and instructions</p>
                            ${isEditing ? `
                                    <textarea id="${agentId}-prompt-system-2"
                                          rows="8"
                                              aria-label="${escapeHtml(agentName)} System Prompt"
                                              data-derived-persist-key="agent_prompts.${escapeHtml(agentName)}.prompt"
                                              data-derived-binding-kind="prompt-system"
                                              placeholder="Enter system prompt (agent role, behavior, constraints)..."
                                              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:text-white font-mono text-sm">${escapeHtml(promptParts.system)}</textarea>
                                ` : systemDisplayHtml}
                                <div id="${agentId}-validate-result-2" class="hidden mt-2"></div>
                            </div>
                        ${isLockedScaffoldAgent ? `
                            <div class="border-l-4 border-amber-500 pl-4">
                                <div class="text-xs text-gray-500 dark:text-gray-400">
                                    User scaffold is locked in runtime and is no longer editable from the UI.
                                </div>
                            </div>
                        ` : `
                            <div class="border-l-4 border-green-500 pl-4">
                                <label class="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                                    <span class="inline-flex items-center gap-2">
                                        <span><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/></svg></span>
                                        <span>User Prompt</span>
                                    </span>
                                </label>
                                <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">User-facing message or task description</p>
                                ${isEditing ? `
                                    <textarea id="${agentId}-prompt-user-2"
                                              rows="8"
                                              aria-label="${escapeHtml(agentName)} User Prompt"
                                              data-derived-persist-key="agent_prompts.${escapeHtml(agentName)}.prompt"
                                              data-derived-binding-kind="prompt-user"
                                              placeholder="Enter user prompt (task, query, or user message)..."
                                              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-green-500 focus:border-green-500 dark:bg-gray-800 dark:text-white font-mono text-sm">${escapeHtml(promptParts.user)}</textarea>
                                ` : `
                                    <div id="${agentId}-prompt-user-display-2" class="text-sm font-mono bg-gray-50 dark:bg-gray-900 border-l-4 border-green-500 border border-gray-200 dark:border-gray-700 pl-4 p-3 rounded-md whitespace-pre-wrap break-words max-h-96 overflow-y-auto leading-relaxed ${!promptParts.user ? 'text-gray-400 italic' : 'text-gray-800 dark:text-gray-200'}">${escapeHtml(promptParts.user || '(empty)')}</div>
                                `}
                            </div>
                        `}
                        </div>
                </div>
            </div>
        </div>
    `;
}

function getOrCreatePromptData(agentName) {
    if (!agentPrompts) {
        agentPrompts = {};
    }
    if (!agentPrompts[agentName]) {
        agentPrompts[agentName] = {
            prompt: '',
            instructions: '',
            model: getCurrentModelForAgent(agentName) || 'Not configured'
        };
    }
    return agentPrompts[agentName];
}

function getDisabledExtractAgentsFromConfig(config) {
    if (!config) return [];
    const prompts = config.agent_prompts || {};
    const extractSettings = prompts.ExtractAgentSettings || prompts.ExtractAgent || {};
    const disabledRaw = extractSettings.disabled_agents || extractSettings.disabled_sub_agents || [];
    
    if (Array.isArray(disabledRaw)) {
        return disabledRaw;
    }
    
    if (disabledRaw && typeof disabledRaw === 'object') {
        return Object.entries(disabledRaw)
            .filter(([_, value]) => value === false || value === 0 || (typeof value === 'string' && value.toLowerCase() === 'false'))
            .map(([key]) => key);
    }
    
    return [];
}

function updateExtractAgentStatusBadge(agentName, enabled) {
    const ids = [
        `${agentName.toLowerCase()}-agent-enabled-badge`,
        `${agentName.toLowerCase()}-agent-enabled-pill`
    ];
    ids.forEach(badgeId => {
        const badge = document.getElementById(badgeId);
        if (!badge) return;
        badge.textContent = enabled ? 'Enabled' : 'Disabled';
        badge.classList.remove('bg-green-100', 'text-green-800', 'dark:bg-green-900', 'dark:text-green-200', 'bg-red-100', 'text-red-800', 'dark:bg-red-900', 'dark:text-red-200');
        if (enabled) {
            badge.classList.add('bg-green-100', 'text-green-800', 'dark:bg-green-900', 'dark:text-green-200');
        } else {
            badge.classList.add('bg-red-100', 'text-red-800', 'dark:bg-red-900', 'dark:text-red-200');
        }
    });
}

function updateRankEnabledBadge() {
    const checkbox = document.getElementById('rank-agent-enabled');
    const enabled = checkbox ? checkbox.checked : true;
    const ids = [
        'rank-agent-enabled-badge',
        'rank-agent-enabled-pill'
    ];
    ids.forEach(badgeId => {
        const badge = document.getElementById(badgeId);
        if (!badge) return;
        badge.textContent = enabled ? 'Enabled' : 'Disabled';
        badge.classList.remove('bg-green-100', 'text-green-800', 'dark:bg-green-900', 'dark:text-green-200', 'bg-red-100', 'text-red-800', 'dark:bg-red-900', 'dark:text-red-200');
        if (enabled) {
            badge.classList.add('bg-green-100', 'text-green-800', 'dark:bg-green-900', 'dark:text-green-200');
        } else {
            badge.classList.add('bg-red-100', 'text-red-800', 'dark:bg-red-900', 'dark:text-red-200');
        }
    });
}

function syncExtractAgentTogglesFromConfig(suppressEvents = false) {
    const disabled = new Set(getDisabledExtractAgentsFromConfig(currentConfig));
    disabledExtractAgents = disabled;
    
    extractSubAgents.forEach(agentName => {
        const checkbox = document.getElementById(`toggle-${agentName.toLowerCase()}-enabled`);
        if (checkbox) {
            const enabled = !disabled.has(agentName);
            const wasChecked = checkbox.checked;
            checkbox.checked = enabled;
            
            // Only dispatch change event if state actually changed and we're not suppressing events
            // Suppress events during initialization to prevent triggering autosave
            if (!suppressEvents && wasChecked !== enabled) {
                void checkbox.offsetHeight;
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            }
            
            updateExtractAgentStatusBadge(agentName, enabled);
            // Hide/show model selection UI based on enabled state
            toggleModelSelectionVisibility(agentName, enabled);
        }
    });
}

function toggleModelSelectionVisibility(agentName, enabled) {
    // Map agent names to their panel content IDs and provider select IDs
    const agentConfig = {
        'CmdlineExtract': {
            panelContent: 'cmdlineextract-agent-panel-content',
            providerSelect: 'cmdlineextract-provider'
        },
        'ProcTreeExtract': {
            panelContent: 'proctreeextract-agent-panel-content',
            providerSelect: 'proctreeextract-provider'
        },
        'HuntQueriesExtract': {
            panelContent: 'huntqueriesextract-agent-panel-content',
            providerSelect: 'huntqueriesextract-provider'
        },
        'RegistryExtract': {
            panelContent: 'registryextract-agent-panel-content',
            providerSelect: 'registryextract-provider'
        },
        'ServicesExtract': {
            panelContent: 'servicesextract-agent-panel-content',
            providerSelect: 'servicesextract-provider'
        },
        'ScheduledTasksExtract': {
            panelContent: 'scheduledtasksextract-agent-panel-content',
            providerSelect: 'scheduledtasksextract-provider'
        },
        'NetworkIndicatorExtract': {
            panelContent: 'networkindicatorextract-agent-panel-content',
            providerSelect: 'networkindicatorextract-provider'
        }
    };

    const config = agentConfig[agentName];
    if (!config) return;
    
    const panelContent = document.getElementById(config.panelContent);
    if (!panelContent) return;
    
    // Find the Model Selection section by finding the div that contains the provider select
    const providerSelect = document.getElementById(config.providerSelect);
    if (!providerSelect) return;
    
    // Find the parent div that contains the provider select - this is the Model Selection section
    let modelSelectionDiv = providerSelect.closest('div.bg-gray-50');
    
    // If not found by class, find by traversing up to find the container div
    if (!modelSelectionDiv) {
        let parent = providerSelect.parentElement;
        while (parent && parent !== panelContent) {
            if (parent.classList.contains('bg-gray-50') || parent.querySelector('label')?.textContent.includes('Model Provider')) {
                modelSelectionDiv = parent;
                break;
            }
            parent = parent.parentElement;
        }
    }
    
    if (modelSelectionDiv) {
        // Also find Temperature and Top_P sections
        const allSections = Array.from(panelContent.querySelectorAll('div.bg-gray-50'));
        const temperatureDiv = allSections.find(div => {
            const label = div.querySelector('label');
            return label && label.textContent.trim() === 'Temperature';
        });
        const topPDiv = allSections.find(div => {
            const label = div.querySelector('label');
            return label && label.textContent.trim() === 'Top_P';
        });
        
        if (enabled) {
            modelSelectionDiv.style.display = '';
            if (temperatureDiv) temperatureDiv.style.display = '';
            if (topPDiv) topPDiv.style.display = '';
        } else {
            modelSelectionDiv.style.display = 'none';
            if (temperatureDiv) temperatureDiv.style.display = 'none';
            if (topPDiv) topPDiv.style.display = 'none';
        }
    }
}

// Legacy function - now uses unified autosave
async function persistExtractAgentSettings() {
    await autoSaveConfig();
}

async function handleExtractAgentToggle(agentName) {
    const checkbox = document.getElementById(`toggle-${agentName.toLowerCase()}-enabled`);
    const enabled = checkbox ? checkbox.checked : true;
    if (!enabled) {
        disabledExtractAgents.add(agentName);
    } else {
        disabledExtractAgents.delete(agentName);
    }
    updateExtractAgentStatusBadge(agentName, enabled);
    toggleModelSelectionVisibility(agentName, enabled);
    
    // Auto-save the change (don't await - let it debounce in background)
    // If autosave fails, the toggle state is still correct in the DOM
    autoSaveConfig().catch(err => {
        console.warn('Autosave failed for extract agent toggle, but toggle state is preserved:', err);
    });
    
    // Update config display to reflect disabled state
    if (typeof updateConfigDisplay === 'function') {
        updateConfigDisplay();
    }
}

// Sub-agent scope mapping (extract+QA pairs)
const SUBAGENT_SCOPE_MAP = {
    cmdline: { extract: 'CmdlineExtract', extractPrefix: 'cmdlineextract' },
    proctree: { extract: 'ProcTreeExtract', extractPrefix: 'proctreeextract' },
    huntqueries: { extract: 'HuntQueriesExtract', extractPrefix: 'huntqueriesextract' },
    registry: { extract: 'RegistryExtract', extractPrefix: 'registryextract' },
    services: { extract: 'ServicesExtract', extractPrefix: 'servicesextract' },
    scheduledtasks: { extract: 'ScheduledTasksExtract', extractPrefix: 'scheduledtasksextract' },
    networkindicator: { extract: 'NetworkIndicatorExtract', extractPrefix: 'networkindicatorextract' }
};

const SUBAGENT_SCOPES = ['cmdline', 'proctree', 'huntqueries', 'registry', 'services', 'scheduledtasks', 'networkindicator'];

function getSubAgentPresetState(pairScope) {
    if (!SUBAGENT_SCOPES.includes(pairScope)) {
        throw new Error(`Invalid sub-agent scope: ${pairScope}`);
    }
    const map = SUBAGENT_SCOPE_MAP[pairScope];
    const allModels = collectAllAgentConfigs();
    const extractConfig = getAgentConfig(map.extractPrefix);
    const agent_models = {};
    [extractConfig].filter(Boolean).forEach(config => {
        if (config.providerKey && allModels[config.providerKey] !== undefined) agent_models[config.providerKey] = allModels[config.providerKey];
        if (config.modelKey && allModels[config.modelKey] !== undefined) agent_models[config.modelKey] = allModels[config.modelKey];
        if (config.temperatureKey && allModels[config.temperatureKey] !== undefined) agent_models[config.temperatureKey] = allModels[config.temperatureKey];
        if (config.topPKey && allModels[config.topPKey] !== undefined) agent_models[config.topPKey] = allModels[config.topPKey];
    });
    const promptsSource = { ...(currentConfig?.agent_prompts || {}), ...(agentPrompts || {}) };
    const agent_prompts = {};
    if (promptsSource[map.extract]) agent_prompts[map.extract] = promptsSource[map.extract];
    return {
        version: '1.0',
        scope: pairScope,
        created_at: new Date().toISOString(),
        agent_models,
        agent_prompts
    };
}

function applySubAgentPreset(preset) {
    const scope = preset.scope;
    if (!SUBAGENT_SCOPES.includes(scope)) {
        throw new Error(`Invalid sub-agent scope: ${scope}`);
    }
    const map = SUBAGENT_SCOPE_MAP[scope];
    const agentModels = preset.agent_models || {};
    const currentModels = collectAllAgentConfigs();
    const mergedModels = { ...currentModels };
    Object.keys(agentModels).forEach(k => { mergedModels[k] = agentModels[k]; });
    applyAgentConfigs(mergedModels);
    if (preset.agent_prompts && Object.keys(preset.agent_prompts).length > 0) {
        agentPrompts = { ...(agentPrompts || {}), ...preset.agent_prompts };
        renderAgentPrompts();
    }
    if (typeof autoSaveModelChange === 'function') autoSaveModelChange();
    if (typeof updateSaveButtonState === 'function') updateSaveButtonState();
    console.log('✅ Sub-agent preset applied for ' + scope);
}

// Preset Management Functions
function getFullPresetState(scope = null) {
    if (scope && SUBAGENT_SCOPES.includes(scope)) {
        return getSubAgentPresetState(scope);
    }
    // Get all form state
    const formState = getCurrentFormState();
    
    // Get sigma fallback setting
    const sigmaFallbackCheckbox = document.getElementById('sigma-fallback-enabled');
    const sigma_fallback_enabled = sigmaFallbackCheckbox ? sigmaFallbackCheckbox.checked : false;
    
    // Get rank agent enabled setting
    const rankAgentEnabledCheckbox = document.getElementById('rank-agent-enabled');
    const rank_agent_enabled = rankAgentEnabledCheckbox ? rankAgentEnabledCheckbox.checked !== false : true;
    
    // Get disabled extract agents
    const disabled_agents = Array.from(disabledExtractAgents);
    
    // Get description if available
    const description = currentConfig?.description || null;
    
    // Build complete preset
    const preset = {
        version: "1.0",
        created_at: new Date().toISOString(),
        description: description,
        thresholds: {
            junk_filter_threshold: formState.junk_filter_threshold,
            ranking_threshold: formState.ranking_threshold,
            similarity_threshold: formState.similarity_threshold
        },
        agent_models: formState.agent_models,
        sigma_fallback_enabled: sigma_fallback_enabled,
        rank_agent_enabled: rank_agent_enabled,
        cmdline_attention_preprocessor_enabled: document.getElementById('cmdline-attention-preprocessor-enabled')?.checked !== false,
        proc_tree_attention_preprocessor_enabled: document.getElementById('proctree-attention-preprocessor-enabled')?.checked !== false,
        extract_agent_settings: {
            disabled_agents: disabled_agents
        },
        agent_prompts: formState.agent_prompts || {}
    };
    
    return preset;
}

async function exportPresetToFile() {
    try {
        const preset = getFullPresetState();
        
        // Prompt for preset name
        const presetName = await ModalManager.prompt('Enter a name for this preset:', `workflow-preset-${new Date().toISOString().split('T')[0]}`, { title: 'Export Preset', confirmText: 'Export', placeholder: 'Preset name' });
        if (!presetName) {
            return; // User cancelled
        }
        
        // Clean preset name for filename
        const filename = presetName.replace(/[^a-z0-9]/gi, '-').toLowerCase() + '.json';
        
        // Export as normalized v2 format via backend (accepts v1/v2, returns v2)
        const response = await fetch('/api/workflow/config/preset/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(preset)
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || response.statusText);
        }
        const v2Config = await response.json();
        
        // Create blob and download
        const blob = new Blob([JSON.stringify(v2Config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        // Show success message
        showNotification('Preset saved as "' + filename + '" (v2 format)', 'success');
    } catch (error) {
        console.error('Error saving preset:', error);
        showNotification('Error saving preset: ' + (error instanceof Error ? error.message : String(error)), 'error');
    }
}

// Helper function to extract error message from FastAPI error responses
function extractErrorMessage(errorData, defaultMessage = 'Unknown error') {
    if (!errorData) {
        return defaultMessage;
    }
    
    // Handle FastAPI validation error format (detail can be array or string)
    if (errorData.detail) {
        if (Array.isArray(errorData.detail)) {
            // Format validation errors: "field: message"
            return errorData.detail.map(err => {
                if (typeof err === 'string') return err;
                if (err.msg) return `${err.loc?.join('.') || 'field'}: ${err.msg}`;
                return JSON.stringify(err);
            }).join('; ');
        }
        if (typeof errorData.detail === 'string') {
            return errorData.detail;
        }
        // If detail is an object, try to stringify it
        return JSON.stringify(errorData.detail);
    }
    
    // Fallback: try to stringify the whole object
    if (typeof errorData === 'string') {
        return errorData;
    }
    
    try {
        return JSON.stringify(errorData);
    } catch {
        return defaultMessage;
    }
}

async function importPresetFromFile(event) {
    const file = event.target.files[0];
    if (!file) {
        return;
    }
    
    try {
        const text = await file.text();
        let preset = JSON.parse(text);
        
        const isV2 = preset.Version === '2.0';
        if (!preset.version && !isV2) throw new Error('Invalid preset format. Missing version.');
        if (isV2) {
            const response = await fetch('/api/workflow/config/preset/to-legacy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(preset)
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || data.message || 'Failed to convert preset.');
            // V2: warnings are already embedded in the to-legacy response; surface them directly.
            const v2Warnings = data.warnings || [];
            if (v2Warnings.length > 0) {
                console.warn('Preset import warnings:', v2Warnings);
                const summary = v2Warnings.length === 1
                    ? v2Warnings[0]
                    : `${v2Warnings.length} prompt issues found (see console for details)`;
                showNotification('Preset warning: ' + summary, 'warning');
            }
            preset = data;
        }
        if (preset.scope && SUBAGENT_SCOPES.includes(preset.scope)) {
            if (!preset.agent_models && (!preset.agent_prompts || Object.keys(preset.agent_prompts).length === 0)) {
                throw new Error('Sub-agent preset must have agent_models or agent_prompts.');
            }
        } else {
            if (!preset.thresholds || !preset.agent_models) {
                throw new Error('Invalid preset format. Missing thresholds or agent_models.');
            }
        }

        const isSubAgent = preset.scope && SUBAGENT_SCOPES.includes(preset.scope);
        const confirmMsg = isSubAgent
            ? `Load ${SUBAGENT_SCOPE_MAP[preset.scope]?.extract || preset.scope} preset "${file.name}"?\n\nThis will replace only that sub-agent pair's config and prompts.`
            : `Load preset "${file.name}"?\n\nThis will replace all current settings:\n` +
              `- Thresholds\n- Model selections\n- Temperature settings\n` +
              `- Extract agent toggles\n- Sigma fallback setting\n- Agent prompts\n\nClick OK to proceed or Cancel to abort.`;

        if (!await ModalManager.confirm(confirmMsg, { title: 'Load Preset', confirmText: 'Load', confirmClass: 'bg-blue-600 hover:bg-blue-700', cancelText: 'Cancel' })) {
            event.target.value = '';
            return;
        }

        await applyPreset(preset);

        const successMsg = isSubAgent
            ? `${SUBAGENT_SCOPE_MAP[preset.scope]?.extract || preset.scope} preset loaded`
            : 'Preset "' + file.name + '" loaded successfully';
        showNotification(successMsg, 'success');
        // Legacy presets (and V2 presets after conversion) run through the shared helper.
        // V2 warnings were already shown above; _notifyImportWarnings deduplicates naturally
        // since the to-legacy response strips the warnings field before storing as preset.
        if (!isV2) await _notifyImportWarnings(preset);
        
        // Reset file input
        event.target.value = '';
    } catch (error) {
        console.error('Error loading preset:', error);
        const errorMessage = error instanceof Error ? error.message : 
                           (typeof error === 'string' ? error : 
                           (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading preset: ' + errorMessage, 'error');
        event.target.value = ''; // Reset file input
    }
}

function closeConfigPresetListModal() {
    popModal();
}

function closeConfigVersionListModal() {
    popModal();
}

let _cvPage = 1;
let _cvSearch = '';

async function refreshConfigVersionList() {
    const listEl = document.getElementById('configVersionList');
    if (!listEl) return;
    listEl.innerHTML = '<p class="text-gray-500 text-center py-4">Loading…</p>';
    try {
        const params = new URLSearchParams({ page: _cvPage, limit: 20 });
        if (_cvSearch) params.set('version', _cvSearch);
        const response = await fetch(`/api/workflow/config/versions?${params}`);
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to load versions'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, 'Failed to load versions');
            throw new Error(errorMsg);
        }
        listEl.innerHTML = '';
        if (!data.versions?.length) {
            listEl.innerHTML = '<p class="text-gray-500 dark:text-gray-400 text-center py-4">No versions found.</p>';
        } else {
            data.versions.forEach(v => {
                const item = document.createElement('div');
                item.className = 'border border-gray-300 dark:border-gray-600 rounded-md p-3 bg-gray-50 dark:bg-gray-900';
                const updatedStr = new Date(v.updated_at).toLocaleString();
                const activeBadge = v.is_active ? '<span class="text-xs px-2 py-0.5 bg-green-600 text-white rounded">Active</span>' : '';
                item.innerHTML = `
                    <div class="flex items-start justify-between">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="font-semibold text-gray-900 dark:text-white">Version ${v.version}</span>
                                ${activeBadge}
                            </div>
                            ${v.description ? `<p class="text-sm text-gray-600 dark:text-gray-400 mb-2">${escapeHtml(v.description)}</p>` : ''}
                            <div class="text-xs text-gray-500 dark:text-gray-400">Updated: ${updatedStr}</div>
                        </div>
                        <div class="flex space-x-2 ml-4">
                            <button type="button" onclick="toggleConfigVersionDetails(${v.id}, this)" aria-expanded="false" aria-controls="configVersionDetails-${v.id}" class="px-3 py-1 text-xs border border-gray-600 text-gray-300 hover:text-white rounded-md">Expand</button>
                            <button type="button" onclick="loadConfigByVersion(${v.version})" class="px-3 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 text-white rounded-md">Load</button>
                        </div>
                    </div>
                    <div id="configVersionDetails-${v.id}" role="region" class="hidden mt-3 pt-3 border-t border-gray-300 dark:border-gray-600" data-version="${v.version}" data-updated-at="${v.updated_at}"></div>
                `;
                listEl.appendChild(item);
            });
        }
        const total = data.total ?? 0;
        const totalPages = data.total_pages ?? 1;
        const paginationEl = document.getElementById('configVersionPagination');
        if (paginationEl) {
            paginationEl.classList.toggle('hidden', total <= 20);
            document.getElementById('configVersionPageInfo').textContent = `Page ${_cvPage} of ${totalPages} (${total} total)`;
            document.getElementById('configVersionPrevBtn').disabled = _cvPage <= 1;
            document.getElementById('configVersionNextBtn').disabled = _cvPage >= totalPages;
        }
    } catch (error) {
        console.error('Error refreshing config version list:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading versions: ' + errorMessage, 'error');
        listEl.innerHTML = '<p class="text-gray-500 dark:text-gray-400 text-center py-4">Failed to load versions.</p>';
    }
}

async function toggleConfigVersionDetails(rowId, btn) {
    const container = document.getElementById(`configVersionDetails-${rowId}`);
    if (!container) return;
    if (!container.classList.contains('hidden')) {
        container.classList.add('hidden');
        container.innerHTML = '';
        delete container.dataset.loaded;
        btn.textContent = 'Expand';
        btn.setAttribute('aria-expanded', 'false');
        return;
    }
    btn.setAttribute('aria-expanded', 'true');
    if (!container.dataset.loaded) {
        btn.textContent = 'Loading…';
        btn.disabled = true;
        try {
            const version = container.dataset.version;
            const response = await fetch(`/api/workflow/config/version/${version}`);
            let data;
            try {
                data = await response.json();
            } catch (jsonError) {
                throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to load config'}`);
            }
            if (!response.ok) {
                throw new Error(extractErrorMessage(data, `Failed to load config v${version} (${response.status})`));
            }
            const thresholds = data.thresholds || {};
            const agentPrompts = data.agent_prompts || {};
            if (data.extract_agent_settings && Array.isArray(data.extract_agent_settings.disabled_agents)) {
                agentPrompts.ExtractAgentSettings = agentPrompts.ExtractAgentSettings || {};
                agentPrompts.ExtractAgentSettings.disabled_agents = data.extract_agent_settings.disabled_agents;
            }
            const merged = {
                version,
                ranking_threshold: thresholds.ranking_threshold ?? 'N/A',
                junk_filter_threshold: thresholds.junk_filter_threshold ?? 'N/A',
                similarity_threshold: thresholds.similarity_threshold ?? 'N/A',
                updated_at: container.dataset.updatedAt,
                rank_agent_enabled: data.rank_agent_enabled,
                cmdline_attention_preprocessor_enabled: data.cmdline_attention_preprocessor_enabled,
                proc_tree_attention_preprocessor_enabled: data.proc_tree_attention_preprocessor_enabled,
                agent_models: data.agent_models || {},
                agent_prompts: agentPrompts,
            };
            renderWorkflowConfigDisplay(merged, { containerId: container.id, showVersion: false });
            container.dataset.loaded = '1';
        } catch (error) {
            console.error('Error loading config version details:', error);
            const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
            showNotification('Error loading config details: ' + errorMessage, 'error');
            container.innerHTML = `<p class="text-xs text-red-500">Failed to load details: ${escapeHtml(errorMessage)}</p>`;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Collapse';
        }
    }
    container.classList.remove('hidden');
}

function searchConfigVersions() {
    _cvSearch = document.getElementById('configVersionSearch')?.value.trim() ?? '';
    _cvPage = 1;
    document.getElementById('configVersionClearSearch')?.classList.toggle('hidden', !_cvSearch);
    refreshConfigVersionList();
}

function clearConfigVersionSearch() {
    const input = document.getElementById('configVersionSearch');
    if (input) input.value = '';
    _cvSearch = '';
    _cvPage = 1;
    document.getElementById('configVersionClearSearch')?.classList.add('hidden');
    refreshConfigVersionList();
}

function changeConfigVersionPage(delta) {
    _cvPage = Math.max(1, _cvPage + delta);
    refreshConfigVersionList();
}

async function showConfigVersionList() {
    _cvPage = 1;
    _cvSearch = '';
    const input = document.getElementById('configVersionSearch');
    if (input) input.value = '';
    document.getElementById('configVersionClearSearch')?.classList.add('hidden');
    pushModal('configVersionListModal', true);
    await refreshConfigVersionList();
}

/**
 * Validate a legacy-shaped preset against the server-side prompt scanner and
 * surface any warnings as a toast. Best-effort: validation failure never
 * blocks the load.
 */
async function _notifyImportWarnings(preset) {
    try {
        const vResp = await fetch('/api/workflow/config/preset/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(preset)
        });
        if (!vResp.ok) return;
        const vData = await vResp.json().catch(() => ({}));
        const warnings = vData.warnings || [];
        if (warnings.length > 0) {
            console.warn('Preset load warnings:', warnings);
            const summary = warnings.length === 1
                ? warnings[0]
                : `${warnings.length} prompt issues found (see console for details)`;
            showNotification('Preset warning: ' + summary, 'warning');
        }
    } catch (_) { /* validation is best-effort */ }
}

async function loadConfigByVersion(versionNumber) {
    try {
        const response = await fetch(`/api/workflow/config/version/${versionNumber}`);
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to load config'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to load config v${versionNumber} (${response.status})`);
            throw new Error(errorMsg);
        }
        await applyPreset(data);
        closeConfigVersionListModal();
        showNotification('Config v' + versionNumber + ' loaded (prompts + models). Click Save to make it active.', 'info');
        await _notifyImportWarnings(data);
    } catch (error) {
        console.error('Error loading config by version:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading version: ' + errorMessage, 'error');
    }
}

let _configPresetListScope = null;

async function refreshConfigPresetList(scope = null) {
    try {
        _configPresetListScope = scope;
        const url = scope ? `/api/workflow/config/preset/list?scope=${encodeURIComponent(scope)}` : '/api/workflow/config/preset/list';
        const response = await fetch(url);
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to load presets'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to load presets (${response.status})`);
            throw new Error(errorMsg);
        }
        const listEl = document.getElementById('configPresetList');
        const titleEl = document.querySelector('#configPresetListModal h3');
        const importRow = document.getElementById('configPresetListImportRow');
        if (!listEl) return;
        if (titleEl) {
            const scopeLabel = scope ? ` (${SUBAGENT_SCOPE_MAP[scope]?.extract || scope})` : '';
            titleEl.textContent = '📋 Configuration Presets' + scopeLabel;
        }
        if (importRow) importRow.classList.toggle('hidden', !scope);
        listEl.innerHTML = '';
        if (!data.presets || data.presets.length === 0) {
            listEl.innerHTML = '<p class="text-gray-500 dark:text-gray-400 text-center py-4">' + (scope ? `No ${scope} presets saved yet.` : 'No presets saved yet.') + '</p>';
            return;
        }
        data.presets.forEach(p => {
            const item = document.createElement('div');
            item.className = 'border border-gray-300 dark:border-gray-600 rounded-md p-3 bg-gray-50 dark:bg-gray-900';
            const dateStr = new Date(p.updated_at).toLocaleString();
            item.innerHTML = `
                <div class="flex items-start justify-between">
                    <div class="flex-1">
                        <div class="flex items-center space-x-2 mb-2">
                            <span class="font-semibold text-gray-900 dark:text-white">${escapeHtml(p.name)}</span>
                        </div>
                        ${p.description ? `<p class="text-sm text-gray-600 dark:text-gray-400 mb-2">${escapeHtml(p.description)}</p>` : ''}
                        <div class="text-xs text-gray-500 dark:text-gray-400">Updated: ${dateStr}</div>
                    </div>
                    <div class="flex space-x-2 ml-4">
                        <button type="button" onclick="loadConfigPresetById(${p.id})" class="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md">Load</button>
                        <button type="button" onclick="deleteConfigPreset(${p.id}, '${String(p.name).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')" class="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded-md">Delete</button>
                    </div>
                </div>
            `;
            listEl.appendChild(item);
        });
    } catch (error) {
        console.error('Error refreshing config preset list:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading presets: ' + errorMessage, 'error');
    }
}

async function showConfigPresetList() {
    try {
        pushModal('configPresetListModal', true);
        await refreshConfigPresetList(null);
    } catch (error) {
        console.error('Error showing config preset list:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading presets: ' + errorMessage, 'error');
    }
}

async function showConfigPresetListForScope(scope) {
    try {
        if (!SUBAGENT_SCOPES.includes(scope)) {
            showNotification('Invalid sub-agent scope', 'error');
            return;
        }
        pushModal('configPresetListModal', true);
        await refreshConfigPresetList(scope);
    } catch (error) {
        console.error('Error showing config preset list:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading presets: ' + errorMessage, 'error');
    }
}

async function saveSubAgentPreset(scope) {
    try {
        if (!SUBAGENT_SCOPES.includes(scope)) {
            showNotification('Invalid sub-agent scope', 'error');
            return;
        }
        const preset = getFullPresetState(scope);
        const map = SUBAGENT_SCOPE_MAP[scope];
        const defaultName = `${map.extract.toLowerCase()}-preset-${new Date().toISOString().split('T')[0]}`;
        const name = await ModalManager.prompt('Enter a name for this preset:', defaultName, { title: 'Save Preset', confirmText: 'Save', placeholder: 'Preset name' });
        if (!name) return;
        const description = await ModalManager.prompt('Enter a description (optional):', '', { title: 'Description', confirmText: 'Save', placeholder: 'Optional description' }) || null;
        const response = await fetch('/api/workflow/config/preset/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, config: preset })
        });
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to save preset'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to save preset (${response.status})`);
            throw new Error(errorMsg);
        }
        showNotification(data.message || 'Sub-agent preset saved', 'success');
    } catch (error) {
        console.error('Error saving sub-agent preset:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error saving preset: ' + errorMessage, 'error');
    }
}

async function saveConfigPreset() {
    try {
        const preset = getFullPresetState();
        const name = await ModalManager.prompt('Enter a name for this preset:', 'workflow-preset-' + new Date().toISOString().split('T')[0], { title: 'Save Preset', confirmText: 'Save', placeholder: 'Preset name' });
        if (!name) return;
        const description = await ModalManager.prompt('Enter a description (optional):', '', { title: 'Description', confirmText: 'Save', placeholder: 'Optional description' }) || null;
        const response = await fetch('/api/workflow/config/preset/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, config: preset })
        });
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to save preset'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to save preset (${response.status})`);
            throw new Error(errorMsg);
        }
        showNotification(data.message || 'Preset saved', 'success');
    } catch (error) {
        console.error('Error saving config preset:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error saving preset: ' + errorMessage, 'error');
    }
}

async function loadConfigPresetById(presetId) {
    try {
        const id = parseInt(presetId, 10);
        if (isNaN(id)) throw new Error(`Invalid preset ID: ${presetId}`);
        const response = await fetch(`/api/workflow/config/preset/${id}`);
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to load preset'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to load preset (${response.status})`);
            throw new Error(errorMsg);
        }
        await applyPreset(data);
        closeConfigPresetListModal();
        const msg = data.scope && SUBAGENT_SCOPES.includes(data.scope)
            ? `${SUBAGENT_SCOPE_MAP[data.scope]?.extract || data.scope} preset loaded`
            : 'Preset loaded';
        showNotification(msg, 'success');
        await _notifyImportWarnings(data);
    } catch (error) {
        console.error('Error loading config preset:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading preset: ' + errorMessage, 'error');
    }
}

async function deleteConfigPreset(presetId, name) {
    try {
        const id = parseInt(presetId, 10);
        if (isNaN(id)) throw new Error(`Invalid preset ID: ${presetId}`);
        if (!await ModalManager.confirm(`Delete preset "${name}"?`, { title: 'Delete Preset', confirmText: 'Delete', confirmClass: 'bg-red-600 hover:bg-red-700' })) return;
        const response = await fetch(`/api/workflow/config/preset/${id}`, { method: 'DELETE' });
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to delete preset'}`);
        }
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to delete preset (${response.status})`);
            throw new Error(errorMsg);
        }
        await refreshConfigPresetList();
        showNotification('Preset "' + name + '" deleted', 'success');
    } catch (error) {
        console.error('Error deleting config preset:', error);
        const errorMessage = error instanceof Error ? error.message : (typeof error === 'string' ? error : (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error deleting preset: ' + errorMessage, 'error');
    }
}

async function applyPreset(preset) {
    try {
        if (preset.scope && SUBAGENT_SCOPES.includes(preset.scope)) {
            applySubAgentPreset(preset);
            return;
        }
        // Apply thresholds
        if (preset.thresholds) {
            const junkFilterInput = document.getElementById('junkFilterThreshold');
            if (junkFilterInput && preset.thresholds.junk_filter_threshold !== undefined) {
                junkFilterInput.value = preset.thresholds.junk_filter_threshold;
            }
            
            const rankingInput = document.getElementById('rankingThreshold');
            if (rankingInput && preset.thresholds.ranking_threshold !== undefined) {
                rankingInput.value = preset.thresholds.ranking_threshold;
            }
            
            const similarityInput = document.getElementById('similarityThreshold');
            if (similarityInput && preset.thresholds.similarity_threshold !== undefined) {
                similarityInput.value = preset.thresholds.similarity_threshold;
            }
            ['junkFilterThreshold', 'rankingThreshold', 'similarityThreshold'].forEach(updateThresholdDisplay);
        }

        // Apply agent models using unified system
        if (preset.agent_models) {
            // Use the unified applyAgentConfigs function which handles providers correctly
            // This ensures providers are set first, then models on the correct provider-specific selects
            applyAgentConfigs(preset.agent_models);
        }
        
        // Sync currentConfig.agent_models so any async rebuild (renderAgentModels, loadAgentModels)
        // reads the preset values rather than the stale in-memory config.
        if (currentConfig && typeof currentConfig === 'object' && preset.agent_models) {
            currentConfig.agent_models = { ...(currentConfig.agent_models || {}), ...preset.agent_models };
        }

        // Apply sigma fallback
        if (preset.sigma_fallback_enabled !== undefined) {
            const sigmaFallbackCheckbox = document.getElementById('sigma-fallback-enabled');
            if (sigmaFallbackCheckbox) {
                sigmaFallbackCheckbox.checked = preset.sigma_fallback_enabled;
            }
        }
        
        // Apply cmdline attention preprocessor
        if (preset.cmdline_attention_preprocessor_enabled !== undefined) {
            const cmdlineAttentionPreprocessorCheckbox = document.getElementById('cmdline-attention-preprocessor-enabled');
            if (cmdlineAttentionPreprocessorCheckbox) {
                cmdlineAttentionPreprocessorCheckbox.checked = preset.cmdline_attention_preprocessor_enabled;
            }
        }
        // Apply proc tree attention preprocessor
        if (preset.proc_tree_attention_preprocessor_enabled !== undefined) {
            const proctreeAttentionPreprocessorCheckbox = document.getElementById('proctree-attention-preprocessor-enabled');
            if (proctreeAttentionPreprocessorCheckbox) {
                proctreeAttentionPreprocessorCheckbox.checked = preset.proc_tree_attention_preprocessor_enabled;
            }
        }
        
        // Apply rank agent enabled
        if (preset.rank_agent_enabled !== undefined) {
            const rankAgentEnabledCheckbox = document.getElementById('rank-agent-enabled');
            if (rankAgentEnabledCheckbox) {
                rankAgentEnabledCheckbox.checked = preset.rank_agent_enabled;
                // Update badge to reflect preset state
                if (typeof updateRankEnabledBadge === 'function') {
                    updateRankEnabledBadge();
                }
            }
        }
        
        // Apply extract agent toggles
        if (preset.extract_agent_settings && preset.extract_agent_settings.disabled_agents) {
            const disabledList = preset.extract_agent_settings.disabled_agents;
            disabledExtractAgents = new Set(disabledList);
            
            extractSubAgents.forEach(agentName => {
                const checkbox = document.getElementById(`toggle-${agentName.toLowerCase()}-enabled`);
                if (checkbox) {
                    const enabled = !disabledList.includes(agentName);
                    checkbox.checked = enabled;
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    updateExtractAgentStatusBadge(agentName, enabled);
                }
            });
        }
        
        // Apply agent prompts to form state only (do NOT PUT per prompt).
        // Each PUT /config/prompts creates a new config version that copies agent_models from
        // the current active config, so prompts would be restored but temperature/qa/etc. would
        // stay from the previous version. By loading prompts into form state, one Save creates
        // a single new version with both preset prompts and preset agent_models.
        if (preset.agent_prompts && Object.keys(preset.agent_prompts).length > 0) {
            console.log('🔄 Loading agent prompts from preset into form (Save to apply)...');
            agentPrompts = { ...(agentPrompts || {}), ...preset.agent_prompts };
            renderAgentPrompts();
            console.log('✅ Agent prompts loaded from preset. Click Save to make this config active.');
        }
        
        // Merge threshold fields that have no form inputs so they are sent on next Save
        if (preset.min_hunt_score !== undefined) {
            if (!currentConfig || typeof currentConfig !== 'object') currentConfig = {};
            currentConfig.min_hunt_score = preset.min_hunt_score;
        }
        
        // Trigger auto-save handlers to update UI state
        if (typeof autoSaveModelChange === 'function') {
            autoSaveModelChange();
        }
        
        // Update save button state
        if (typeof updateSaveButtonState === 'function') {
            updateSaveButtonState();
        }
        
        console.log('✅ Preset applied successfully');
    } catch (error) {
        console.error('Error applying preset:', error);
        throw error;
    }
}

// Prompt editing functions
function editPrompt(agentName) {
    editingPrompts[agentName] = true;
    renderAgentPrompts();
}

function cancelEditPrompt2(agentName) {
    editingPrompts[agentName] = false;
    renderAgentPrompts();
    // Reload prompts to restore original values
    loadAgentPrompts();
}

// overrides: optional { systemOverride: string, userOverride: string|null }
// When provided (expanded editor path), values come directly from the caller
// and the inline DOM textarea lookup is skipped entirely.
async function saveAgentPrompt2(agentName, overrides = {}) {
    const agentId = agentName.toLowerCase().replace(/\s+/g, '-');
    const lockedScaffold = isLockedExtractorPrompt(agentName) || isLockedCanonicalPrompt(agentName);

    let systemVal, userVal;
    if (overrides.systemOverride !== undefined) {
        // Expanded-editor path: values passed directly — no DOM relay needed.
        systemVal = overrides.systemOverride || "";
        userVal = (overrides.userOverride !== null && overrides.userOverride !== undefined)
            ? overrides.userOverride
            : "";
    } else {
        // Inline-editor path: read from the agent card's edit-mode textareas.
        const promptSystemElement = document.getElementById(`${agentId}-prompt-system-2`);
        const promptUserElement = document.getElementById(`${agentId}-prompt-user-2`);
        if (!promptSystemElement || (!promptUserElement && !lockedScaffold)) {
            showNotification('Prompt elements not found for ' + agentName, 'error');
            return;
        }
        systemVal = promptSystemElement.value || "";
        userVal = promptUserElement ? promptUserElement.value || "" : "";

        // Gate: run validation before saving. Block on errors; warnings are allowed through.
        const systemValTrimmed = systemVal.trim();
        const issues = _collectPromptIssues(agentName, systemValTrimmed);
        const errors = issues.filter(function(i) { return i.level === 'error'; });
        if (errors.length > 0) {
            const resultDiv = document.getElementById(`${agentId}-validate-result-2`)
                           || document.getElementById(`${agentId}-validate-result`);
            if (resultDiv) _renderValidateResult(resultDiv, issues);
            return;
        }
    }

    isSavingPrompt = true;
    if (autoSaveTimeout) { clearTimeout(autoSaveTimeout); autoSaveTimeout = null; }

    const isExtractionAgent = isLockedExtractorPrompt(agentName);
    const current = agentPrompts[agentName]?.prompt || '';
    let parsed = {};
    try { parsed = current ? JSON.parse(current) : {}; } catch (_) {}

    let combinedPrompt;
    let instructions = null;
    if (isExtractionAgent) {
        // If systemVal is a full JSON config object (user edited the full envelope),
        // use it directly. Otherwise treat it as a plain role persona string.
        let parsedSystem = null;
        try { parsedSystem = JSON.parse(systemVal); } catch (_) {}
        let merged;
        if (parsedSystem && typeof parsedSystem === 'object' && ('system' in parsedSystem || 'role' in parsedSystem)) {
            // Full JSON config edited -- use as-is, but normalize legacy role key.
            merged = { ...parsedSystem };
            if (merged.role && !merged.system) { merged.system = merged.role; }
        } else {
            // Plain system persona string -- preserve existing envelope fields
            merged = {
                ...parsed,
                system: systemVal,
                task: parsed.task || "",
                json_example: parsed.json_example || "{}",
                instructions: parsed.instructions || ""
            };
        }
        delete merged.user;
        delete merged.role;  // remove legacy key from any spread of old DB records
        delete merged.prompt;
        delete merged.user_template;  // not read by backend; keep JSON clean
        combinedPrompt = JSON.stringify(merged);
        instructions = merged.instructions || null;
    } else {
        // Canonical write path: send {system, user} as separate fields.
        combinedPrompt = null;
    }

    const promptData = combinedPrompt === null
        ? {
            agent_name: agentName,
            system: systemVal,
            user: userVal,
            instructions: instructions,
            change_description: null
          }
        : {
            agent_name: agentName,
            prompt: combinedPrompt,
            instructions: instructions,
            change_description: null
          };
    
    try {
        const response = await fetch('/api/workflow/config/prompts', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(promptData)
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('✅ Save successful:', result);
            
            // CRITICAL: Exit edit mode FIRST so display mode is shown
            editingPrompts[agentName] = false;
            
            // Update agentPrompts from API response when available (source of truth), else from what we sent
            if (!agentPrompts) agentPrompts = {};
            const savedPromptData = {
                prompt: result.prompt !== undefined ? result.prompt : promptData.prompt,
                instructions: (result.instructions !== undefined ? result.instructions : promptData.instructions) || '',
                model: agentPrompts[agentName]?.model || 'Not configured'
            };
            // CRITICAL: Update agentPrompts with saved data BEFORE any rendering
            // This ensures renderAgentPrompts() uses the correct data
            agentPrompts[agentName] = savedPromptData;
            
            console.log('Updated agentPrompts for', agentName, ':', savedPromptData);
            
            // Re-render all prompts immediately with saved data (before reload)
            // This shows the saved data immediately in display mode
            renderAgentPrompts();
            lastPromptSaveAt = Date.now();
            lastSavedPromptAgent = agentName;
            
            // Use console.log instead of alert to avoid blocking browser automation
            console.log(`✅ Agent prompt updated successfully for ${agentName}`);
            // Sync currentConfig so auto-save uses fresh data
            if (currentConfig) {
                if (!currentConfig.agent_prompts) currentConfig.agent_prompts = {};
                currentConfig.agent_prompts[agentName] = savedPromptData;
            }
            // Do NOT call loadConfig here - it fetches config and can overwrite agentPrompts/display with stale data
            resetOriginalConfigStateFromCurrent();
            updateSaveButtonState();
            isSavingPrompt = false;
            
        } else {
            isSavingPrompt = false;
            let errorMessage = 'Unknown error';
            try {
            const error = await response.json();
                errorMessage = error.detail || error.message || JSON.stringify(error);
                console.error('API error response:', error);
            } catch (e) {
                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                console.error('Failed to parse error response:', e);
            }
            showNotification('Error updating agent prompt: ' + errorMessage, 'error');
            console.error('Full response status:', response.status);
            console.error('Full response headers:', Object.fromEntries(response.headers.entries()));
            console.error('Full response URL:', response.url);
        }
    } catch (error) {
        isSavingPrompt = false;
        console.error('Error saving agent prompt:', error);
        showNotification('Error saving agent prompt: ' + (error.message || error), 'error');
    }
}

// Track original config state for change detection
let originalConfigState = null;

// Reset snapshot of the original state to match the current config (used after saves/auto-saves)
function resetOriginalConfigStateFromCurrent() {
    if (!currentConfig) return;
    
    // Get current prompts state (merged from currentConfig and agentPrompts)
    const promptsSource = {
        ...(currentConfig.agent_prompts || {}),
        ...(agentPrompts || {})
    };
    const extractSettings = promptsSource.ExtractAgentSettings ? { ...promptsSource.ExtractAgentSettings } : {};
    extractSettings.disabled_agents = Array.from(getDisabledExtractAgentsFromConfig(currentConfig) || []);
    promptsSource.ExtractAgentSettings = extractSettings;
    
    originalConfigState = {
        junk_filter_threshold: currentConfig.junk_filter_threshold || 0,
        ranking_threshold: currentConfig.ranking_threshold || 0,
        similarity_threshold: currentConfig.similarity_threshold || 0,
        description: null,
        agent_models: currentConfig.agent_models || {},
        disabled_extract_agents: getDisabledExtractAgentsFromConfig(currentConfig),
        sigma_fallback_enabled: currentConfig.sigma_fallback_enabled || false,
        rank_agent_enabled: currentConfig.rank_agent_enabled !== undefined ? currentConfig.rank_agent_enabled : true,
        agent_prompts: promptsSource
    };
}

// Function to check if a model is an embedding/text encoder (should be excluded)
function isEmbeddingModel(modelName) {
    if (!modelName) return false;
    const lower = modelName.toLowerCase();
    return lower.includes('bert') || 
           lower.includes('embedding') || 
           lower.includes('encoder') ||
           lower.includes('text-embedding') ||
           lower.includes('sentence-transformers') ||
           lower.includes('all-mpnet') ||
           lower.includes('e5-');
}

// Function to get all selected models from form (excluding embedding/text encoder models)
function getAllSelectedModels() {
    const models = new Set();
    
    // Main agent models
    const rankModel = document.getElementById('rankagent-model-2')?.value.trim();
    if (rankModel && !isEmbeddingModel(rankModel)) models.add(rankModel);
    
    const extractModel = document.getElementById('extractagent-model-2')?.value.trim();
    if (extractModel && !isEmbeddingModel(extractModel)) models.add(extractModel);
    
    const sigmaModel = document.getElementById('sigmaagent-model-2')?.value.trim();
    if (sigmaModel && !isEmbeddingModel(sigmaModel)) models.add(sigmaModel);
    
    // Sub-agent models (only if explicitly set, not using ExtractAgent model)
    const subAgents = [
        { name: 'CmdlineExtract', id: 'cmdlineextract-model' },
        { name: 'ProcTreeExtract', id: 'proctreeextract-model' }
    ];
    
    subAgents.forEach(subAgent => {
        const select = document.getElementById(subAgent.id);
        if (select && select.value && select.value.trim()) {
            const model = select.value.trim();
            if (!isEmbeddingModel(model)) {
                models.add(model);
            }
        }
    });
    
    // Note: OS Detection embedding and Sigma embedding models are excluded (they're text encoders)
    
    return Array.from(models).sort();
}

// Function to get all selected models with their providers from UI state
function getAllSelectedModelsWithProviders() {
    const selectedModels = [];
    
    // Get disabled state
    const disabled = typeof disabledExtractAgents !== 'undefined' ? disabledExtractAgents : new Set();
    
    // Helper to get model and provider from UI
    function getModelWithProvider(agentPrefix, providerId, agentName) {
        const providerSelect = document.getElementById(providerId);
        if (!providerSelect) return null;
        
        const provider = (providerSelect.value || getDefaultProvider()).trim().toLowerCase();
        
        // Use getActiveAgentModelValue to get the correct model based on provider
        // This handles LMStudio (uses -model or -model-2) vs commercial providers (uses -model-{provider})
        const model = getActiveAgentModelValue(agentPrefix, provider);
        if (!model || isEmbeddingModel(model)) return null;
        
        return { agent: agentName, model, provider };
    }
    
    // Main agents - show with actual enabled state so summary always shows Rank when model is set
    const rankAgentEnabled = document.getElementById('rank-agent-enabled')?.checked !== false;
    const rankProvider = document.getElementById('rankagent-provider')?.value || getDefaultProvider();
    const rankModel = getActiveAgentModelValue('rankagent', rankProvider);
    const rankAddedFromForm = rankModel && !isEmbeddingModel(rankModel);
    if (rankAddedFromForm) {
        selectedModels.push({ agent: 'Rank', model: rankModel, provider: rankProvider, enabled: rankAgentEnabled });
    }
    // Fallback: show Rank from loaded config when form select not yet synced (e.g. placeholder)
    if (!rankAddedFromForm && currentConfig?.agent_models?.RankAgent && !isEmbeddingModel(currentConfig.agent_models.RankAgent)) {
        const cfgProvider = (currentConfig.agent_models.RankAgent_provider || rankProvider || getDefaultProvider()).trim().toLowerCase();
        selectedModels.push({ agent: 'Rank', model: String(currentConfig.agent_models.RankAgent).trim(), provider: cfgProvider, enabled: rankAgentEnabled });
    }

    // Extract Agent - always enabled (no toggle)
    const extractProvider = document.getElementById('extractagent-provider')?.value || getDefaultProvider();
    const extractModel = getActiveAgentModelValue('extractagent', extractProvider);
    if (extractModel && !isEmbeddingModel(extractModel)) {
        selectedModels.push({ agent: 'Extract', model: extractModel, provider: extractProvider, enabled: true });
    }
    
    // SIGMA Agent - always show if model is configured
    const sigmaProvider = document.getElementById('sigmaagent-provider')?.value || getDefaultProvider();
    const sigmaModel = getActiveAgentModelValue('sigmaagent', sigmaProvider);
    if (sigmaModel && !isEmbeddingModel(sigmaModel)) {
        selectedModels.push({ agent: 'SIGMA', model: sigmaModel, provider: sigmaProvider, enabled: true });
    }
    
    // Sub-agents - only show if not disabled
    const subAgents = [
        { name: 'CmdlineExtract', prefix: 'cmdlineextract', providerId: 'cmdlineextract-provider' },
        { name: 'ProcTreeExtract', prefix: 'proctreeextract', providerId: 'proctreeextract-provider' },
        { name: 'HuntQueriesExtract', prefix: 'huntqueriesextract', providerId: 'huntqueriesextract-provider' },
        { name: 'RegistryExtract', prefix: 'registryextract', providerId: 'registryextract-provider' },
        { name: 'ServicesExtract', prefix: 'servicesextract', providerId: 'servicesextract-provider' },
        { name: 'ScheduledTasksExtract', prefix: 'scheduledtasksextract', providerId: 'scheduledtasksextract-provider' },
        { name: 'NetworkIndicatorExtract', prefix: 'networkindicatorextract', providerId: 'networkindicatorextract-provider' }
    ];

    subAgents.forEach(subAgent => {
        const modelInfo = getModelWithProvider(subAgent.prefix, subAgent.providerId, subAgent.name);
        if (modelInfo) {
            modelInfo.enabled = !disabled.has(subAgent.name);
            selectedModels.push(modelInfo);
        }
    });


    return selectedModels;
}

// Function to update the config display (same source as Agent-evals: saved config only)
function updateConfigDisplay() {
    if (typeof renderWorkflowConfigDisplay === 'function' && currentConfig) {
        renderWorkflowConfigDisplay(currentConfig);
    }
}

// Generate LMStudio context window commands
async function showGenerateCommandsModal() {
    // Clean up existing modal
    const existingModal = document.getElementById('generateCommandsModal');
    if (existingModal) {
        if (window.ModalManager) {
            const stack = window.ModalManager.getStack();
            while (stack.includes('generateCommandsModal')) {
                const index = stack.indexOf('generateCommandsModal');
                stack.splice(index, 1);
            }
        }
        existingModal.remove();
        await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    // Get all selected models
    const uiModels = getAllSelectedModelsWithProviders();
    
    // Filter to only LMStudio models and exclude embedding models
    const embeddingModels = ['text-embedding-e5-base-v2', 'ibm-research/CTI-BERT', 'text-embedding', 'embedding'];
    const lmstudioModels = uiModels.filter(m => 
        m.provider === 'lmstudio' && 
        !embeddingModels.some(emb => m.model.toLowerCase().includes(emb.toLowerCase()))
    );
    
    if (lmstudioModels.length === 0) {
        showNotification('No LMStudio models found in current configuration.', 'warning');
        return;
    }
    
    // Get context lengths from config or use defaults
    const contextLength = await ModalManager.prompt('Enter context length (tokens):', '16384', { title: 'Context Length', confirmText: 'Generate', placeholder: 'e.g. 16384' });
    if (!contextLength || isNaN(contextLength)) {
        return;
    }
    
    const ctxLen = parseInt(contextLength);
    
    // Generate commands
    let commands = [];
    commands.push('# LMStudio Context Window Commands');
    commands.push('# Generated from workflow configuration');
    commands.push('');
    
    // Group by model to avoid duplicates
    const uniqueModels = new Map();
    lmstudioModels.forEach(m => {
        const modelName = m.model;
        if (!uniqueModels.has(modelName)) {
            uniqueModels.set(modelName, {
                model: modelName,
                agents: []
            });
        }
        uniqueModels.get(modelName).agents.push(m.agent);
    });
    
    // Generate command for each unique model
    uniqueModels.forEach((info, modelName) => {
        commands.push(`# ${info.agents.join(', ')}`);
        commands.push(`./scripts/set_lmstudio_context.sh "${modelName}" ${ctxLen}`);
        commands.push('');
    });
    
    const commandsText = commands.join('\n');
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'generateCommandsModal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
    modal.innerHTML = `
        <div class="card-xl max-w-3xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div class="flex justify-between items-center p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 class="text-xl font-semibold text-gray-900 dark:text-white">Generate LMStudio Context Commands</h3>
                <button onclick="closeGenerateCommandsModal()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="p-6 overflow-y-auto flex-1">
                <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    Copy these commands to set context windows for your LMStudio models:
                </p>
                <textarea id="generatedCommands" readonly class="w-full h-64 p-4 font-mono text-sm bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-lg border border-gray-300 dark:border-gray-600">${commandsText}</textarea>
            </div>
            <div class="flex justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
                <button onclick="copyGeneratedCommands()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors">
                    📋 Copy Commands
                </button>
                <button onclick="closeGenerateCommandsModal()" class="px-4 py-2 bg-gray-300 hover:bg-gray-400 dark:bg-gray-600 dark:hover:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-md transition-colors">
                    Close
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeGenerateCommandsModal() {
    if (window.ModalManager) {
        window.ModalManager.close('generateCommandsModal');
    } else {
        const modal = document.getElementById('generateCommandsModal');
        if (modal) {
            modal.remove();
        }
    }
}

function copyGeneratedCommands() {
    const textarea = document.getElementById('generatedCommands');
    if (textarea) {
        textarea.select();
        document.execCommand('copy');
        
        // Show feedback
        const button = event.target;
        const originalText = button.textContent;
        button.textContent = '✓ Copied!';
        button.classList.add('bg-emerald-600', 'hover:bg-green-700');
        button.classList.remove('bg-blue-600', 'hover:bg-blue-700');
        
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('bg-emerald-600', 'hover:bg-green-700');
            button.classList.add('bg-blue-600', 'hover:bg-blue-700');
        }, 2000);
    }
}

// Get only LMStudio models from selected models

function getLMStudioModelsOnly() {
    const models = new Set();
    
    // Get disabled state
    const disabled = typeof disabledExtractAgents !== 'undefined' ? disabledExtractAgents : new Set();
    
    // Main agent models - only include if provider is 'lmstudio' and agent is enabled
    // Rank Agent - check if enabled
    const rankAgentEnabled = document.getElementById('rank-agent-enabled')?.checked !== false;
    if (rankAgentEnabled) {
        const rankProviderSelect = document.getElementById('rankagent-provider');
        if (rankProviderSelect) {
            const rankProvider = (rankProviderSelect.value || '').trim().toLowerCase();
            if (rankProvider === 'lmstudio') {
                const rankModel = document.getElementById('rankagent-model-2')?.value.trim();
                if (rankModel && !isEmbeddingModel(rankModel)) models.add(rankModel);
            }
        }
    }
    
    // Extract Agent - always enabled (no toggle)
    const extractProviderSelect = document.getElementById('extractagent-provider');
    if (extractProviderSelect) {
        const extractProvider = (extractProviderSelect.value || '').trim().toLowerCase();
        if (extractProvider === 'lmstudio') {
            const extractModel = document.getElementById('extractagent-model-2')?.value.trim();
            if (extractModel && !isEmbeddingModel(extractModel)) models.add(extractModel);
        }
    }
    
    
    // Sub-agent models (only if explicitly set, not using ExtractAgent model)
    // Sub-agents have their own provider selectors
    const subAgents = [
        { name: 'CmdlineExtract', prefix: 'cmdlineextract', providerId: 'cmdlineextract-provider' },
        { name: 'ProcTreeExtract', prefix: 'proctreeextract', providerId: 'proctreeextract-provider' }
    ];
    
    subAgents.forEach(subAgent => {
        // Skip if agent is disabled
        if (disabled.has(subAgent.name)) return;
        
        const providerSelect = document.getElementById(subAgent.providerId);
        if (!providerSelect) return; // Skip if provider dropdown doesn't exist
        
        const provider = (providerSelect.value || '').trim().toLowerCase();
        if (provider !== 'lmstudio') return; // Only process LMStudio providers
        
        // Use getActiveAgentModelValue to get the correct model (handles -model and -model-2 variants)
        const model = getActiveAgentModelValue(subAgent.prefix, 'lmstudio');
        if (model && !isEmbeddingModel(model)) {
            models.add(model);
        }
    });
    
    // Note: OS Detection embedding and Sigma embedding models are excluded (they're text encoders)
    
    return Array.from(models).sort();
}


// Function to get current form state
function getCurrentFormState() {
    // Get agent models from form using unified system (includes providers)
    const agent_models = collectAllAgentConfigs();

    agent_models.OSDetectionAgent_selected_os = ['Windows'];

    const disabled_agents = Array.from(disabledExtractAgents || []);

    // Get agent prompts from global agentPrompts variable (merged with currentConfig)
    const promptsSource = {
        ...(currentConfig?.agent_prompts || {}),
        ...(agentPrompts || {})
    };
    const extractSettings = promptsSource.ExtractAgentSettings ? { ...promptsSource.ExtractAgentSettings } : {};
    extractSettings.disabled_agents = Array.from(disabled_agents || []);
    promptsSource.ExtractAgentSettings = extractSettings;

    return {
        junk_filter_threshold: parseFloat(document.getElementById('junkFilterThreshold')?.value || '0'),
        ranking_threshold: parseFloat(document.getElementById('rankingThreshold')?.value || '0'),
        similarity_threshold: parseFloat(document.getElementById('similarityThreshold')?.value || '0'),
        description: null,
        agent_models: agent_models,
        disabled_extract_agents: disabled_agents,
        sigma_fallback_enabled: document.getElementById('sigma-fallback-enabled')?.checked || false,
        rank_agent_enabled: document.getElementById('rank-agent-enabled')?.checked ?? true,
        agent_prompts: promptsSource
    };
}

// Function to check if there are unsaved changes
function checkForUnsavedChanges() {
    if (!originalConfigState || !currentConfig) {
        return false;
    }
    
    const currentState = getCurrentFormState();
    const originalState = originalConfigState;
    
    // Compare thresholds
    if (Math.abs(currentState.junk_filter_threshold - originalState.junk_filter_threshold) > 0.0001) return true;
    if (Math.abs(currentState.ranking_threshold - originalState.ranking_threshold) > 0.0001) return true;
    if (Math.abs(currentState.similarity_threshold - originalState.similarity_threshold) > 0.0001) return true;
    
    
    // Compare disabled extract agents
    const currentDisabled = new Set(currentState.disabled_extract_agents || []);
    const originalDisabled = new Set((originalState.disabled_extract_agents || []));
    if (currentDisabled.size !== originalDisabled.size) return true;
    for (const name of currentDisabled) {
        if (!originalDisabled.has(name)) return true;
    }
    
    // Compare agent_models - check all keys including sub-agent models and temperatures
    const currentModels = currentState.agent_models || {};
    const originalModels = originalState.agent_models || currentConfig.agent_models || {};
    
    // Get all unique keys from both objects
    const allKeys = new Set([...Object.keys(currentModels), ...Object.keys(originalModels)]);
    
    for (const key of allKeys) {
        const currentValue = currentModels[key];
        const originalValue = originalModels[key];
        
        // Handle numeric comparison for temperatures (account for floating point precision)
        if (key.includes('_temperature')) {
            const currentNum = typeof currentValue === 'number' ? currentValue : parseFloat(currentValue) || 0.0;
            const originalNum = typeof originalValue === 'number' ? originalValue : parseFloat(originalValue) || 0.0;
            if (Math.abs(currentNum - originalNum) > 0.0001) return true;
        } else {
            // String comparison for model names
            if (currentValue !== originalValue) return true;
        }
    }
    
    // Compare sigma_fallback_enabled
    if (currentState.sigma_fallback_enabled !== originalState.sigma_fallback_enabled) return true;
    
    // Compare rank_agent_enabled
    if (currentState.rank_agent_enabled !== originalState.rank_agent_enabled) return true;
    
    // Compare agent_prompts - deep comparison
    const currentPrompts = currentState.agent_prompts || {};
    const originalPrompts = originalState.agent_prompts || currentConfig.agent_prompts || {};
    
    // Compare all agent prompts
    const allPromptKeys = new Set([...Object.keys(currentPrompts), ...Object.keys(originalPrompts)]);
    for (const key of allPromptKeys) {
        const currentPrompt = currentPrompts[key];
        const originalPrompt = originalPrompts[key];
        
        // Deep comparison using JSON stringify for nested objects
        if (JSON.stringify(currentPrompt) !== JSON.stringify(originalPrompt)) return true;
    }
    
    return false;
}

// Function to update save button state
function updateSaveButtonState() {
    const saveButton = document.getElementById('save-config-button');
    if (!saveButton) {
        console.warn('Save button not found');
        return;
    }
    
    const hasChanges = checkForUnsavedChanges();
    saveButton.disabled = !hasChanges;
    
    // Update button text and styling based on state
    if (hasChanges) {
        saveButton.classList.remove('opacity-50', 'cursor-not-allowed');
        saveButton.classList.add('hover:bg-purple-700');
        saveButton.style.opacity = '1';
        saveButton.style.cursor = 'pointer';
    } else {
        saveButton.classList.add('opacity-50', 'cursor-not-allowed');
        saveButton.classList.remove('hover:bg-purple-700');
        saveButton.style.opacity = '0.5';
        saveButton.style.cursor = 'not-allowed';
    }
    
    console.log('Save button state updated:', { hasChanges, disabled: saveButton.disabled });
}

    // Initialize original state and set up change listeners
function initializeChangeTracking() {
    // Store original state after config is loaded
    resetOriginalConfigStateFromCurrent();
    
    // Add change listeners to all configurable fields
    const fields = [
        'junkFilterThreshold',
        'rankingThreshold',
        'similarityThreshold'
    ];
    
    fields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', updateSaveButtonState);
            field.addEventListener('change', updateSaveButtonState);
        }
    });
    
    // Add change listeners to agent model selects
    const modelSelects = [
        'rankagent-model-2',
        'rankagent-temperature',
        'extractagent-model-2',
        'sigmaagent-model-2'
    ];
    
    modelSelects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (select) {
            select.addEventListener('change', updateSaveButtonState);
            select.addEventListener('input', updateSaveButtonState);
        }
    });
    
    // Add change listeners to extract sub-agent enable toggles
    extractSubAgents.forEach(agentName => {
        const toggle = document.getElementById(`toggle-${agentName.toLowerCase()}-enabled`);
        if (toggle) {
            toggle.addEventListener('change', updateSaveButtonState);
        }
    });
    
    // Add change listeners to sigma fallback and rank agent enabled toggles
    // Note: These now use onchange handlers in HTML for autosave, but we keep listeners for save button state
    const sigmaFallbackToggle = document.getElementById('sigma-fallback-enabled');
    if (sigmaFallbackToggle) {
        sigmaFallbackToggle.addEventListener('change', updateSaveButtonState);
    }
    
    const rankAgentToggle = document.getElementById('rank-agent-enabled');
    if (rankAgentToggle) {
        rankAgentToggle.addEventListener('change', updateSaveButtonState);
    }
    
    // Add change listeners to prompt input fields using event delegation
    // This handles dynamically rendered prompts
    const agentPromptsContainer = document.getElementById('agentPromptsContainer');
    if (agentPromptsContainer) {
        agentPromptsContainer.addEventListener('input', (e) => {
            if (e.target.matches('[id$="-prompt-2"], [id$="-instructions-2"], [id$="-prompt-system"], [id$="-prompt-user"], [id$="-prompt-system-2"], [id$="-prompt-user-2"]')) {
                updateSaveButtonState();
            }
        });
        agentPromptsContainer.addEventListener('change', (e) => {
            if (e.target.matches('[id$="-prompt-2"], [id$="-instructions-2"], [id$="-prompt-system"], [id$="-prompt-user"], [id$="-prompt-system-2"], [id$="-prompt-user-2"]')) {
                updateSaveButtonState();
            }
        });
    }
    
    // Also attach to document for any prompts rendered outside the container
    document.addEventListener('input', (e) => {
        if (e.target.matches('[id$="-prompt-2"], [id$="-instructions-2"], [id$="-prompt-system"], [id$="-prompt-user"]')) {
            updateSaveButtonState();
        }
    });
    document.addEventListener('change', (e) => {
        if (e.target.matches('[id$="-prompt-2"], [id$="-instructions-2"], [id$="-prompt-system"], [id$="-prompt-user"]')) {
            updateSaveButtonState();
        }
    });
    
    // Initial button state - ensure button starts disabled
    const saveButton = document.getElementById('save-config-button');
    if (saveButton) {
        saveButton.disabled = true;
        saveButton.classList.add('opacity-50', 'cursor-not-allowed');
        saveButton.style.opacity = '0.5';
        saveButton.style.cursor = 'not-allowed';
    }
    
    // Then update based on actual changes
    updateSaveButtonState();
}

const workflowConfigForm = document.getElementById('workflowConfigForm');
if (workflowConfigForm) {
    workflowConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
    
    // Check if there are any changes to save
    if (!checkForUnsavedChanges()) {
        console.log('No changes to save');
        return;
    }

    // Validate all thresholds before submission (run before clamping so invalid values block save)
    const junkFilterInput = document.getElementById('junkFilterThreshold');
    const rankingInput = document.getElementById('rankingThreshold');
    const similarityInput = document.getElementById('similarityThreshold');
    const junkFilterValid = junkFilterInput ? validateThreshold(junkFilterInput, 0, 1) : true;
    const rankingValid = rankingInput ? validateThreshold(rankingInput, 0, 10) : true;
    const similarityValid = similarityInput ? validateThreshold(similarityInput, 0, 1) : true;

    if (!junkFilterValid || !rankingValid || !similarityValid) {
        showNotification('Please fix the validation errors before saving.', 'error');
        return;
    }

    // Clamp any remaining out-of-range number inputs before building payload
    const numberInputs = workflowConfigForm.querySelectorAll('input[type="number"]');
    let hasInvalidInputs = false;
    numberInputs.forEach(input => {
        const min = parseFloat(input.getAttribute('min'));
        const max = parseFloat(input.getAttribute('max'));
        if (!isNaN(min) || !isNaN(max)) {
            const value = parseFloat(input.value);
            if (!isNaN(value)) {
                let clampedValue = value;
                if (!isNaN(min) && value < min) {
                    clampedValue = min;
                    hasInvalidInputs = true;
                }
                if (!isNaN(max) && value > max) {
                    clampedValue = max;
                    hasInvalidInputs = true;
                }
                if (clampedValue !== value) {
                    input.value = clampedValue;
                    console.warn(`Clamped ${input.name || input.id} from ${value} to ${clampedValue}`);
                }
            }
        }
    });

    if (hasInvalidInputs) {
        console.log('Some values were clamped to valid ranges. Saving with corrected values...');
    }
    
    // Collect all agent provider/model values using unified system
    const collectedAgentConfigs = collectAllAgentConfigs();

    const formData = {
        min_hunt_score: currentConfig?.min_hunt_score || 97.0,
        junk_filter_threshold: parseFloat(document.getElementById('junkFilterThreshold').value),
        ranking_threshold: parseFloat(document.getElementById('rankingThreshold').value),
        similarity_threshold: parseFloat(document.getElementById('similarityThreshold').value),
        description: null,
        agent_models: {
            ...collectedAgentConfigs
        },
        sigma_fallback_enabled: document.getElementById('sigma-fallback-enabled')?.checked || false,
        rank_agent_enabled: document.getElementById('rank-agent-enabled')?.checked ?? true
    };
    
    // Merge agent_prompts and include disabled extract agents
    const promptsSource = {
        ...(currentConfig?.agent_prompts || {}),
        ...(agentPrompts || {})
    };
    const extractSettings = promptsSource.ExtractAgentSettings ? { ...promptsSource.ExtractAgentSettings } : {};
    
    // CRITICAL: Read disabled agents directly from DOM checkboxes to ensure accuracy
    // This is the source of truth, not the disabledExtractAgents Set which might be stale
    const disabledFromDOM = [];
    EXTRACT_SUB_AGENTS.forEach(agentName => {
        const checkbox = document.getElementById(`toggle-${agentName.toLowerCase()}-enabled`);
        if (checkbox && !checkbox.checked) {
            disabledFromDOM.push(agentName);
        }
    });
    
    // Also sync the Set for consistency
    disabledExtractAgents = new Set(disabledFromDOM);
    
    extractSettings.disabled_agents = disabledFromDOM;
    
    // Store disabledFromDOM in formData for use in response handler
    formData._disabledFromDOM = disabledFromDOM;
    promptsSource.ExtractAgentSettings = extractSettings;
    formData.agent_prompts = promptsSource;
    
    // Validate RankAgent model is set (only required when Rank Agent is enabled)
    if (formData.rank_agent_enabled && !formData.agent_models.RankAgent) {
        showNotification('Rank Agent model is required. Please select a model from the dropdown.', 'error');
        document.getElementById('rankagent-model-2')?.focus();
        return;
    }
    
    // Remove null/empty values from agent_models
    const cleanedAgentModels = {};
    for (const [key, value] of Object.entries(formData.agent_models)) {
        if (value !== null && value !== '') {
            cleanedAgentModels[key] = value;
        }
    }
    formData.agent_models = Object.keys(cleanedAgentModels).length > 0 ? cleanedAgentModels : null;
    
    // Show loading state
    const saveButton = document.getElementById('save-config-button');
    const originalButtonText = saveButton.textContent;
    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';
    saveButton.classList.add('opacity-50', 'cursor-not-allowed');
    
    try {
        const response = await fetch('/api/workflow/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        
        if (response.ok) {
            const updatedConfig = await response.json();
            
            // Update currentConfig with the response
            currentConfig = updatedConfig;
            agentModels = updatedConfig.agent_models || {};
            
            // Re-apply agent configs to ensure Top_P and other values are set correctly
            if (updatedConfig.agent_models) {
                applyAgentConfigs(updatedConfig.agent_models);
            }
            
            // Update form fields and UI directly instead of fetching again
            if (updatedConfig.ranking_threshold !== undefined) {
                document.getElementById('rankingThreshold').value = updatedConfig.ranking_threshold;
            }
            if (updatedConfig.junk_filter_threshold !== undefined) {
                document.getElementById('junkFilterThreshold').value = updatedConfig.junk_filter_threshold;
            }
            if (updatedConfig.similarity_threshold !== undefined) {
                document.getElementById('similarityThreshold').value = updatedConfig.similarity_threshold;
            }
            ['junkFilterThreshold', 'rankingThreshold', 'similarityThreshold'].forEach(updateThresholdDisplay);

            // Update config display using shared component (same source as Agent-evals: saved config only)
            if (typeof renderWorkflowConfigDisplay === 'function') {
                renderWorkflowConfigDisplay(updatedConfig);
            }

            // Update currentConfig first to ensure syncExtractAgentTogglesFromConfig uses the latest config
            currentConfig = updatedConfig;
            
            // CRITICAL: Ensure currentConfig.agent_prompts includes ExtractAgentSettings with disabled_agents
            // Use what we actually sent in the form submission, not just what the server returned
            if (formData.agent_prompts && formData.agent_prompts.ExtractAgentSettings) {
                if (!currentConfig.agent_prompts) {
                    currentConfig.agent_prompts = {};
                }
                currentConfig.agent_prompts.ExtractAgentSettings = formData.agent_prompts.ExtractAgentSettings;
            }
            
            // Update agentModels global variable with the saved config before reloading
            agentModels = updatedConfig.agent_models || {};
            
            // CRITICAL: Use disabledFromDOM from form submission if available (what we actually sent)
            // Otherwise fall back to reading from the response
            const savedDisabledAgents = formData._disabledFromDOM || getDisabledExtractAgentsFromConfig(updatedConfig);
            disabledExtractAgents = new Set(savedDisabledAgents);
            
            syncExtractAgentTogglesFromConfig();
            
            // Show success state immediately (don't wait for reloads)
            saveButton.textContent = '✓ Saved!';
            saveButton.classList.remove('bg-purple-600', 'hover:bg-purple-700');
            saveButton.classList.add('bg-emerald-600');
            
            // Restore button state after 2 seconds, regardless of reload status
            setTimeout(() => {
                saveButton.textContent = originalButtonText;
                saveButton.classList.remove('bg-emerald-600');
                saveButton.classList.add('bg-purple-600', 'hover:bg-purple-700');
                saveButton.disabled = false;
                updateSaveButtonState();
            }, 2000);
            
            // Reload agent models and prompts in background (with timeout protection)
            Promise.race([
                Promise.all([
                    loadAgentModels().then(() => {
                        // Re-apply agent configs after models are reloaded to ensure Top_P values are set
                        if (updatedConfig.agent_models) {
                            applyAgentConfigs(updatedConfig.agent_models);
                        }
                    }).catch(err => {
                        console.warn('Error reloading agent models after save:', err);
                    }),
                    loadAgentPrompts().catch(err => {
                        console.warn('Error reloading agent prompts after save:', err);
                    })
                ]),
                new Promise(resolve => setTimeout(resolve, 10000)) // 10 second timeout
            ]).then(() => {
                // Sync toggles again after prompts are reloaded to ensure UI is in sync
                syncExtractAgentTogglesFromConfig();
                // Initialize change tracking after save
                initializeChangeTracking();
            }).catch(err => {
                console.warn('Error in post-save reload:', err);
                // Still restore UI state even if reloads fail
                syncExtractAgentTogglesFromConfig();
                initializeChangeTracking();
            });
        } else {
            const error = await response.json();
            // Handle error detail - could be string, array, or object
            let errorMessage = 'Unknown error';
            if (error.detail) {
                if (Array.isArray(error.detail)) {
                    // Pydantic validation errors - format them nicely
                    errorMessage = error.detail.map(e => {
                        if (typeof e === 'string') return e;
                        if (e.msg) return `${e.loc?.join('.') || 'Field'}: ${e.msg}`;
                        return JSON.stringify(e);
                    }).join('\n');
                } else if (typeof error.detail === 'string') {
                    errorMessage = error.detail;
                } else {
                    errorMessage = JSON.stringify(error.detail, null, 2);
                }
            }
            showNotification('Error updating configuration: ' + errorMessage, 'error');
            saveButton.disabled = false;
            saveButton.textContent = originalButtonText;
            updateSaveButtonState();
        }
    } catch (error) {
        console.error('Error saving config:', error);
        showNotification('Error saving configuration', 'error');
        saveButton.disabled = false;
        saveButton.textContent = originalButtonText;
        updateSaveButtonState();
    }
    });
}


// ---------------------------------------------------------------------------
// Appended from the template tail. ORDER IS LOAD-BEARING: this block reassigns
// window.renderSubAgentCommercialInputs, overriding the assignment made earlier
// in this file. Inline it ran after the config region and won; it has to keep
// running last, so it travels here rather than staying inline ahead of us.
// ---------------------------------------------------------------------------

// --- Global fallback definitions to ensure sub-agent provider inputs always render ---
const subAgentModelKeysGlobal = {
    cmdlineextract: 'CmdlineExtract_model',
    proctreeextract: 'ProcTreeExtract_model',
    huntqueriesextract: 'HuntQueriesExtract_model',
    registryextract: 'RegistryExtract_model',
    servicesextract: 'ServicesExtract_model',
    scheduledtasksextract: 'ScheduledTasksExtract_model',
    networkindicatorextract: 'NetworkIndicatorExtract_model'
};

function renderSubAgentCommercialInputsGlobal(agentPrefix) {
    const modelKey = subAgentModelKeysGlobal[agentPrefix];
    if (!modelKey) return;
    const providerSelect = document.getElementById(`${agentPrefix}-provider`);
    const provider = (providerSelect?.value || getDefaultProvider()).toString().trim().toLowerCase();
    const currentModel = agentModels?.[modelKey] || '';

    // Always use buildCommercialProviderInput for consistency with main agents
    ['openai', 'codex', 'anthropic'].forEach(p => {
        const container = document.querySelector(`[data-agent-prefix="${agentPrefix}"][data-provider="${p}"]`);
        if (!container) {
            console.warn(`Container not found for ${agentPrefix} provider ${p}`);
            return;
        }

        // Use buildCommercialProviderInput which handles both catalog and manual input cases
        if (typeof buildCommercialProviderInput === 'function') {
            let html = buildCommercialProviderInput(agentPrefix, p, provider, currentModel);
            // Sub-agents use smaller padding (px-2 py-1.5) and text-xs instead of px-3 py-2 and text-sm
            html = html.replace(/px-3 py-2/g, 'px-2 py-1.5').replace(/text-sm/g, 'text-xs');
            container.innerHTML = html;
        } else {
            // Fallback to manual input if buildCommercialProviderInput not available
            const placeholder = p === 'openai' ? 'gpt-4o-mini' : p === 'codex' ? 'gpt-5.6-luna' : 'claude-sonnet-4-5';
            container.innerHTML = `
                <input type="text"
                       id="${agentPrefix}-model-${p}"
                       name="agent_models[${modelKey}]"
                       class="w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white font-mono text-xs"
                       placeholder="${placeholder}"
                       value="${escapeHtml(currentModel || '')}"
                       onchange="autoSaveModelChange()">
            `;
        }
    });
}
window.renderSubAgentCommercialInputs = renderSubAgentCommercialInputsGlobal;
