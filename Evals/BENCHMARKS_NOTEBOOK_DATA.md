# BENCHMARKS.ipynb Update Data

## For Adding Deepseek-R1-Qwen3-8B

Add these lines to the data dictionary in BENCHMARKS.ipynb:

```python
'deepseek-r1-qwen3-8b': [7, 8, 8, 8, 8, 6],
'deepseek-r1-qwen3-8b-mean': [7.2, 7.8, 8.4, 8.8, 7.2, 5.8],
'deepseek-r1-qwen3-8b-variance': [0.6, 0.2, 0.3, 1.1, 6.0, 5.1],
```

## Complete Updated Data Dictionary (Reference)

```python
data = {
    'Article': ['1974', '1909', '1866', '1860', '1937', '1794'],
    'Hunt Score': [81.3, 99.6, 96.7, 97.9, 93.1, 95.3],
    'Huntable GPT': ['7', '7', '5, 9', '7', '8', '6'],
    'GPT4o Median of 5 runs': [6, 6, 5, 5, 3, 6],
    'gpt-oss-20b': [1, 1, 2, 7, 6, 10],
    'gpt-oss-20b-mean': [3.40, 1.00, 3.80, 7.80, 7.20, 8.80],
    'gpt-oss-20b-variance': [10.80, 0.00, 13.20, 1.70, 6.70, 4.70],
    'Claude Sonnet 3.5': [7, 6, 6, 8, 7, 6],
    'Claude Sonnet 3.5-mean': [7.0, 6, 6, 8, 7, 6.2],
    'Claude Sonnet 3.5-variance': [0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
    'codellama-7b-instruct': [7, 7, 9, 8, 9, 8],
    'codellama-7b-instruct-mean': [7.0, 7.0, 9.0, 8.0, 9.0, 8.0],
    'codellama-7b-instruct-variance': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    'qwen2-7b-instruct': [9, 7, 8, 8, 8, 8],
    'qwen2-7b-instruct-mean': [9.0, 6.6, 8.0, 8.0, 8.0, 8.4],
    'qwen2-7b-instruct-variance': [0.0, 4.8, 0.0, 0.0, 0.0, 0.3],
    'nous-hermes-2-mistral-7b-dpo': [8, 7, None, 2, 6, 1],
    'nous-hermes-2-mistral-7b-dpo-mean': [8.0, 7.0, None, 2.0, 6.0, 1.0],
    'nous-hermes-2-mistral-7b-dpo-variance': [0.0, 0.0, None, 0.0, 0.0, 0.0],
    'qwen/qwen2.5-coder-32b': [7, 8, 5, 8, 7, 7],
    'qwen/qwen2.5-coder-32b-mean': [7.0, 8.0, 5.8, 8.0, 7.0, 7.0],
    'qwen/qwen2.5-coder-32b-variance': [0.0, 0.0, 1.2, 0.0, 0.0, 0.0],
    'Mistral 7B Instruct v0.3': [8, 7, 8, 6, 7, 7],
    'Mistral 7B Instruct v0.3-mean': [7.8, 7.2, 7.6, 6.0, 6.8, 7.0],
    'Mistral 7B Instruct v0.3-variance': [0.2, 0.2, 0.3, 0.0, 0.2, 0.0],
    'deepseek-r1-qwen3-8b': [7, 8, 8, 8, 8, 6],
    'deepseek-r1-qwen3-8b-mean': [7.2, 7.8, 8.4, 8.8, 7.2, 5.8],
    'deepseek-r1-qwen3-8b-variance': [0.6, 0.2, 0.3, 1.1, 6.0, 5.1],
}
```

