# Selecting Articles for Fine-Tuning

## Key Concept: Full Articles, Not Chunks

**Important:** The Extract Agent processes **full articles**, not chunks. Fine-tuning uses complete article content as input and expects complete extraction results as output.

The 1000-character chunks are only used for **analysis** to help you identify which articles contain observable-rich sections.

## Workflow

### 1. Identify Candidate Articles

Use the preparation script to analyze articles:

```bash
python scripts/prepare_articles_for_finetuning.py \
    --article-ids 1937 1974 1909 1866 \
    --analyze-only
```

This will:
- Analyze each article's content
- Identify observable-rich sections (using 1000-char chunks for analysis)
- Show keyword density and suitability scores
- Display top chunks with most observable keywords
- Check for existing extraction results

**Output:**
- Suitability score (0-10) based on keyword density
- Top 5 observable-rich chunks with previews
- Keyword breakdown (command, registry, process, etc.)

### 2. Review Analysis

Look for articles with:
- **High suitability score** (≥5.0): Rich in observable keywords
- **Existing extractions**: Already processed, can use results directly
- **Good keyword distribution**: Mix of command-line, registry, process chains

**Example output:**
```
Article 1937:
  Suitability score: 7.5/10
  Top keywords: command(12), registry(8), process(6)
  ✅ Existing extraction: 15 observables
  
  Top observable-rich sections:
  Chunk 1 (chars 0-1000, 8 keywords):
  "The malware executes the following command: powershell.exe -enc <base64>..."
```

### 3. Prepare Training Examples

Once you've identified good articles:

```bash
python scripts/prepare_articles_for_finetuning.py \
    --article-ids 1937 1974 1909 \
    --min-suitability 5.0 \
    --use-existing-extractions \
    --output outputs/training_data/manual_training_data.json
```

This creates training examples from:
- Full article content (not chunks)
- Existing extraction results (if available)
- Only articles meeting suitability threshold

### 4. For Articles Without Extractions

If an article has no existing extraction:

1. **Run Extract Agent first:**
   ```bash
   # Trigger workflow for the article
   python trigger_workflow.py --article-id 1937
   ```

2. **Or extract manually:**
   - Use the web UI to run extraction
   - Wait for workflow to complete
   - Then re-run preparation script

3. **Or provide manual observables:**
   - Edit the training data JSON
   - Add observables manually based on your analysis

## Understanding Chunk Analysis

The 1000-character chunks are **only for analysis** to help you:

1. **Identify observable-rich sections** within articles
2. **Understand article structure** (where observables are located)
3. **Assess article quality** (keyword density)

**They are NOT used for training.** Training uses:
- **Input**: Full article content
- **Output**: Complete extraction result (all observables from entire article)

## Best Practices

### Article Selection Criteria

**Good candidates:**
- ✅ Suitability score ≥ 5.0
- ✅ 3+ observables already extracted
- ✅ Mix of observable types (commands, registry, processes)
- ✅ Windows-specific content
- ✅ Technical depth (not just high-level descriptions)

**Avoid:**
- ❌ Articles with only atomic IOCs (IPs, hashes)
- ❌ Strategic/high-level content without technical details
- ❌ Non-Windows platforms (Linux, macOS, Cloud)
- ❌ Very short articles (<500 chars)

### Training Data Quality

**Minimum requirements:**
- 50+ articles for meaningful fine-tuning
- Each with 3+ observables
- Valid JSON extraction results

**Recommended:**
- 100-500 articles
- Average 5+ observables per article
- Diverse threat types (malware, APT, ransomware, etc.)

## Example: Complete Workflow

```bash
# Step 1: Analyze candidate articles
python scripts/prepare_articles_for_finetuning.py \
    --article-ids 1937 1974 1909 1866 1860 1794 \
    --analyze-only

# Review output, identify best articles

# Step 2: Extract observables for articles without extractions
# (Use web UI or trigger workflow)

# Step 3: Prepare training data
python scripts/prepare_articles_for_finetuning.py \
    --article-ids 1937 1974 1909 1866 \
    --min-suitability 5.0 \
    --use-existing-extractions \
    --output outputs/training_data/manual_training_data.json

# Step 4: Combine with other training data (optional)
# Merge with database-harvested data

# Step 5: Format and fine-tune
python scripts/format_extract_training_data.py \
    --input outputs/training_data/manual_training_data.json \
    --format alpaca

python scripts/finetune_extract_agent.py \
    --model mistralai/Mistral-7B-Instruct-v0.2 \
    --data outputs/training_data/manual_training_data_alpaca.json \
    --output models/extract_agent_finetuned
```

## FAQ

**Q: Do I need to manually identify sections?**
A: No. The script analyzes articles automatically. You just need to provide article IDs.

**Q: What if an article is too long?**
A: The Extract Agent handles truncation automatically. Full articles are preferred - truncation happens only if content exceeds model context.

**Q: Can I use partial articles?**
A: Not recommended. Fine-tuning should use full articles to learn complete extraction patterns.

**Q: How do I know if an article is good?**
A: Check the suitability score and keyword breakdown. Articles with score ≥5.0 and diverse keywords are good candidates.

