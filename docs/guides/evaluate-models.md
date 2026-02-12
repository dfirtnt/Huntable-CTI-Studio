# Evaluate Extraction Models

Use the built-in evaluation scripts to measure Extract Agent quality before and after fine-tuning.

## Prerequisites
- Stack running (PostgreSQL available) so article lookups and metadata writes succeed
- Test dataset present: `outputs/training_data/test_finetuning_data.json` (ships with high-scoring articles)

## Metrics captured
- JSON validity and field completeness (`behavioral_observables`, `observable_list`, `discrete_huntables_count`, `content`, `url`)
- Observable counts and count accuracy vs. expectations
- Error rate per article and per field
- Optional processing time

## Run a baseline evaluation
```bash
docker-compose exec -T web python scripts/eval_extract_agent.py \
  --test-data outputs/training_data/test_finetuning_data.json \
  --output outputs/evaluations/extract_agent_baseline.json \
  --model baseline
```

## Evaluate a fine-tuned model
```bash
docker-compose exec -T web python scripts/eval_extract_agent.py \
  --test-data outputs/training_data/test_finetuning_data.json \
  --output outputs/evaluations/extract_agent_finetuned.json \
  --model finetuned-mistral-7b
```

## Compare runs
```bash
python3 scripts/compare_evaluations.py \
  --baseline outputs/evaluations/extract_agent_baseline.json \
  --finetuned outputs/evaluations/extract_agent_finetuned.json
```
The comparison highlights JSON validity, field completeness, average huntable counts, and count accuracy deltas between runs.

## Troubleshooting
- Low JSON validity: verify model availability and prompt loading.
- Missing fields: ensure the Extract Agent prompt and schema are unchanged; rerun with debug logging enabled.
- Count mismatches: review `discrete_huntables_count` vs. the `observable_list` in the output JSON to see whether a sub-agent under-reported.
