# Workflow Context Length Issues - Fix Guide

## Problem

Workflow executions are failing with context length errors:
```
Error: LMStudio model 'gemma-3n-e4b-it-text' has context length of 4096 tokens, 
which is below the required threshold of 16384 tokens.
```

## Root Cause

Models in LMStudio are loaded with default context lengths (often 2048-4096 tokens), but the workflow requires 16384 tokens for proper operation.

## Solution

### Option 1: Load All Workflow Models (Recommended)

Run the utility script to load all configured models with proper context:

```bash
python utils/load_workflow_models.py
```

This script:
- Reads active workflow configuration from database
- Loads all configured models with 16384 context tokens
- Verifies each model can be loaded

**Note:** Models are loaded one at a time and unloaded after each test to verify they can be loaded. The workflow will load models on-demand during execution.

### Option 2: Load Specific Model

If you know which model is failing, load it manually:

```bash
lms load gemma-3n-e4b-it-text --context-length 16384
```

Or use the utility script:

```bash
python utils/load_lmstudio_models.py gemma-3n-e4b-it-text --context-length 16384
```

### Option 3: Load All Models from Environment

If using environment variables:

```bash
python utils/load_lmstudio_models.py --all
```

## Current Workflow Models

To see which models are configured in your workflow:

```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -c \
  "SELECT agent_models FROM agentic_workflow_config WHERE is_active = true ORDER BY version DESC LIMIT 1;"
```

## Prevention

The workflow checks context length before execution and will fail early if insufficient. To prevent failures:

1. **Before running workflows**: Run `python utils/load_workflow_models.py` to verify all models can be loaded
2. **After changing workflow config**: Re-run the script to load any new models
3. **On LMStudio restart**: Models need to be reloaded with proper context

## Troubleshooting

### Model Not Found
If a model is not found in LMStudio:
- Check model name matches exactly (case-sensitive)
- Verify model is downloaded in LMStudio
- Use `lms ls` to see available models

### Insufficient Resources
If model fails to load due to resource constraints:
- Close other applications to free RAM
- Use smaller quantization (Q4_K_M instead of Q8_0)
- Load models one at a time during workflow execution

### Context Still Too Small
If workflow still fails after loading:
- Verify context length: `lms ps` should show 16384 in CONTEXT column
- Check if model supports 16384 (some small models may not)
- Consider using a different model that supports larger context

## Related Files

- `utils/load_workflow_models.py` - Load all workflow models from database config
- `utils/load_lmstudio_models.py` - Load models from environment variables
- `src/workflows/agentic_workflow.py` - Workflow context length check (line 1369-1383)
- `src/services/llm_service.py` - Context length validation logic

