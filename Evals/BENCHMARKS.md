# Benchmark Test Results

This document records benchmark test results for various language models evaluating article huntability scores.

## Test Results

| Article | Huntable GPT | GPT4o Median of 5 runs | gpt-oss-20b | Claude Sonnet 3.5 | Mistral 7B Instruct v0.2 | Mixtral 8x 7B Instruct | LLaMA 3 8B Instruct | LLaMA 3 70B Instruct | codellama-7b-instruct | qwen2-7b-instruct | nous-hermes-2-mistral-7b-dpo | qwen/qwen2.5-coder-32b | Phi-3 Medium (14 B) |
|---------|--------------|------------------------|-------------|-------------------|---------------------------|-------------------------|---------------------|----------------------|----------------------|---------------------|--------------------------------|------------------------|---------------------|
| http://127.0.0.1:8001/articles/1974 | 7 | 6 | | | | | | | | | | | |
| http://127.0.0.1:8001/articles/1909 | 7 | 6 | | | | | | | | | | | |
| http://127.0.0.1:8001/articles/1866 | 5, 9 | 5 | | | | | | | | | | | |
| http://127.0.0.1:8001/articles/1860 | 7 | 5 | | | | | | | | | | | |
| http://127.0.0.1:8001/articles/1937 | 8 | 3 | | | | | | | | | | | |
| http://127.0.0.1:8001/articles/1794 | 6 | 6 | | | | | | | | | | | |

---

## Notes

- Scores are integers on a scale (typically 0-10 or as defined by the evaluation prompt)
- "Median of 5 runs" indicates the median score across 5 separate evaluations
- Multiple scores may be comma-separated when multiple evaluations are recorded

