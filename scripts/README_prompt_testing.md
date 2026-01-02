# Prompt Testing Script

Flexible script to test prompts from the database against LMStudio models.

## Quick Start

```bash
# Use the helper script (recommended)
./scripts/run_prompt_test.sh --help

# Or run directly in Docker
docker exec -it cti_workflow_worker python3 /app/scripts/test_prompt_with_models.py --help
```

## Features

- ✅ Loads current prompt from database (same as UI shows)
- ✅ Tab-completable model selection (use shell tab completion)
- ✅ Wildcard support for model selection (`qwen/*`, `*8b*`, etc.)
- ✅ Test single article or all eval articles
- ✅ Multiple models at once
- ✅ Saves results to JSON file

## Examples

### List available models
```bash
./scripts/run_prompt_test.sh --list-models
```

### List eval articles
```bash
./scripts/run_prompt_test.sh --list-eval-articles
```

### Test single model on single article
```bash
./scripts/run_prompt_test.sh --model "qwen/qwen3-8b" --article 68
```

### Test multiple models with wildcards
```bash
./scripts/run_prompt_test.sh --model "qwen/*" --article 68
```

### Test all Qwen models on all eval articles
```bash
./scripts/run_prompt_test.sh --model "qwen/*" --all-eval
```

### Test specific models on multiple articles
```bash
./scripts/run_prompt_test.sh --model "qwen/qwen3-8b" "mistral/*" --article 68 69 70
```

### Test with content filtering
```bash
./scripts/run_prompt_test.sh --model "qwen/qwen3-8b" --article 68 --use-junk-filter --junk-filter-threshold 0.8
```

## Output

Results are saved to `prompt_test_results.json` with:
- Success/failure status
- Model name
- Article ID and title
- Extraction results (count, items)
- Error messages if failed

## Tab Completion

For better tab completion, add to your `.bashrc` or `.zshrc`:

```bash
# Tab completion for model names (requires listing models first)
_complete_models() {
    local models=$(docker exec cti_workflow_worker python3 /app/scripts/test_prompt_with_models.py --list-models 2>/dev/null | grep "  -" | sed 's/  - //')
    COMPREPLY=($(compgen -W "$models" -- "${COMP_WORDS[COMP_CWORD]}"))
}
complete -F _complete_models ./scripts/run_prompt_test.sh
```

