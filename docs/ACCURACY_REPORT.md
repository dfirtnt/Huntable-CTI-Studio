# Documentation Accuracy Report

**Generated**: 2026-02-12
**Scope**: All docs in `mkdocs.yml` nav verified against current codebase
**Method**: Every doc claim cross-referenced against Python source, config files, and Docker compose

---

## Executive Summary

| Category | Files Reviewed | Files with Issues | Total Issues |
|----------|---------------|-------------------|-------------|
| Getting Started | 5 | 4 | 7 |
| Concepts | 4 | 2 | 3 |
| Architecture | 5 | 3 | 8 |
| Features | 6 | 2 | 8 |
| Guides | 7 | 0 | 0 |
| LLM & Models | 3 | 2 | 6 |
| ML Training | 2 | 0 | 0 |
| Reference | 7 | 2 | 3 |
| Development | 10 | 2 | 3 |
| Prompts | 3 | 0 | 0 |
| Other (contrib/changelog) | 2 | 0 | 0 |
| **TOTAL** | **56** | **17** | **38** |

**Additional structural issues**: 40 orphan files, 10+ broken links, 2 case-duplicate pairs.

---

## CRITICAL — Wrong Facts

These doc claims contradict the actual implementation.

### 1. Scoring Algorithm is Wrong
**File**: `architecture/scoring.md` (lines 63-75)
**Doc claims**: Logarithmic bucket scoring — `Perfect Score = min(35 × log(matches + 1), 75.0)`
**Actual code** (`src/utils/content.py:1240-1246`): Geometric series — `max_points * (1.0 - 0.5^matches)` (50% diminishing returns)
**Impact**: Anyone implementing or debugging scoring will get wrong results.

### 2. Pattern Counts are Wrong (affects 2 files)
**Files**: `features/sigma-rules.md`, `features/content-filtering.md`

| Pattern Category | Doc Claims | Actual Code | Delta |
|-----------------|-----------|-------------|-------|
| Perfect discriminators | 103 (87 strings + 16 regex) | 92 strings, 0 regex | -11, no regex |
| Good discriminators | 77 | 89 | +12 |
| LOLBAS executables | 64 | 239 | +175 |
| Intelligence indicators | 45 | 56 | +11 |

### 3. Non-existent Queue Documented
**Files**: `getting-started/configuration.md` (line 167), `development/workflow-queue.md` (line 32)
**Doc claims**: `priority_checks` queue exists
**Actual** (`docker-compose.yml` line 178): Queues are `default,source_checks,maintenance,reports,connectivity,collection` — no `priority_checks`

### 4. Git Repository URL is Wrong
**File**: `quickstart.md` (line 24)
**Doc claims**: `https://github.com/starlord/CTIScraper.git`
**Actual**: `https://github.com/dfirtnt/Huntable-CTI-Studio.git`

### 5. `first-workflow.md` is Empty
**File**: `getting-started/first-workflow.md`
**Status**: Contains only a header comment ("MERGED FROM: quickstart.md extract steps 3-6") and no actual content.
**Impact**: Getting Started nav promises a page that delivers nothing.

---

## HIGH — Outdated / Misleading

### 6. LM Studio Model Name Outdated (3 files)
**Files**: `getting-started/configuration.md`, `llm/lmstudio.md`
**Doc claims**: Default model is `deepseek-r1-qwen3-8b`
**Actual** (`docker-compose.yml` line 81): `deepseek/deepseek-r1-0528-qwen3-8b` (namespace + version)

### 7. Corrupted Text in LLM Docs
**File**: `llm/model-selection.md` (lines 752, 768)
**Issue**: Date reads "FebruaryDecember 20264" — garbled merge artifact

**File**: `llm/lmstudio.md` (lines 30, 58)
**Issue**: Concatenated model names: `deepseek-r1-qwen3-8bllama-3.1-8b-instruct` and truncated env var description: `LMSTUDIO_MAX_CONTEXT`: Maximum context window sizellama-3.2-1b-instruct`)`

### 8. Line Number References Stale
**File**: `architecture/workflow-data-flow.md`
All code line references are off by ~100 lines:

| Doc Reference | Documented Lines | Actual Lines |
|--------------|-----------------|-------------|
| Supervisor aggregation | 1641-1679 | 1732-1786 |
| Database persistence | 1695-1744 | 1788-1837 |
| SIGMA consumption | 1772-1860 | 1871-1970 |
| DB model (AgenticWorkflowExecutionTable) | models.py:479 | models.py:536 |

### 9. DATABASE_URL Default is Misleading
**File**: `getting-started/configuration.md` (line 71)
**Doc claims**: Default `DATABASE_URL` is `postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper`
**Actual**: `.env.example` doesn't contain this. Docker compose constructs URL dynamically from `POSTGRES_PASSWORD`.

### 10. `training_category` Claimed Deprecated But Actively Used
**File**: `development/database-queries.md` (line 59)
**Doc claims**: "Article-level chosen/rejected/unclassified classification has been deprecated and removed"
**Actual** (`src/database/async_manager.py`): Active queries still filter on `training_category = 'rejected'`, `= 'chosen'`, `IS NULL`

### 11. Context Length Variance Undocumented
**Actual** (`docker-compose.yml`):
- Web service: `LMSTUDIO_CONTEXT_LENGTH_deepseek_...=16384`
- Worker + workflow_worker: `4096`
No doc mentions this difference.

### 12. Worker Queue Split Not Clearly Documented
**File**: `getting-started/installation.md` (line 75)
**Issue**: Doesn't clearly state that `workflows` queue runs on a SEPARATE `workflow_worker` service, not the main worker.

---

## STRUCTURAL — Broken Links

| Source File | Broken Link | Should Be |
|------------|-------------|-----------|
| `concepts/agents.md` | `../features/CMDLINE_ATTENTION_PREPROCESSOR.md` | `../features/cmdline-preprocessor.md` |
| `concepts/huntables.md` | `../internals/scoring.md` | `../architecture/scoring.md` |
| `concepts/huntables.md` | `../ML_HUNT_SCORING.md` | `../ml-training/hunt-scoring.md` |
| `architecture/qa-loops.md` | `../EXTRACTION_PIPELINE_SPEC_FOR_AI.md` | `../archive/EXTRACTION_PIPELINE_SPEC_FOR_AI.md` |
| `features/observable-evaluation.md` | `../howto/extract_observables.md` | `../guides/extract-observables.md` |
| `features/sigma-rules.md` | `[internal-notes://behavioral_novelCosine Similarity]` | Malformed link — remove |
| `guides/backup-and-restore.md` | `./SOURCE_CONFIG_PRECEDENCE.md` | Dead link — file doesn't exist in guides/ |
| `guides/extract-observables.md` | `../features/CMDLINE_ATTENTION_PREPROCESSOR.md` | `../features/cmdline-preprocessor.md` |
| `reference/cli.md` | `../howto/add_feed.md` | `../guides/add-feed.md` |
| `reference/cli.md` | `../howto/generate_sigma.md` | `../guides/generate-sigma.md` |
| `reference/cli.md` | `../internals/scoring.md` | `../architecture/scoring.md` |
| `reference/cli.md` | `../internals/chunking.md` | `../architecture/chunking.md` |
| `reference/cli.md` | `../RAG_SYSTEM.md` | `../features/rag-search.md` |
| `reference/cli.md` | `../deployment/DOCKER_ARCHITECTURE.md` | Dead link — file doesn't exist |

---

## STRUCTURAL — Orphan Files (40 total)

Files present in `/docs/` but NOT in `mkdocs.yml` nav. These are invisible to readers.

### Root-level orphans (15)
```
CHANGELOG.md                          (case-duplicate of changelog.md)
CONTRIBUTING.md                       (case-duplicate of contributing.md)
EXTRACT_AGENT_EVALUATION.md
EXTRACT_AGENT_FINETUNING.md
EXTRACT_AGENT_MODEL_RECOMMENDATIONS.md
HUNTABLE_WINDOWS_CLASSIFIER.md
HUNTABLE_WINDOWS_TRAINING_STRATEGY.md
LMSTUDIO_INTEGRATION.md
LOCAL_LLM_PERFORMANCE.md
ML_HUNT_SCORING.md
ML_VS_HUNT_COMPARISON_GUIDE.md
Model_Selection_Guide_CTI_Workflows.md
OS_DETECTION_CLASSIFIER_TRAINING.md
OpenAI_Chat_Models_Reference.md
Welcome file.md
```

### development/ orphans (18)
```
DEBUGGING_TOOLS_GUIDE.md
DEBUG_EVAL_LMSTUDIO_LOGS.md
EVAL_ARTICLES_STATIC_FILES.md
LIGHTWEIGHT_INTEGRATION_TESTING.md
MANUAL_CHECKLIST_30MIN.md
MANUAL_TEST_CHECKLIST.md
PORT_CONFIGURATION.md
TESTING_STRATEGY.md
TEST_COVERAGE_ANALYSIS.md
TEST_DATA_SAFETY.md
TEST_GROUPS.md
TEST_PLAN.md
TROUBLESHOOT_EVAL_PENDING.md
VALIDATION_REPORT.md
WEB_APP_TESTING.md
WebAppDevtestingGuide.md
boolean-search.md
test_scripts_vs_production_comparison.md
```

### features/ orphans (5)
```
CONTENT_FILTERING.md                  (duplicate of content-filtering.md)
CONTENT_FILTER_ML_SETUP.md
OS_DETECTION.md                       (duplicate of os-detection.md)
SIGMA_DETECTION_RULES.md              (duplicate of sigma-rules.md)
Scrapper_Troubleshooting.md
```

### Other orphans (2)
```
reference/config.md
reference/sigma.md
```

> **Note**: `reference/config.md` and `reference/sigma.md` exist on disk but are NOT in the nav. They may contain useful content that should either be added to nav or merged into existing nav pages.

---

## CLEAN — No Issues Found

These files passed verification:

- `index.md`
- `architecture/overview.md`
- `architecture/chunking.md`
- `concepts/observables.md`
- `features/os-detection.md`
- `features/cmdline-preprocessor.md`
- `features/rag-search.md`
- `features/observable-evaluation.md`
- `guides/add-feed.md`
- `guides/backup-and-restore.md`
- `guides/evaluate-models.md`
- `guides/extract-observables.md`
- `guides/generate-sigma.md`
- `guides/memory-tuning.md`
- `guides/source-config.md`
- `llm/extract-agent-eval.md`
- `ml-training/hunt-scoring.md`
- `ml-training/database-training.md`
- `reference/schemas.md`
- `prompts/eval-bundle.md`
- `prompts/huntquery-eval.md`
- `prompts/proctree-eval.md`
- `contributing.md`
- `changelog.md`

---

## Recommended Fix Priority

1. **P0 — Fix now**: Scoring algorithm (wrong math), empty `first-workflow.md`, wrong git URL
2. **P1 — Fix soon**: Pattern counts (4 wrong numbers × 2 files), corrupted text in LLM docs, non-existent queue
3. **P2 — Fix next**: 14 broken links, stale line numbers, misleading DATABASE_URL
4. **P3 — Cleanup**: Delete 40 orphan files (or archive), remove case-duplicates
