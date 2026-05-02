# Prompt Mapping: File System to Database

## Source Of Truth

- Live prompts live in the database workflow config (`agent_prompts`). Disk files in `src/prompts/` are **seed defaults** read only on bootstrap, empty fallback, or explicit reset.
- Canonical agent names: `src/config/workflow_config_schema.py`
- Loader logic: `src/config/workflow_config_loader.py`

If this document and code disagree, trust the code.

## Workflow Agents (Mapped to DB)

These agents have both a seed file in `src/prompts/` and a database entry in workflow config. The database takes precedence at runtime.

| Seed File | DB Agent Name | Notes |
|-----------|---------------|-------|
| `ExtractAgent` | `ExtractAgent` | Parent config for all extract sub-agents (model/provider fallback) |
| `lmstudio_sigma_ranking.txt` | `RankAgent` | Primary ranking prompt |
| `sigma_generation.txt` | `SigmaAgent` | Sigma rule generation |
| `CmdlineExtract` | `CmdlineExtract` | Command-line artifact extraction |
| `ProcTreeExtract` | `ProcTreeExtract` | Process lineage extraction |
| `HuntQueriesExtract` | `HuntQueriesExtract` | Hunt query extraction |
| `RegistryExtract` | `RegistryExtract` | Registry artifact extraction |
| `ServicesExtract` | `ServicesExtract` | Windows services extraction |
| `ScheduledTasksExtract` | `ScheduledTasksExtract` | Scheduled tasks extraction |
| `QAAgentCMD` | `CmdLineQA` | QA for CmdlineExtract |
| `ProcTreeQA` | `ProcTreeQA` | QA for ProcTreeExtract |
| `HuntQueriesQA` | `HuntQueriesQA` | QA for HuntQueriesExtract |
| `RegistryQA` | `RegistryQA` | QA for RegistryExtract |
| `ServicesQA` | `ServicesQA` | QA for ServicesExtract |
| `ScheduledTasksQA` | `ScheduledTasksQA` | QA for ScheduledTasksExtract |

## File-Only Prompts (Not in Workflow Config)

| Seed File | Usage |
|-----------|-------|
| `OSDetectionAgent` | Referenced by scoring scripts; OS detection uses regex at runtime, not an LLM call |
| `ObservablesCountAgent` | Used in evaluation scripts only |

## Sigma Support Prompts

| File | Purpose |
|------|---------|
| `sigma_system.txt` | Sigma system context |
| `sigma_guidance.txt` | Sigma guidance/instructions |
| `sigma_generate_multi.txt` | Multi-rule Sigma generation |
| `sigma_generation_simple.txt` | Simplified Sigma generation |
| `sigma_enrichment.txt` | Sigma rule enrichment |
| `sigma_repair_single.txt` | Single-rule Sigma repair |

## Utility Prompts

| File | Purpose |
|------|---------|
| `article_summary.txt` | Article summarization |
| `metadata_summary.txt` | Metadata summarization |

## Alternate/Historical Versions (Not Active)

| File | Notes |
|------|-------|
| `huntability_ranking.txt` | Alternative ranking prompt |
| `huntability_ranking_alt.txt` | Alternative ranking variant |
| `llm_sigma_ranking.txt` | Generic LLM ranking |
| `llm_sigma_ranking_simple.txt` | Simplified LLM ranking |
| `SIGMA_Huntability_Ranking_v2C-R.md` | Historical documentation |

## Priority Order

1. **Database** (workflow config `agent_prompts`) -- takes precedence
2. **Seed file** (`src/prompts/`) -- fallback on bootstrap or reset

_Last updated: 2026-05-01_
