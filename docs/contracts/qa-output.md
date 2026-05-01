# QA Output Contract

Canonical schema for all QA evaluation results produced by `QAEvaluator`.

## Canonical Output Key: `verdict`

All QA results use `verdict` as the primary decision key.  The legacy `status`
key that appeared in older eval bundles is normalized to `verdict` at the
evaluator boundary.  New code must read `verdict`; `status` is kept in
`_qa_result` storage only for backward compatibility with existing eval bundles.

## Verdict Values

| Value | Meaning |
|---|---|
| `pass` | Output meets all QA criteria; no revision needed. |
| `needs_revision` | Output has issues; RankAgent will retry, extractors record the feedback. |
| `critical_failure` | Output violates a hard constraint; surfaces as an error in the execution log. |

Mapping from legacy `status` values:

| Old `status` | Normalized `verdict` |
|---|---|
| `pass` | `pass` |
| `needs_revision` | `needs_revision` |
| `fail` | `needs_revision` |
| (parse failure) | `needs_revision` (fail-closed) |

## Schema

```json
{
  "verdict": "pass | needs_revision | critical_failure",
  "summary": "Human-readable explanation of the verdict",
  "issues": [
    {
      "type": "compliance | factuality | formatting | completeness",
      "description": "Short description of the issue",
      "severity": "low | medium | high",
      "location": "optional -- section or field name"
    }
  ]
}
```

Extractor QA results additionally include a `corrections` key (extractor-specific):

```json
{
  "corrections": {
    "removed": [{"command": "...", "reason": "..."}],
    "added":   [{"command": "...", "found_in": "..."}]
  }
}
```

## Stored `_qa_result` Shape

The `_qa_result` key written into `execution.error_log["qa_results"]` includes
both `verdict` and a backward-compat `status` field:

```json
{
  "verdict": "pass | needs_revision | critical_failure",
  "status": "(same as verdict for new results; legacy bundles may differ)",
  "summary": "...",
  "feedback": "...",
  "issues": [...],
  "corrections_applied": {"removed": [...]},
  "pre_filter_count": 0
}
```

## Owner

`QAEvaluator` in `src/services/qa_evaluator.py` is the single implementation
that owns the LLM call, the 6-strategy response parser, fail-closed default,
and schema normalization.  All call sites (`qa_agent_service.py`,
`run_extraction_agent` in `llm_service.py`) delegate to it.
