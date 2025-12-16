# Observable Extraction Evaluation Design

## Design Constraints & Implementation

### 1. Unit of Evaluation: Per Article

**Constraint**: Metrics are computed per article, comparing the set of predicted spans to the set of annotated spans within that article.

**Implementation**:
- `_compute_eval_metrics()` and `_compute_gold_metrics()` process articles individually
- Each article's predicted spans are compared to its annotated spans
- Gold metrics like Zero-FP Pass Rate are computed at the article level (not per span)
- Article-level results are stored in `article_results` for inspection

**Key Metrics**:
- **Eval**: Precision, Recall, F1 computed across all articles
- **Gold**: Zero-FP Pass Rate = (articles with zero false positives) / (total articles)

### 2. Negative-Space Handling

**Constraint**: Explicitly define how predictions are scored when:
- An article has zero gold observables
- Predictions exist with no matching gold span
- Hallucination Rate must include predictions on gold-empty articles

**Implementation**:
- Articles with zero gold annotations are explicitly handled in `_compute_gold_metrics()`
- All predictions on gold-empty articles count as hallucinations
- `articles_with_zero_gold` tracks how many such articles exist
- Hallucination rate includes these predictions: `total_hallucinations / total_gold_spans`
- Articles with zero gold are tracked in failure taxonomy as `hallucination_on_empty`

**Scoring Rules**:
- **Gold-empty article with predictions**: All predictions = hallucinations
- **Article with gold but unmatched predictions**: Unmatched predictions = hallucinations
- **Article with zero gold and zero predictions**: Passes zero-FP check

### 3. Span Normalization Rules

**Constraint**: 
- Eval datasets: relaxed normalization (whitespace, quotes)
- Gold datasets: strict normalization (trim whitespace, normalize quotes, NO argument reordering, NO semantic canonicalization)

**Implementation**:
- `normalize_span(text, mode)` supports two modes:
  - `"relaxed"`: Collapse whitespace, normalize quotes (for eval)
  - `"strict"`: Only trim whitespace, normalize quotes (for gold)
- Gold evaluation uses `mode="strict"` for all comparisons
- Eval evaluation uses `mode="relaxed"` for overlap calculations
- `is_exact_match()` defaults to `mode="strict"` for gold correctness

**Normalization Rules**:
```python
# Relaxed (eval):
- Collapse multiple whitespace to single space
- Normalize quote types
- Preserve argument order

# Strict (gold):
- Only trim leading/trailing whitespace
- Normalize quote types
- NO argument reordering
- NO semantic canonicalization
```

### 4. Failure Taxonomy Capture

**Constraint**: Persist error categories even if not surfaced as metrics:
- merged commands
- truncated spans
- argument hallucination
- context bleed

**Implementation**:
- `ObservableEvaluationFailureTable` stores failure records per article
- Failure types tracked:
  - `merged_commands`: Single prediction spans multiple gold commands
  - `truncated_span`: Prediction significantly shorter than gold
  - `argument_hallucination`: Prediction has extra arguments not in gold
  - `hallucination_on_empty`: Predictions on articles with zero gold
- Failure taxonomy is stored via `_store_failure_taxonomy()`
- API endpoint: `GET /api/observables/evaluation/failures` for inspection
- Failure records include: article_id, failure_count, zero_fp_pass status

**Inspection**:
- Query failures by model version, failure type, article
- View which articles had which failure types
- Track failure counts per article

### 5. Dashboard Worst-Case Indicators

**Constraint**: Dashboard must include worst-case gold indicators, not just averages:
- Max merged commands in a single article
- Count of articles failing Zero-FP Pass
- Links to failing gold examples

**Implementation**:
- Metrics persisted:
  - `max_merged_commands_per_article`: Worst-case single article
  - `articles_failing_zero_fp`: Count of articles that failed
  - `articles_failing_zero_fp_ids`: List of article IDs (limited to 20 for response size)
- Dashboard displays:
  - Worst-case indicators in red warning box
  - "View Failing Articles" button
  - Links to individual articles via `/articles/{article_id}`
- Failure taxonomy API provides full list of failing articles by failure type

**Dashboard Features**:
- Worst-case section shows:
  - Max merged commands per article
  - Articles failing zero-FP count
  - Articles with zero gold (hallucination test)
- Clickable links to failing articles
- Grouped by failure type for inspection

## Database Schema

### `observable_model_metrics`
Stores computed metrics per model version:
- `model_name`, `model_version`, `observable_type`
- `dataset_usage` (eval or gold)
- `metric_name`, `metric_value`, `sample_count`
- `computed_at` (immutable once written)

### `observable_evaluation_failures`
Stores failure taxonomy for inspection:
- `model_name`, `model_version`, `observable_type`, `article_id`
- `failure_type` (merged_commands, truncated_span, etc.)
- `failure_count`, `failure_details` (JSON)
- `zero_fp_pass`, `total_predictions`, `total_gold_spans`

## API Endpoints

- `POST /api/observables/evaluation/run` - Run evaluation
- `GET /api/observables/evaluation/metrics` - Get metrics
- `GET /api/observables/evaluation/metrics/aggregated` - Get aggregated by version
- `GET /api/observables/evaluation/failures` - Get failure taxonomy

## Design Principles

1. **Eval vs Gold Separation**: Eval metrics track learning progress; gold metrics track production correctness
2. **Article-Level Evaluation**: All metrics computed per article, comparing sets of spans
3. **Strict Gold Correctness**: Gold uses strict normalization - no fuzzy matching
4. **Negative Space Handling**: Articles with zero gold are explicitly evaluated for hallucinations
5. **Failure Inspection**: Failure taxonomy stored for detailed analysis, not just aggregate metrics
6. **Worst-Case Visibility**: Dashboard shows worst-case indicators, not just averages


