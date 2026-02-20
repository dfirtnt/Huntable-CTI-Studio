# Agent configuration schema (v2)

## Overview

Workflow agent configuration uses a **normalized hierarchical schema (v2)** with Pydantic validation, backward-compatible migration from the legacy flat format, and typed models. Config is stored in the DB as before (flat JSONB and columns); at load time it is migrated to v2 and validated.

## Structural improvements

- **Single casing**: PascalCase for schema keys (Version, Metadata, Thresholds, Agents, Embeddings, QA, Features, Prompts, Execution).
- **Nested agents**: Instead of flat keys like `RankAgent_provider`, `RankAgent_temperature`, config is structured as `Agents.RankAgent.Provider`, `Agents.RankAgent.Temperature`, etc. Each agent has required fields: Provider, Model, Temperature, TopP, Enabled.
- **Dedicated sections**:
  - **Thresholds**: MinHuntScore, RankingThreshold, SimilarityThreshold, JunkFilterThreshold, AutoTriggerHuntScoreThreshold.
  - **Agents**: All LLM agents (RankAgent, ExtractAgent, SigmaAgent, sub-agents, QA agents, OSDetectionFallback).
  - **Embeddings**: OsDetection and Sigma (moved out of `agent_models`).
  - **QA**: Enabled (per-agent) and MaxRetries.
  - **Features**: SigmaFallbackEnabled, OsDetectionFallbackEnabled, RankAgentEnabled, CmdlineAttentionPreprocessorEnabled.
  - **Prompts**: Per-agent prompt/instructions (content unchanged; relocation only).
  - **Execution**: ExtractAgentSettings.DisabledAgents, OsDetectionSelectedOs.
- **Naming normalization**: Legacy `CmdLineQA` is normalized to `CmdlineQA` in v2.
- **No unknown keys**: Schema validation forbids unknown root keys; validation errors are explicit.

## Backward compatibility

- **Read**: DB rows (or preset JSON) are always passed through `load_workflow_config()`. If the payload is v1 (or legacy flat), it is migrated to v2 and validated. The API response is built from the v2 model in legacy shape (flat `agent_models`, etc.) so the UI and other consumers are unchanged.
- **Write**: PUT and preset apply still accept the legacy flat shape. Config is persisted as flat in the DB. Optional: future endpoints can accept v2 JSON and normalize before persist.
- **Legacy consumers**: `WorkflowConfigV2.flatten_for_llm_service()` produces the flat key format expected by LLMService, SigmaGenerationService, and the workflow. No change to those call sites until they are refactored to use nested config.

## Modules

| Module | Role |
|--------|------|
| `src.config.workflow_config_schema` | Pydantic models (AgentConfig, WorkflowConfigV2, ThresholdConfig, etc.). |
| `src.config.workflow_config_migrate` | `migrate_v1_to_v2(raw)` — legacy flat → v2 dict; logs deprecation for legacy keys. |
| `src.config.workflow_config_loader` | `load_workflow_config(raw)` — migrate, validate, return WorkflowConfigV2. `config_row_to_flat_agent_models(row)` for legacy callers. |

## Version and validation

- **Version field**: v2 config must have `Version: "2.0"`. v1 or missing version triggers migration.
- **Validation**: Required sections and types are enforced. Invalid types or missing required agent fields raise Pydantic `ValidationError`.
- **Feature/agent gating**: If a feature is disabled (e.g. RankAgentEnabled false) or an agent has Enabled false, that agent must not execute (enforced by workflow logic; schema documents the contract).

## Example and presets

- **Example v2 JSON**: `config/schema/workflow_config_v2_example.json` (placeholder values).
- **Baseline v2 example**: `python3 scripts/build_baseline_presets.py --v2` writes `config/schema/workflow_config_v2_baseline_example.json`.
- **Baseline presets (v1)**: `config/presets/AgentConfigs/*.json` remain v1 for UI “Import from file” compatibility; the loader accepts both when config is loaded server-side.

## ExtractAgent (supervisor)

ExtractAgent is the supervisor; sub-agents (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract) inherit provider/model from ExtractAgent when not configured. The schema types `Agents.ExtractAgent` explicitly; fallback behavior is implemented in the workflow and LLMService.
