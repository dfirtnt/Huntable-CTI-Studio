# Scripts and How To Use Them

Comprehensive guide to all utility scripts in the Huntable CTI Studio project.

## Table of Contents

- [Setup & Installation](#setup--installation)
- [Testing](#testing)
- [Backup & Restore](#backup--restore)
- [Training & ML](#training--ml)
- [Evaluation](#evaluation)
- [Maintenance](#maintenance)
- [Migration](#migration)
- [Analysis & Reporting](#analysis--reporting)
- [Data Management](#data-management)
- [Workflow & Execution](#workflow--execution)
- [Model Management](#model-management)
- [Prompt Testing](#prompt-testing)

---

## Setup & Installation

### `install.sh`
**Purpose**: Browser extension installation helper  
**Usage**:
```bash
./scripts/install.sh
```
Creates placeholder icons and provides installation instructions for the browser extension.

### `setup_local_models.sh`
**Purpose**: Download and manage local LLM models (MLX, GGUF, LM Studio)  
**Usage**:
```bash
# Download all models
./scripts/setup_local_models.sh --with-mlx --with-llamacpp --all-models

# Download specific models
./scripts/setup_local_models.sh llama-3.2-1b-instruct phi3-mini

# Show help
./scripts/setup_local_models.sh --help
```
**Requirements**: macOS (Apple Silicon for MLX), Python 3, pip3

### `test_setup.sh` / `test_teardown.sh`
**Purpose**: Start/stop test containers  
**Usage**:
```bash
./scripts/test_setup.sh      # Start test environment
./scripts/test_teardown.sh   # Stop test environment
```

---

## Testing

### `run_tests.sh`
**Purpose**: Main test runner with auto-configuration  
**Usage**:
```bash
# Run all tests
./scripts/run_tests.sh

# Run specific test file
./scripts/run_tests.sh tests/test_content_filter.py

# Run with pytest options
./scripts/run_tests.sh -v -k "test_filter"
```
**Features**: Auto-sets `APP_ENV=test` and `TEST_DATABASE_URL`

### `run_tests_by_group.py`
**Purpose**: Run tests by group (smoke, unit, api, integration, etc.)  
**Usage**:
```bash
python3 scripts/run_tests_by_group.py --group smoke
python3 scripts/run_tests_by_group.py --group unit
python3 scripts/run_tests_by_group.py --group api
```

### `run_prompt_test.sh`
**Purpose**: Test prompts against LMStudio models  
**Usage**:
```bash
# List available agents/models
./scripts/run_prompt_test.sh --list-agents
./scripts/run_prompt_test.sh --list-models

# Test single model on article
./scripts/run_prompt_test.sh --model "qwen/qwen3-8b" --article 68

# Test multiple models
./scripts/run_prompt_test.sh --model "qwen/*" --all-eval

# Test specific agent
./scripts/run_prompt_test.sh --agent RankAgent --model "qwen/qwen3-8b" --article 68
```
See `README_prompt_testing.md` for detailed documentation.

### Testing Directory Scripts
**Location**: `scripts/testing/`

- `analyze_keywords.py` - Keyword analysis
- `check_missing_keywords.py` - Missing keyword detection
- `check_source_urls.py` - Source URL validation
- `llm_local_runner.py` - Local LLM testing
- `validate_threat_scoring.py` - Threat scoring validation

**Usage**:
```bash
python3 scripts/testing/analyze_keywords.py
python3 scripts/testing/check_source_urls.py
```

---

## Backup & Restore

### `backup_system.py`
**Purpose**: Comprehensive system backup (database, models, configs, volumes)  
**Usage**:
```bash
python3 scripts/backup_system.py

# With options
python3 scripts/backup_system.py --output-dir /path/to/backups --components db,models,configs
```
**Features**: Parallel execution, SHA256 checksums, component validation

### `backup_restore.sh`
**Purpose**: Unified backup/restore helper script  
**Usage**:
```bash
# Backup
./scripts/backup_restore.sh backup

# Restore
./scripts/backup_restore.sh restore /path/to/backup.tar.gz

# Verify backup
./scripts/backup_restore.sh verify /path/to/backup.tar.gz
```

### `restore_system.py`
**Purpose**: Comprehensive system restore  
**Usage**:
```bash
python3 scripts/restore_system.py /path/to/backup.tar.gz

# Dry run
python3 scripts/restore_system.py /path/to/backup.tar.gz --dry-run
```

### `restore_database.py` / `restore_database_v2.py` / `restore_database_v3.py`
**Purpose**: Database-only restore (various versions)  
**Usage**:
```bash
python3 scripts/restore_database_v3.py /path/to/dump.sql.gz
```

### `verify_backup.py`
**Purpose**: Verify backup integrity  
**Usage**:
```bash
python3 scripts/verify_backup.py /path/to/backup.tar.gz
```

### `setup_automated_backups.sh`
**Purpose**: Configure automated backup cron jobs  
**Usage**:
```bash
./scripts/setup_automated_backups.sh
```

---

## Training & ML

### `train_os_bert_workflow.sh`
**Purpose**: Complete OS-BERT fine-tuning workflow  
**Usage**:
```bash
# With defaults
./scripts/train_os_bert_workflow.sh

# With custom parameters
MIN_HUNT_SCORE=80.0 LIMIT=200 EPOCHS=3 ./scripts/train_os_bert_workflow.sh
```
**Steps**: Data preparation → Quality check → Fine-tuning → Model save

### `train_huntable_windows_workflow.sh`
**Purpose**: Huntable Windows classifier training workflow  
**Usage**:
```bash
./scripts/train_huntable_windows_workflow.sh
```

### `finetune_os_bert.py`
**Purpose**: Fine-tune OS-BERT model  
**Usage**:
```bash
python3 scripts/finetune_os_bert.py \
    --data data/os_detection_training_data.json \
    --base-model ibm-research/CTI-BERT \
    --output-dir models/os-bert \
    --epochs 3 \
    --batch-size 16 \
    --learning-rate 2e-5 \
    --use-gpu
```

### `prepare_os_detection_training_data.py`
**Purpose**: Prepare training data for OS detection  
**Usage**:
```bash
python3 scripts/prepare_os_detection_training_data.py \
    --min-hunt-score 80.0 \
    --limit 200 \
    --output data/os_detection_training_data.json
```

### `prepare_huntable_windows_training_data.py`
**Purpose**: Prepare training data for huntable Windows classifier  
**Usage**:
```bash
python3 scripts/prepare_huntable_windows_training_data.py \
    --output data/huntable_windows_training_data.json
```

### `publish_os_bert_to_hf.py`
**Purpose**: Publish fine-tuned model to HuggingFace  
**Usage**:
```bash
python3 scripts/publish_os_bert_to_hf.py \
    --model-dir models/os-bert \
    --repo-id your-username/os-bert
```

### `train_huntable_windows_classifier.py`
**Purpose**: Train huntable Windows classifier  
**Usage**:
```bash
python3 scripts/train_huntable_windows_classifier.py \
    --data data/huntable_windows_training_data.json \
    --output-dir models/huntable-windows
```

---

## Evaluation

### `eval_extract_agent.py`
**Purpose**: Evaluate Extract Agent performance  
**Usage**:
```bash
python3 scripts/eval_extract_agent.py \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_baseline.json \
    --model gpt-4o
```

### `eval_os_detection.py`
**Purpose**: Evaluate OS detection model  
**Usage**:
```bash
python3 scripts/eval_os_detection.py \
    --model-dir models/os-bert \
    --test-data data/os_detection_test_data.json
```

### `eval_os_detection_multiple_models.py`
**Purpose**: Compare multiple OS detection models  
**Usage**:
```bash
python3 scripts/eval_os_detection_multiple_models.py \
    --models models/os-bert,models/os-bert-v2 \
    --test-data data/os_detection_test_data.json
```

### `eval_sigma_agent.py`
**Purpose**: Evaluate Sigma generation agent  
**Usage**:
```bash
python3 scripts/eval_sigma_agent.py \
    --test-articles 68,69,70 \
    --output outputs/evaluations/sigma_agent.json
```

### `eval_rank_agent.py`
**Purpose**: Evaluate Rank Agent performance  
**Usage**:
```bash
python3 scripts/eval_rank_agent.py \
    --test-set eval \
    --output outputs/evaluations/rank_agent.json
```

### `eval_all_agents.py`
**Purpose**: Run evaluation for all agents  
**Usage**:
```bash
python3 scripts/eval_all_agents.py \
    --output-dir outputs/evaluations/
```

### `evaluate_huntable_windows_baseline.py`
**Purpose**: Evaluate baseline huntable Windows classifier  
**Usage**:
```bash
python3 scripts/evaluate_huntable_windows_baseline.py
```

### `evaluate_huntable_windows_model.py`
**Purpose**: Evaluate trained huntable Windows model  
**Usage**:
```bash
python3 scripts/evaluate_huntable_windows_model.py \
    --model-dir models/huntable-windows
```

### `run_cmdline_count_eval.py`
**Purpose**: Evaluate command-line extraction counts  
**Usage**:
```bash
python3 scripts/run_cmdline_count_eval.py \
    --article-id 68
```

### `generate_cmdextract_eval_csv.py`
**Purpose**: Generate CSV for command-line extraction evaluation  
**Usage**:
```bash
python3 scripts/generate_cmdextract_eval_csv.py \
    --output outputs/evaluations/cmdline_eval.csv
```

---

## Maintenance

### `maintenance/fix_corrupted_articles.py`
**Purpose**: Fix corrupted article records  
**Usage**:
```bash
python3 scripts/maintenance/fix_corrupted_articles.py
```

### `maintenance/fix_corrupted_articles_batch.py`
**Purpose**: Batch fix corrupted articles  
**Usage**:
```bash
python3 scripts/maintenance/fix_corrupted_articles_batch.py --limit 100
```

### `maintenance/fix_duplicate_articles.py`
**Purpose**: Fix duplicate article records  
**Usage**:
```bash
python3 scripts/maintenance/fix_duplicate_articles.py
```

### `maintenance/find_duplicate_articles.py`
**Purpose**: Find duplicate articles  
**Usage**:
```bash
python3 scripts/maintenance/find_duplicate_articles.py
```

### `maintenance/fix_incomplete_articles.py`
**Purpose**: Fix incomplete article records  
**Usage**:
```bash
python3 scripts/maintenance/fix_incomplete_articles.py
```

### `maintenance/fix_url_deduplication.py`
**Purpose**: Fix URL deduplication issues  
**Usage**:
```bash
python3 scripts/maintenance/fix_url_deduplication.py
```

### `maintenance/fix_ioc_field_names.py`
**Purpose**: Fix IOC field name inconsistencies  
**Usage**:
```bash
python3 scripts/maintenance/fix_ioc_field_names.py
```

### `maintenance/update_annotation_usage.py`
**Purpose**: Update annotation usage statistics  
**Usage**:
```bash
python3 scripts/maintenance/update_annotation_usage.py
```

### `maintenance/verify_training_usage.py`
**Purpose**: Verify training data usage  
**Usage**:
```bash
python3 scripts/maintenance/verify_training_usage.py
```

### `maintenance/check_training_datasets.py`
**Purpose**: Check training dataset integrity  
**Usage**:
```bash
python3 scripts/maintenance/check_training_datasets.py
```

### `maintenance/rollback_training.py`
**Purpose**: Rollback training changes  
**Usage**:
```bash
python3 scripts/maintenance/rollback_training.py --version 1.2.3
```

### `maintenance/reset_gold_eval_training_flag.py`
**Purpose**: Reset gold evaluation training flags  
**Usage**:
```bash
python3 scripts/maintenance/reset_gold_eval_training_flag.py
```

### `maintenance/update_provider_model_catalogs.py`
**Purpose**: Fetch latest OpenAI, Anthropic, and Gemini models from provider APIs and update the curated list used by the workflow UI. Keeps `config/provider_model_catalog.json` in sync so new models appear in dropdowns. The catalog is filtered: **OpenAI** — chat-only, latest only (no `-YYYY-MM-DD` dated variants); **Anthropic** — one main/latest per family (e.g. one Sonnet 4.5, one Haiku 4.5).  
**Usage**:
```bash
# Preview only (no write)
python3 scripts/maintenance/update_provider_model_catalogs.py

# Write updated catalog to config/provider_model_catalog.json
python3 scripts/maintenance/update_provider_model_catalogs.py --write
```
**Requirements**: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` (and optionally `GEMINI_API_KEY`) in environment. Missing keys cause that provider to retain its existing catalog list.

### When the catalog is refreshed
- **At setup**: `./setup.sh` runs the refresh after services start so users see the current model list immediately.
- **At start**: `./start.sh` runs the refresh so each start has an up-to-date catalog (no 24h wait).
- **Daily**: The catalog is also updated **daily at 4:00 AM** by the Celery beat schedule (task `update_provider_model_catalogs`, queue `maintenance`). Ensure the worker that consumes the `maintenance` queue has `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` set so providers can be refreshed.

For a one-off or host-based run: `./scripts/maintenance/daily_update_provider_models.sh` (from repo root).

### `maintenance/sync_sources_fix.py`
**Purpose**: Fix source synchronization issues  
**Usage**:
```bash
python3 scripts/maintenance/sync_sources_fix.py
```

### `maintenance/convert_to_workshop.py`
**Purpose**: Convert data to workshop format  
**Usage**:
```bash
python3 scripts/maintenance/convert_to_workshop.py
```

---

## Migration

### `migrate_add_auto_trigger_threshold.py`
**Purpose**: Add auto-trigger threshold to workflow config  
**Usage**:
```bash
python3 scripts/migrate_add_auto_trigger_threshold.py
```

### `migrate_eval_tables.py`
**Purpose**: Migrate evaluation tables  
**Usage**:
```bash
python3 scripts/migrate_eval_tables.py
```

### `migrate_sigma_to_canonical.py`
**Purpose**: Migrate Sigma rules to canonical format  
**Usage**:
```bash
python3 scripts/migrate_sigma_to_canonical.py
```

### `migrate_sigma_canonical_fields.py`
**Purpose**: Migrate Sigma canonical fields  
**Usage**:
```bash
python3 scripts/migrate_sigma_canonical_fields.py
```

### `migrate_subagent_evaluation_table.py`
**Purpose**: Migrate subagent evaluation table  
**Usage**:
```bash
python3 scripts/migrate_subagent_evaluation_table.py
```

### `migrate_feedback_csv_to_db.py`
**Purpose**: Migrate feedback CSV to database  
**Usage**:
```bash
python3 scripts/migrate_feedback_csv_to_db.py --csv-file feedback.csv
```

### `migrate_enrichment_presets.py`
**Purpose**: Migrate enrichment presets  
**Usage**:
```bash
python3 scripts/migrate_enrichment_presets.py
```

### `migrate_enrichment_prompt_versions.py`
**Purpose**: Migrate enrichment prompt versions  
**Usage**:
```bash
python3 scripts/migrate_enrichment_prompt_versions.py
```

### `migrate_sigma_embeddings.py`
**Purpose**: Migrate Sigma rule embeddings  
**Usage**:
```bash
python3 scripts/migrate_sigma_embeddings.py
```

### `migrate_app_settings.py`
**Purpose**: Migrate application settings  
**Usage**:
```bash
python3 scripts/migrate_app_settings.py
```

---

## Analysis & Reporting

### `analyze_high_scores.py`
**Purpose**: Analyze articles with high threat scores  
**Usage**:
```bash
python3 scripts/analyze_high_scores.py --min-score 8.0
```

### `assess_top_articles_sigma_coverage.py`
**Purpose**: Assess Sigma coverage for top articles  
**Usage**:
```bash
python3 scripts/assess_top_articles_sigma_coverage.py --limit 100
```

### `assess_kql_indicators.py`
**Purpose**: Assess KQL indicators  
**Usage**:
```bash
python3 scripts/assess_kql_indicators.py
```

### `assess_falcon_indicators.py`
**Purpose**: Assess Falcon indicators  
**Usage**:
```bash
python3 scripts/assess_falcon_indicators.py
```

### `assess_edr_indicators_comprehensive.py`
**Purpose**: Comprehensive EDR indicator assessment  
**Usage**:
```bash
python3 scripts/assess_edr_indicators_comprehensive.py
```

### `generate_extract_html_report.py`
**Purpose**: Generate HTML report for extractions  
**Usage**:
```bash
python3 scripts/generate_extract_html_report.py \
    --output reports/extraction_report.html
```

### `generate_commandline_notebook.py`
**Purpose**: Generate Jupyter notebook for command-line analysis  
**Usage**:
```bash
python3 scripts/generate_commandline_notebook.py \
    --output notebooks/cmdline_analysis.ipynb
```

### `extraction_metrics_calculator.py`
**Purpose**: Calculate extraction metrics  
**Usage**:
```bash
python3 scripts/extraction_metrics_calculator.py
```

### `compare_sigma_rules.py`
**Purpose**: Compare Sigma rules  
**Usage**:
```bash
python3 scripts/compare_sigma_rules.py --rule1-id 1 --rule2-id 2
```

### `compare_evaluations.py`
**Purpose**: Compare evaluation results  
**Usage**:
```bash
python3 scripts/compare_evaluations.py \
    --eval1 outputs/evaluations/eval1.json \
    --eval2 outputs/evaluations/eval2.json
```

---

## Data Management

### `regenerate_all_scores.py`
**Purpose**: Regenerate threat hunting scores for all articles  
**Usage**:
```bash
python3 scripts/regenerate_all_scores.py
```
**Note**: Use `./run_cli.sh rescore --force` for CLI-based rescoring

### `ensure_article_embeddings.py`
**Purpose**: Ensure all articles have embeddings  
**Usage**:
```bash
python3 scripts/ensure_article_embeddings.py
```

### `update_article_expected_count.py`
**Purpose**: Update expected extraction counts for articles  
**Usage**:
```bash
python3 scripts/update_article_expected_count.py --article-id 68
```

### `update_annotation_counts.py`
**Purpose**: Update annotation counts  
**Usage**:
```bash
python3 scripts/update_annotation_counts.py
```

### `update_source_counts.py`
**Purpose**: Update source article counts  
**Usage**:
```bash
python3 scripts/update_source_counts.py
```

### `setup_deduplication.py`
**Purpose**: Setup deduplication system  
**Usage**:
```bash
python3 scripts/setup_deduplication.py
```

### `backfill_simhash.py`
**Purpose**: Backfill SimHash values for articles  
**Usage**:
```bash
python3 scripts/backfill_simhash.py
```

### `backfill_simhash_robust.py`
**Purpose**: Robust SimHash backfill with error handling  
**Usage**:
```bash
python3 scripts/backfill_simhash_robust.py
```

### `backfill_simhash_direct.py`
**Purpose**: Direct SimHash backfill  
**Usage**:
```bash
python3 scripts/backfill_simhash_direct.py
```

### `backfill_annotation_context.py`
**Purpose**: Backfill annotation context  
**Usage**:
```bash
python3 scripts/backfill_annotation_context.py
```

### `backfill_eval_records.py`
**Purpose**: Backfill evaluation records  
**Usage**:
```bash
python3 scripts/backfill_eval_records.py
```

---

## Workflow & Execution

### `trigger_workflow.py`
**Purpose**: Manually trigger agentic workflow  
**Usage**:
```bash
python3 scripts/trigger_workflow.py --article-id 68
```

### `trigger_stuck_executions.py`
**Purpose**: Trigger stuck workflow executions  
**Usage**:
```bash
python3 scripts/trigger_stuck_executions.py
```

### `fix_workflow_execution_status.py`
**Purpose**: Fix workflow execution status issues  
**Usage**:
```bash
python3 scripts/fix_workflow_execution_status.py
```

### `check_execution_details.py`
**Purpose**: Check workflow execution details  
**Usage**:
```bash
python3 scripts/check_execution_details.py --execution-id 123
```

### `trace_hunt_queries_execution.py`
**Purpose**: Trace hunt queries execution  
**Usage**:
```bash
python3 scripts/trace_hunt_queries_execution.py --article-id 68
```

---

## Model Management

### `list_lmstudio_models.py`
**Purpose**: List available LMStudio models  
**Usage**:
```bash
python3 scripts/list_lmstudio_models.py
```

### `check_lmstudio_model_loaded.py`
**Purpose**: Check if LMStudio model is loaded  
**Usage**:
```bash
python3 scripts/check_lmstudio_model_loaded.py --model-name "qwen/qwen3-8b"
```

### `check_lmstudio_models_availability.py`
**Purpose**: Check LMStudio models availability  
**Usage**:
```bash
python3 scripts/check_lmstudio_models_availability.py
```

### `load_lmstudio_model.sh`
**Purpose**: Load LMStudio model  
**Usage**:
```bash
./scripts/load_lmstudio_model.sh "qwen/qwen3-8b"
```

### `set_lmstudio_context.sh`
**Purpose**: Set LMStudio context  
**Usage**:
```bash
./scripts/set_lmstudio_context.sh
```

### `benchmark_llm_providers.py`
**Purpose**: Benchmark LLM providers  
**Usage**:
```bash
python3 scripts/benchmark_llm_providers.py \
    --providers openai,anthropic,lmstudio \
    --test-articles 68,69,70
```

---

## Prompt Testing

### `run_prompt_test.sh`
**Purpose**: Test prompts against models (see Testing section)  
**Documentation**: See `README_prompt_testing.md`

### `test_prompt_with_models.py`
**Purpose**: Core prompt testing script  
**Usage**:
```bash
python3 scripts/test_prompt_with_models.py \
    --agent CmdlineExtract \
    --model "qwen/qwen3-8b" \
    --article-id 68
```

### `get_prompts_by_versions.py`
**Purpose**: Get prompts by version  
**Usage**:
```bash
python3 scripts/get_prompts_by_versions.py --agent CmdlineExtract
```

### `extract_prompt_1643.py`
**Purpose**: Extract prompt from version 1643  
**Usage**:
```bash
python3 scripts/extract_prompt_1643.py
```

### `get_hunt_prompts_1643_1729.py`
**Purpose**: Get hunt prompts from versions 1643-1729  
**Usage**:
```bash
python3 scripts/get_hunt_prompts_1643_1729.py
```

### `compare_prompt_928.py`
**Purpose**: Compare prompt version 928  
**Usage**:
```bash
python3 scripts/compare_prompt_928.py
```

### `compare_configs_1643_1729.py`
**Purpose**: Compare configs between versions  
**Usage**:
```bash
python3 scripts/compare_configs_1643_1729.py
```

### `bootstrap_prompts.py`
**Purpose**: Bootstrap prompts from files  
**Usage**:
```bash
python3 scripts/bootstrap_prompts.py --prompt-dir src/prompts/
```

---

## Utility Scripts

### `config_backup.py`
**Purpose**: Backup configuration files  
**Usage**:
```bash
python3 scripts/config_backup.py --output config_backup.tar.gz
```

### `validate_ioc_system.py`
**Purpose**: Validate IOC extraction system  
**Usage**:
```bash
python3 scripts/validate_ioc_system.py
```

### `check_sigma_failures.py`
**Purpose**: Check Sigma generation failures  
**Usage**:
```bash
python3 scripts/check_sigma_failures.py
```

### `show_sigma_errors.py`
**Purpose**: Show Sigma validation errors  
**Usage**:
```bash
python3 scripts/show_sigma_errors.py
```

### `export_annotations_for_eval.py`
**Purpose**: Export annotations for evaluation  
**Usage**:
```bash
python3 scripts/export_annotations_for_eval.py \
    --output outputs/evaluations/annotations.json
```

### `bulk_export_pdfs.py`
**Purpose**: Bulk export articles as PDFs  
**Usage**:
```bash
python3 scripts/bulk_export_pdfs.py --output-dir exports/pdfs/
```

### `create_notebook.py`
**Purpose**: Create Jupyter notebook  
**Usage**:
```bash
python3 scripts/create_notebook.py --output notebook.ipynb
```

### `create_commandline_testing_notebook.py`
**Purpose**: Create command-line testing notebook  
**Usage**:
```bash
python3 scripts/create_commandline_testing_notebook.py \
    --output notebooks/cmdline_testing.ipynb
```

### `prune_backups.py`
**Purpose**: Prune old backups  
**Usage**:
```bash
python3 scripts/prune_backups.py --keep-days 30
```

---

## Running Scripts

### Docker Environment
Most scripts should be run inside the Docker container:
```bash
docker exec -it cti_workflow_worker python3 /app/scripts/script_name.py
```

### Local Environment
For local execution, ensure:
1. Virtual environment is activated
2. Dependencies are installed (`pip3 install -r requirements.txt`)
3. Environment variables are set (`.env` file)
4. Database is accessible

### Common Patterns

**Python Scripts**:
```bash
# From project root
python3 scripts/script_name.py [args]

# With Docker
docker exec -it cti_workflow_worker python3 /app/scripts/script_name.py [args]
```

**Shell Scripts**:
```bash
# Make executable if needed
chmod +x scripts/script_name.sh

# Run from project root
./scripts/script_name.sh [args]
```

---

## Getting Help

Most scripts support `--help` flag:
```bash
python3 scripts/script_name.py --help
./scripts/script_name.sh --help
```

For detailed documentation on specific features:
- Prompt Testing: `scripts/README_prompt_testing.md`
- Test Groups: `docs/TEST_GROUPS.md`
- Testing Guide: `tests/TESTING.md`
