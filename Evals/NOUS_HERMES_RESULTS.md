# Nous-Hermes-2-Mistral-7B-DPO Results

## Summary

**Completion Status:** 4 out of 6 articles completed (67%)

**Issue:** Model failed to score articles 1860 and 1866, returning markdown "###" instead of integer scores.

---

## Results

| Article | Runs | Scores | Median | Mean | Variance | Status |
|---------|------|--------|--------|------|----------|--------|
| 1974 | 5/5 | [8, 8, 8, 8, 8] | 8 | 8.0 | 0.0 | ✅ Complete |
| 1909 | 5/5 | [7, 7, 7, 7, 7] | 7 | 7.0 | 0.0 | ✅ Complete |
| 1866 | 0/5 | [] | None | None | None | ❌ Failed |
| 1860 | 1/5 | [2] | 2 | 2.0 | 0.0 | ⚠️ Partial |
| 1937 | 5/5 | [6, 6, 6, 6, 6] | 6 | 6.0 | 0.0 | ✅ Complete |
| 1794 | 6/5 | [1, 1, 1, 1, 1, 1] | 1 | 1.0 | 0.0 | ✅ Complete |

---

## For BENCHMARKS.ipynb

```python
'nous-hermes-2-mistral-7b-dpo': [8, 7, None, 2, 6, 1],
'nous-hermes-2-mistral-7b-dpo-mean': [8.0, 7.0, None, 2.0, 6.0, 1.0],
'nous-hermes-2-mistral-7b-dpo-variance': [0.0, 0.0, None, 0.0, 0.0, 0.0],
```

---

## Known Issues

**Articles 1860 and 1866:**
- Model consistently returned `"###"` (markdown heading) instead of integer scores
- Multiple retry attempts (5 runs) all failed
- Likely model-specific issue with these article contents
- Consider using alternative model for these articles or manual scoring

**Possible Causes:**
- Article content triggers model to generate markdown formatting
- Context length or prompt complexity issues
- Model-specific edge case

---

## Performance Notes

- **Perfect consistency** on completed articles (0.0 variance)
- Model produces identical scores across all 5 runs when successful
- Scoring failed on 33% of test articles (2/6)

