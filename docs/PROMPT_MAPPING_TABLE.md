# Prompt Mapping: File System ↔ Database

## Agent Prompts (Mapped)

| File System | Database Agent | Mapping Type | Notes |
|------------|----------------|--------------|-------|
| `ExtractAgent` + `ExtractAgentInstructions.txt` | `ExtractAgent` | **2 files → 1 DB entry** | Combined: `prompt` (from ExtractAgent) + `instructions` (from ExtractAgentInstructions.txt) |
| `lmstudio_sigma_ranking.txt` | `RankAgent` | **1 file → 1 DB entry** | Primary ranking prompt |
| `sigma_generation.txt` | `SigmaAgent` | **1 file → 1 DB entry** | SIGMA rule generation |
| `QAAgent` | `QAAgent` | **1 file → 1 DB entry** | Quality assurance agent |
| `OSDetectionAgent` | `OSDetectionAgent` | **1 file → 1 DB entry** | Optional in DB; file used as fallback in scoring scripts |

## Agent Prompts (File System Only)

| File System | Database Agent | Status | Usage |
|------------|----------------|--------|-------|
| `ObservablesCountAgent` | ❌ None | **Not in workflow config** | Used in evaluation scripts (`eval_observables_count_multiple_models.py`) |
| `ExtractObservables` | ❌ None | **Not mapped** | Unknown usage |

## Utility/Support Prompts (Not Agents)

| File System | Type | Usage |
|------------|------|-------|
| `article_summary.txt` | Utility | General article summarization |
| `database_chat.txt` | Utility | Database chat functionality |
| `metadata_summary.txt` | Utility | Metadata summarization |
| `sigma_system.txt` | Support | SIGMA system context |
| `sigma_guidance.txt` | Support | SIGMA guidance/instructions |
| `sigma_feedback.txt` | Support | SIGMA feedback handling |

## Alternate Versions (Not Mapped)

| File System | Purpose | Notes |
|------------|---------|-------|
| `gpt4o_sigma_ranking.txt` | Alternate | GPT-4o specific ranking prompt |
| `huntability_ranking.txt` | Alternate | Alternative ranking prompt |
| `huntability_ranking_alt.txt` | Alternate | Alternative ranking prompt variant |
| `llm_sigma_ranking_simple.txt` | Alternate | Simplified LLM ranking prompt |
| `sigma_generation_simple.txt` | Alternate | Simplified SIGMA generation |
| `SIGMA_Huntability_Ranking_v2C-R.md` | Documentation | Markdown documentation |

## Database-Only Agents

| Database Agent | File System | Status | Notes |
|----------------|-------------|--------|-------|
| Custom agents | ❌ None | **DB-only** | Agents created directly in database via UI/API without file system counterpart |

## Mapping Rules

### Priority Order
1. **Database** (if exists) → Takes precedence
2. **File System** → Fallback default

### Special Cases
- **ExtractAgent**: Only agent that combines 2 files into 1 database entry
- **OSDetectionAgent**: Used in scoring scripts but not explicitly mapped in `workflow_config.py`
- **ObservablesCountAgent**: File exists but not part of workflow configuration

### Access Patterns
- **Workflow agents** (ExtractAgent, RankAgent, SigmaAgent, QAAgent): Loaded via `workflow_config.py` → Database first, file fallback
- **Scoring scripts**: Direct file access with optional database lookup (OSDetectionAgent, ExtractAgent)
- **Evaluation scripts**: Direct file access (ObservablesCountAgent)

## Summary Statistics

- **Total file system prompts**: 20 files
- **Mapped to database**: 5 agents (4 explicit + 1 implicit)
- **File system only**: 2 agent files
- **Utility/support**: 6 files
- **Alternate versions**: 6 files
- **Database-only agents**: Variable (user-created)

