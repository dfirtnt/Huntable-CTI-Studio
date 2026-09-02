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
| `lmstudio_sigma_ranking.txt` | `RankAgent` | Primary ranking seed; the canonical `AGENT_PROMPT_FILES["RankAgent"]` entry (`src/utils/default_agent_prompts.py`) |
| `rank_article.txt` | `RankAgent` | Fallback user-message template for `LLMService.rank_article()` when the workflow config supplies no `prompt_template` (see `src/services/llm_service.py`) |
| `sigma_generation.txt` | `SigmaAgent` | Sigma rule generation |
| `sigma_repair_single.txt` | `SigmaRepair` | Per-rule repair pass after pySigma validation failure; receives `{validation_errors}` and `{original_rule}` |
| `CmdlineExtract` | `CmdlineExtract` | Command-line artifact extraction |
| `ProcTreeExtract` | `ProcTreeExtract` | Process lineage extraction |
| `HuntQueriesExtract` | `HuntQueriesExtract` | Hunt query extraction |
| `RegistryExtract` | `RegistryExtract` | Registry artifact extraction |
| `ServicesExtract` | `ServicesExtract` | Windows services extraction |
| `ScheduledTasksExtract` | `ScheduledTasksExtract` | Scheduled tasks extraction |
| `NetworkIndicatorExtract` | `NetworkIndicatorExtract` | Network indicators extraction |

`src/prompts/ExtractAgent` remains on disk but is not mapped into the v2 `Prompts` section or loaded by prompt bootstrap. `Agents.ExtractAgent` is model/provider fallback configuration only.

## Platform Detection Prompt

| Seed File | Usage |
|-----------|-------|
| `OSDetectionAgent` | Seeded via `AGENT_PROMPT_FILES["OSDetectionAgent"]`. Platform detection is deterministic (entity/keyword registry), but the low-confidence tail is adjudicated by an LLM: `os_detection_node` resolves the legacy database/display key `agent_prompts["OSDetectionAgent"]` and passes it as the adjudicator's system prompt (`src/workflows/agentic_workflow.py`, `src/services/platform_adjudicator.py`). This compatibility key is not an `ALL_AGENT_NAMES` or v2 `Prompts` key. |

## Sigma Support Prompts

| File | Purpose |
|------|---------|
| `sigma_generate_multi.txt` | Multi-rule Sigma generation |
| `sigma_enrichment.txt` | Sigma rule enrichment |
| `sigma_repair_single.txt` | Seed default for the `SigmaRepair` per-rule repair prompt (see Workflow Agents table above). Repair reuses the `SigmaAgent` model/provider/params — `SigmaRepair` is a prompt-only config key, not a separate model config. |

## Priority Order

1. **Database** (workflow config `agent_prompts`) — takes precedence
2. **Seed file** (`src/prompts/`) — fallback on bootstrap or reset

_Last updated: 2026-08-13_
_Last reviewed: 2026-09-01_
