# Commandline Extractor Evaluation

This directory contains evaluation scripts for the commandline extractor component of the CTI Scraper system.

## Overview

The evaluation system provides:
- **Quantitative metrics**: Precision, recall, F1-score against ground truth
- **Qualitative evaluation**: LLM-as-a-Judge scoring (requires agentevals)
- **Trajectory matching**: Exact match evaluation of extraction patterns
- **Configurable presets**: JSON-based configuration for different evaluation scenarios

## Files

- `evaluate_cmdline_extractor.py` - Main evaluation script
- `cmdline_eval_preset.json` - Example configuration preset
- `test_cmdline_eval.py` - Test script for basic functionality

## Installation Requirements

```bash
# Required dependencies (install in virtual environment)
pip install agentevals langfuse  # Optional: agentevals for LLM-as-judge evaluation

# The script will work without agentevals but with reduced functionality
```

## Usage

### Dataset Evaluation

```bash
# Run evaluation on all articles in dataset
python scripts/evaluate_cmdline_extractor.py --preset scripts/cmdline_eval_preset.json --output results.json

# Run with verbose logging
python scripts/evaluate_cmdline_extractor.py --preset scripts/cmdline_eval_preset.json --verbose
```

### Single Article Evaluation

```bash
# Evaluate specific article by ID from dataset
python scripts/evaluate_cmdline_extractor.py --preset scripts/cmdline_eval_preset.json --article-id sample_1

# Evaluate single article from JSON string
python scripts/evaluate_cmdline_extractor.py --single-article '{
  "id": "test_article",
  "input": {
    "article_content": "The malware used cmd.exe /c mklink command to create links.",
    "article_title": "Malware Analysis Report"
  },
  "expected_output": {
    "cmdline_items": ["cmd.exe /c mklink"]
  }
}'

# Evaluate single article from JSON file
python scripts/evaluate_cmdline_extractor.py --single-article /path/to/my_article.json

# Evaluate article directly from Postgres database (extraction testing only - no ground truth)
python scripts/evaluate_cmdline_extractor.py --db-article-id 12345
```

**Note:** When using `--db-article-id`, the database article won't have ground truth labels, so quantitative metrics (precision/recall/F1) will show 0. This mode is useful for testing extraction behavior and seeing what commands are found, but for full evaluation with metrics, use JSON files with `expected_output` or LangFuse datasets.

### Configuration

Create a preset JSON file (see `cmdline_eval_preset.json` for example):

```json
{
  "description": "Commandline Extractor Evaluation Configuration",
  "ground_truth_dataset": "cmdline_gold_standard",
  "dataset_source": "langfuse",  // or "local" for JSON files

  "evaluation_settings": {
    "use_llm_judge": true,        // Requires agentevals
    "use_trajectory_match": true, // Requires agentevals
    "continuous_scoring": false,
    "match_mode": "unordered"
  },

  "models": {
    "extraction_model": "qwen/qwen2.5-coder-14b",
    "judge_model": "openai:o3-mini",
    "provider": "lmstudio"
  },

  "extraction_config": {
    "temperature": 0.1,
    "max_tokens": 1000,
    "timeout": 60
  }
}
```

### Ground Truth Format

The evaluation expects ground truth in this format:

```json
{
  "id": "sample_1",
  "input": {
    "article_content": "Article text containing Windows commands...",
    "article_title": "Threat Report Title"
  },
  "expected_output": {
    "cmdline_items": [
      "cmd.exe /c echo hello",
      "powershell -Command Write-Host 'test'"
    ]
  },
  "metadata": {
    "source": "manual_annotation",
    "difficulty": "medium"
  }
}
```

## Evaluation Metrics

### Quantitative Metrics
- **Precision**: Correct extractions / Total extractions
- **Recall**: Correct extractions / Total expected commands
- **F1 Score**: Harmonic mean of precision and recall
- **True/False Positives/Negatives**: Detailed breakdown

### Qualitative Evaluation (LLM-as-a-Judge)
- **Scoring**: 0-1 scale for extraction quality
- **Reasoning**: Detailed explanation of evaluation
- **Trajectory Analysis**: Pattern matching against expected workflows

## Testing

Run the test suite to verify functionality:

```bash
python scripts/test_cmdline_eval.py
```

## Output Format

Results are saved as JSON with this structure:

```json
{
  "config": {...},
  "results": [
    {
      "item_id": "sample_1",
      "extraction_result": {...},
      "expected_commands": [...],
      "evaluations": {
        "basic_metrics": {...},
        "llm_judge": {...},
        "trajectory_match": {...}
      },
      "status": "success"
    }
  ],
  "summary": {
    "total_evaluated": 2,
    "basic_metrics_avg": {
      "precision": 0.85,
      "recall": 0.90,
      "f1_score": 0.87
    },
    "llm_judge_avg_score": 0.82
  }
}
```

## Integration with LangFuse

The evaluation script integrates with LangFuse for:
- **Dataset Management**: Store and version ground truth data
- **Trace Logging**: Record evaluation runs for debugging
- **Experiment Tracking**: Compare evaluation results over time

## Troubleshooting

### Common Issues

1. **"agentevals not available"**: Install with `pip install agentevals` or disable LLM judge features
2. **"Model not found"**: Ensure LM Studio models are loaded and accessible
3. **"Dataset not found"**: Check dataset name and LangFuse connection

### Debug Mode

Enable verbose logging for detailed execution information:

```bash
python scripts/evaluate_cmdline_extractor.py --preset config.json --verbose
```

## Future Enhancements

- [ ] Full LangFuse dataset API integration
- [ ] Batch evaluation across multiple models
- [ ] Statistical significance testing
- [ ] Custom evaluation metrics
- [ ] Web-based evaluation dashboard