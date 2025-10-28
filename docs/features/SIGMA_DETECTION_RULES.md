# SIGMA Detection Rules System

Comprehensive system for AI-powered SIGMA detection rule generation, matching against SigmaHQ repository, and similarity search.

## Table of Contents

1. [Overview](#overview)
2. [Rule Generation](#rule-generation)
3. [Rule Matching Pipeline](#rule-matching-pipeline)
4. [Similarity Search](#similarity-search)
5. [Technical Architecture](#technical-architecture)
6. [Usage & Examples](#usage--examples)
7. [CLI Commands](#cli-commands)
8. [API Reference](#api-reference)
9. [Configuration](#configuration)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The SIGMA Detection Rules System combines three powerful features:

1. **AI-Powered Generation**: Automatically creates detection rules from threat intelligence articles
2. **Rule Matching**: Matches articles to existing SigmaHQ rules (3,068+ indexed rules)
3. **Similarity Search**: Compares generated rules against existing community rules to prevent duplication

### System Flow

```
Article → Match Existing Rules → Classify Coverage → Generate New Rules (if needed) → Similarity Check → Store
```

### Key Benefits

- **Prevents Duplication**: Identifies existing coverage before generating new rules
- **Improves Quality**: Validates rules through pySIGMA and community comparison
- **Saves Time**: Automates rule creation and coverage analysis
- **Provides Context**: Shows relationships between articles and detection rules

---

## Rule Generation

### Features

#### 🤖 AI-Powered Rule Generation
- **Multiple AI Models**: Supports ChatGPT (OpenAI) and LMStudio (local LLM)
- **Content Analysis**: Analyzes article content to extract detection patterns
- **Context Awareness**: Understands threat techniques and attack patterns
- **Multiple Rule Generation**: Can generate multiple rules per article
- **Content Filtering**: ML-based optimization to reduce token usage
- **Consistent Temperature**: Uses temperature 0.2 for deterministic output

#### ✅ pySIGMA Validation
- **Automatic Validation**: All rules validated using pySIGMA
- **Compliance Checking**: Ensures SIGMA format requirements
- **Error Detection**: Identifies syntax errors and missing fields
- **Warning Detection**: Flags potential issues and best practices

#### 🔄 Iterative Rule Fixing
- **Automatic Retry**: Failed rules retried with error feedback
- **Up to 3 Attempts**: Maximum 3 generation attempts per rule set
- **Error Feedback**: AI receives detailed validation errors
- **Progressive Improvement**: Each attempt incorporates previous results

#### 📊 Metadata Storage
- **Complete Audit Trail**: Stores all generation attempts and validation results
- **Attempt Tracking**: Records number of attempts made
- **Validation Results**: Stores detailed errors and warnings
- **Generation Timestamps**: Tracks when rules were generated

#### 🔄 Conversation Log Display
- **Interactive Visualization**: Shows LLM ↔ pySigma validator conversation
- **Attempt-by-Attempt View**: Each retry in separate card with visual indicators
- **Collapsible Sections**: Long prompts/responses expandable
- **Color-Coded Feedback**: Valid (green) and invalid (red) results
- **Detailed Error Messages**: Specific validation errors from pySigma
- **Progressive Learning**: See how LLM improves based on feedback

### Prerequisites

- Article classified as "chosen" (required)
- Threat hunting score < 65 shows warning but allows proceeding
- AI model configured:
  - **ChatGPT**: OpenAI API key required
  - **LMStudio**: Local server running (no API key)
- pySIGMA library installed

### Generation Process

1. **Content Analysis**: AI analyzes article title and content
2. **Content Filtering**: ML-based optimization reduces token usage
3. **Pattern Extraction**: Identifies attack patterns and techniques
4. **Rule Creation**: Generates appropriate SIGMA detection rules
5. **Format Compliance**: Ensures proper YAML structure
6. **Validation**: pySIGMA validates generated rules
7. **Iterative Fixing**: Failed rules trigger retry with feedback (up to 3 attempts)
8. **Storage**: Rules stored in article metadata with audit trail

### Error Handling

**Common Validation Errors:**
- Missing required fields (title, logsource, detection)
- Invalid YAML syntax
- Incorrect field types
- Missing condition statements
- Invalid logsource configurations

**Retry Logic:**
- Maximum 3 attempts per rule set
- Error feedback provided to AI model
- Progressive improvement with each attempt
- Graceful failure after max attempts
- Complete conversation log captured for debugging

---

## Rule Matching Pipeline

A three-layer pipeline that matches CTI articles to existing Sigma detection rules from SigmaHQ, classifies coverage status, and intelligently generates new rules only when needed.

### Architecture Components

#### 1. Database Schema

**Tables:**
- `sigma_rules`: Stores Sigma detection rules with embeddings
  - 768-dimensional pgvector embeddings for semantic search
  - JSONB fields for logsource and detection logic
  - Full metadata (tags, level, status, author, references)
  - Source tracking (file_path, repo_commit_sha)

- `article_sigma_matches`: Stores article-to-rule matches
  - Similarity scores and match levels (article/chunk)
  - Coverage classification (covered/extend/new)
  - Matched behaviors (discriminators, LOLBAS, intelligence)

**Indexes:**
- IVFFlat vector index for embedding similarity search
- GIN indexes for JSONB logsource and tags arrays
- BTree indexes for foreign keys and coverage status

#### 2. Sigma Sync Service

**File**: `src/services/sigma_sync_service.py`

**Features:**
- Clones/pulls SigmaHQ repository (read-only)
- Parses YAML rule files using PyYAML
- Extracts all rule fields (title, description, logsource, detection, tags)
- Generates embeddings from enriched rule text
- Batch indexing with progress tracking
- Incremental updates (only new rules)

**Key Methods:**
- `clone_or_pull_repository()`: Git operations
- `find_rule_files()`: Recursive file discovery
- `parse_rule_file()`: YAML parsing and normalization
- `create_rule_embedding_text()`: Embedding text generation
- `index_rules()`: Batch indexing with embeddings

#### 3. Sigma Matching Service

**File**: `src/services/sigma_matching_service.py`

**Features:**
- Article-level semantic search using existing embeddings
- Chunk-level semantic search with on-the-fly embedding generation
- Pgvector cosine similarity queries
- Configurable threshold and limits
- Match storage with full metadata

**Key Methods:**
- `match_article_to_rules()`: Article-level matching
- `match_chunks_to_rules()`: Chunk-level matching with deduplication
- `store_match()`: Persist matches to database
- `get_article_matches()`: Retrieve matches with rule details
- `get_coverage_summary()`: Aggregate coverage statistics

**SQL Query Pattern:**
```sql
SELECT sr.*, 1 - (sr.embedding <=> :embedding::vector) AS similarity
FROM sigma_rules sr
WHERE sr.embedding IS NOT NULL
  AND 1 - (sr.embedding <=> :embedding::vector) >= :threshold
ORDER BY similarity DESC
LIMIT :limit
```

#### 4. Coverage Classification Service

**File**: `src/services/sigma_coverage_service.py`

**Features:**
- Extracts behaviors from `chunk_analysis_results`
- Compares article behaviors to rule detection patterns
- Classifies as covered/extend/new
- Confidence scoring
- Detailed reasoning generation

**Classification Logic:**
- **Covered** (similarity ≥ 0.85, overlap ≥ 0.7): Behaviors well represented
- **Extend** (similarity ≥ 0.7, overlap ≥ 0.3): Partial overlap, room for extension
- **New** (low overlap): Represents new detection opportunity

**Key Methods:**
- `extract_article_behaviors()`: Aggregate discriminators, LOLBAS, intelligence
- `extract_rule_patterns()`: Parse Sigma detection fields
- `calculate_behavior_overlap()`: Compare behaviors to patterns
- `classify_match()`: Full classification with reasoning
- `analyze_article_coverage()`: Overall coverage analysis

### Enhanced Generation Workflow

**File**: `src/web/routes/ai.py`

1. **Match Phase**: Automatically match article to existing rules (threshold 0.7)
2. **Classify Phase**: Classify each match as covered/extend/new
3. **Store Phase**: Persist matches to database
4. **Decision Phase**: 
   - If ≥2 rules marked "covered": Skip generation, return matches
   - Otherwise: Proceed with LLM generation

**New Parameters:**
- `skip_matching`: Boolean to bypass matching phase
- Returns `matched_rules` and `coverage_summary` in all responses

### Embedding Strategy

- **Model**: all-mpnet-base-v2 (768 dimensions)
- **Reuse**: Leverages existing `EmbeddingService`
- **Article embeddings**: Already populated in `articles.embedding`
- **Chunk embeddings**: Generated on-demand from `chunk_analysis_results`
- **Rule embeddings**: Combines title + description + logsource + tags

### Behavior Extraction

**Source**: `chunk_analysis_results` table

**Fields used:**
- `perfect_discriminators_found`: High-confidence indicators
- `good_discriminators_found`: Medium-confidence indicators
- `lolbas_matches_found`: Living-off-the-land binaries
- `intelligence_matches_found`: Intelligence indicators
- `hunt_score`: Threat hunting relevance score

### Coverage Classification

- **Covered**: Article behaviors ⊆ rule detection patterns
- **Extend**: Partial overlap, article has additional behaviors
- **New**: Minimal overlap, new detection opportunity

---

## Similarity Search

Enhances "Generate SIGMA Rules" by comparing proposed/generated rules against indexed SigmaHQ repository using semantic similarity search.

### Purpose

1. **Prevents Duplication**: Identifies if similar rules already exist
2. **Provides Context**: Shows relationship to community rules
3. **Improves Quality**: Helps understand coverage gaps
4. **Saves Time**: Avoids recreating existing rules

### How It Works

```
User Request → Generate Sigma Rules (AI) → For Each Generated Rule:
  1. Extract title + description
  2. Generate embedding
  3. Query sigma_rules table (cosine similarity)
  4. Return top 5 matches (≥70% similarity)
→ Return Response with similar_rules field
```

### Embedding Details

- **Model**: all-mpnet-base-v2 (768 dimensions)
- **Input**: Rule title + description concatenated
- **Similarity Metric**: Cosine similarity (1 - cosine distance)
- **Threshold**: 0.7 (70% similarity minimum)
- **Performance**: ~150-500ms overhead per generated rule

### Similarity Interpretation

- **High Similarity (>0.9)**: Consider using existing rule instead
- **Medium Similarity (0.7-0.9)**: Review for potential extension
- **No Matches**: Novel detection opportunity

---

## Technical Architecture

### Technology Stack

- **Database**: PostgreSQL with pgvector extension
- **Embeddings**: all-mpnet-base-v2 (sentence-transformers)
- **Rule Format**: SIGMA YAML specification
- **Validation**: pySIGMA library
- **Repository**: SigmaHQ official repository
- **API**: FastAPI with async support

### Performance

- **Indexing**: ~5000 rules indexed in 10-15 minutes
- **Matching**: Article-level match ~100ms, chunk-level ~500ms
- **Vector Index**: IVFFlat with 100 lists provides sub-second similarity search
- **Batch Operations**: Process ~100 articles/minute with matching + classification
- **Query Time**: ~50-200ms per rule similarity search
- **Embedding Generation**: ~100-300ms per rule

### Database Infrastructure

- **Records**: 3,068+ indexed Sigma rules with embeddings
- **Index Type**: IVFFlat vector index for fast similarity search
- **Vector Dimension**: 768 (all-mpnet-base-v2 model)
- **Storage**: JSONB for flexible rule metadata

---

## Usage & Examples

### Initial Setup

```bash
# 1. Sync SigmaHQ repository (first time)
./run_cli.sh sigma sync

# 2. Index all rules (generates embeddings)
./run_cli.sh sigma index

# 3. View statistics
./run_cli.sh sigma stats
```

**Expected Output:**
```
Sigma Rule Index Statistics
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric                 ┃ Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total Rules            │ 5247  │
│ Rules with Embeddings  │ 5247  │
│ Total Matches          │ 0     │
└────────────────────────┴───────┘
```

### Match Single Article

```bash
./run_cli.sh sigma match 123 --save
```

**Output:**
```
Matches for Article 123
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Rule ID         ┃ Title                                   ┃ Similarity ┃ Level ┃ Coverage ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ a1b2c3d4...     │ PowerShell Suspicious Script Execution │ 0.875      │ high  │ covered  │
│ e5f6g7h8...     │ Suspicious Process Creation            │ 0.823      │ med   │ extend   │
│ i9j0k1l2...     │ Registry Modification Detection        │ 0.756      │ low   │ new      │
└─────────────────┴─────────────────────────────────────────┴────────────┴───────┴──────────┘
```

### Batch Matching

```bash
# Match all articles with embeddings and hunt_score >= 50
./run_cli.sh sigma match-all --min-hunt-score 50 --threshold 0.7
```

### Web Interface Usage

1. Navigate to any article classified as "chosen"
2. Click "Generate SIGMA Rules" button
3. AI processes article content
4. System checks for existing coverage
5. Generates new rules if needed
6. Shows similarity to existing rules
7. View conversation log showing LLM ↔ pySigma interaction

---

## CLI Commands

**File**: `src/cli/sigma_commands.py`

### Available Commands

```bash
# Sync SigmaHQ repository
./run_cli.sh sigma sync

# Index rules with embeddings
./run_cli.sh sigma index [--force]

# Match single article
./run_cli.sh sigma match <article_id> [--save]

# Batch match articles
./run_cli.sh sigma match-all [--limit N] [--min-hunt-score N]

# Show index statistics
./run_cli.sh sigma stats
```

### Features

- Rich console output with tables
- Progress tracking for batch operations
- Option to save matches to database
- Configurable thresholds
- Hunt score filtering for batch operations

---

## API Reference

### Generate SIGMA Rules (with Matching & Similarity)

**Endpoint**: `POST /api/articles/{article_id}/generate-sigma`

**Request:**
```json
{
  "force_regenerate": false,
  "include_content": true,
  "ai_model": "chatgpt",
  "api_key": "your_api_key_here",
  "author_name": "CTIScraper User",
  "temperature": 0.2,
  "skip_matching": false,
  "optimization_options": {
    "useFiltering": true,
    "minConfidence": 0.7
  }
}
```

**Response (Article is Covered):**
```json
{
  "success": true,
  "matched_rules": [
    {
      "rule_id": "a1b2c3d4-...",
      "title": "PowerShell Suspicious Script Execution",
      "similarity": 0.875,
      "coverage_status": "covered",
      "matched_behaviors": ["powershell.exe", "EncodedCommand", "bypass"]
    }
  ],
  "coverage_summary": {
    "covered": 2,
    "extend": 1,
    "new": 0,
    "total": 3
  },
  "generated_rules": [],
  "similar_rules": [],
  "recommendation": "Article behaviors are covered by 2 existing Sigma rule(s). No new rules needed.",
  "skipped_generation": true
}
```

**Response (New Rules Generated):**
```json
{
  "success": true,
  "rules": [
    {
      "title": "Suspicious PowerShell Execution",
      "description": "Detects suspicious PowerShell command execution...",
      "logsource": {...},
      "detection": {...}
    }
  ],
  "similar_rules": [
    {
      "generated_rule": {
        "title": "Suspicious PowerShell Execution",
        "description": "Detects suspicious PowerShell command execution..."
      },
      "similar_existing_rules": [
        {
          "rule_id": "a1b2c3d4-...",
          "title": "PowerShell Execution with Encoded Commands",
          "similarity": 0.87,
          "level": "high",
          "status": "stable",
          "file_path": "rules/windows/process_creation/proc_creation_win_powershell_encoded_cmd.yml"
        }
      ]
    }
  ],
  "validation_results": [...],
  "conversation": [...],
  "validation_passed": true,
  "attempts_made": 1,
  "matched_rules": [],
  "coverage_summary": {...}
}
```

### Get Existing Matches

**Endpoint**: `GET /api/articles/{article_id}/sigma-matches`

**Response:**
```json
{
  "success": true,
  "matches": [
    {
      "rule_id": "a1b2c3d4-...",
      "title": "PowerShell Suspicious Script Execution",
      "similarity_score": 0.875,
      "coverage_status": "covered",
      "matched_discriminators": ["powershell.exe", "EncodedCommand"],
      "matched_lolbas": ["powershell.exe", "cmd.exe"],
      "created_at": "2025-01-16T10:30:00"
    }
  ],
  "coverage_summary": {
    "covered": 2,
    "extend": 1,
    "new": 0,
    "total": 3
  }
}
```

---

## Configuration

### Environment Variables

```bash
SIGMA_REPO_PATH=./data/sigma-repo
SIGMA_MATCH_THRESHOLD=0.7
```

### AI Model Configuration

**ChatGPT (OpenAI)**
- Model: gpt-4o-mini
- API Key: Required in request body
- Temperature: 0.2 (for consistent output)
- Best for: High-quality rule generation

**LMStudio (Local LLM)**
- Model: User-configured (e.g., llama-3.2-1b-instruct)
- API Key: Not required
- Temperature: 0.2 (for consistent output)
- Best for: Local processing, privacy, cost savings

### Similarity Thresholds

- **Default**: 0.7 (70% similarity)
- **Covered Classification**: ≥ 0.85 similarity, ≥ 0.7 overlap
- **Extend Classification**: ≥ 0.7 similarity, ≥ 0.3 overlap
- **New Classification**: Low overlap

### Content Filtering

```json
{
  "optimization_options": {
    "useFiltering": true,      // Enable content filtering
    "minConfidence": 0.7       // Minimum confidence threshold
  }
}
```

---

## Troubleshooting

### Common Issues

#### API Key Errors
- Check API key configuration (ChatGPT only)
- Verify API quota and billing
- Monitor rate limiting
- LMStudio requires no API key, verify local server running

#### pySIGMA Validation Failures
- Ensure pySIGMA properly installed
- Check rule format compliance
- Review validation error messages
- Examine conversation log for debugging

#### Generation Failures
- Verify article classified as "chosen"
- Check threat hunting score (warning below 65)
- Review AI model availability
- Check content filtering settings

#### No Similarity Results
1. Verify SigmaHQ rules indexed with embeddings:
   ```bash
   ./run_cli.sh sigma stats
   ```
2. Check embedding service working:
   ```bash
   docker-compose exec web python -c "from src.services.embedding_service import EmbeddingService; e = EmbeddingService(); print(len(e.generate_embedding('test')))"
   ```
3. Lower similarity threshold temporarily to test

#### Slow Performance
1. Rebuild vector index:
   ```sql
   REINDEX INDEX idx_sigma_rules_embedding;
   ```
2. Adjust IVFFlat lists parameter
3. Increase database resources

#### Import Errors
All operations should run inside Docker containers:
```bash
docker-compose exec web python -m src.cli.main sigma [command]
```

### Debug Commands

```bash
# Enable debug logging
LOG_LEVEL=DEBUG

# Check generation logs
docker-compose logs -f web | grep "SIGMA"

# Check service status
docker-compose ps

# Test embedding service
docker-compose exec web python -c "from src.services.embedding_service import EmbeddingService; print('OK')"
```

### Monitoring

```sql
-- Average similarity scores
SELECT AVG(similarity) 
FROM article_sigma_matches 
WHERE match_level = 'article';

-- Distribution of similarity scores
SELECT 
    CASE 
        WHEN similarity >= 0.9 THEN 'Very High (0.9+)'
        WHEN similarity >= 0.8 THEN 'High (0.8-0.9)'
        WHEN similarity >= 0.7 THEN 'Medium (0.7-0.8)'
        ELSE 'Low (<0.7)'
    END as similarity_range,
    COUNT(*) as count
FROM article_sigma_matches
GROUP BY similarity_range;
```

---

## Maintenance

### Regular Updates

```bash
# Update SigmaHQ repository
./run_cli.sh sigma sync

# Re-index rules
./run_cli.sh sigma index --force

# Check statistics
./run_cli.sh sigma stats
```

### Metrics Tracked

- Rules generated per day
- Validation success rate
- Average attempts per generation
- Most common validation errors
- Generation processing time
- Match coverage distribution

### Health Checks

- OpenAI API connectivity
- pySIGMA validation status
- Generation success rates
- Average attempts per rule set
- Similarity search performance

---

## Security Considerations

### Data Privacy
- Article content sent to AI model for analysis
- No sensitive data stored in AI provider logs (ChatGPT)
- Rules stored locally in database
- LMStudio provides local processing for full privacy

### Input Validation
- Article ID validation
- Classification requirement ("chosen")
- Threat score thresholds
- Rate limiting on generation requests
- API key validation for external models

### Output Validation
- pySIGMA validation ensures rule safety
- No arbitrary code execution
- Structured rule format only

---

## Future Enhancements

### Planned Features
- Custom rule templates
- Automatic rule performance optimization
- Bulk rule generation
- Rule testing with SIEM frameworks
- Rule sharing and export
- Batch similarity search
- Weighted similarity (consider detection logic)
- Similarity explanations
- Auto-merge suggestions
- Cross-platform matching

### Integration Opportunities
- SIEM platform integration
- Direct PR creation to SigmaHQ
- Enhanced TTP extraction and mapping
- ML-based rule quality assessment
- Periodic automated SigmaHQ sync
- Rule suggestions for "extend" matches
- Performance optimization with chunk embedding caching

---

## Files & Components

### Created Files
- `init.sql/migrations/20250116_add_sigma_matching_tables.sql`
- `src/services/sigma_sync_service.py`
- `src/services/sigma_matching_service.py`
- `src/services/sigma_coverage_service.py`
- `src/cli/sigma_commands.py`

### Modified Files
- `src/database/models.py` (added SigmaRuleTable, ArticleSigmaMatchTable)
- `src/web/routes/ai.py` (enhanced with match-first logic)
- `src/cli/main.py` (registered sigma_group commands)
- `requirements.txt` (added GitPython==3.1.43)

### Dependencies
- `GitPython==3.1.43`: Repository management
- `pysigma==0.11.23`: Rule parsing/validation
- `pgvector>=0.4.0`: Vector similarity
- `sentence-transformers>=2.2.2`: Embeddings (all-mpnet-base-v2)

---

## Support

For issues and questions:
- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: Check this guide and API documentation
- **Community**: Join CTI Scraper community discussions

---

## References

- [SigmaHQ Repository](https://github.com/SigmaHQ/sigma)
- [Sigma Specification](https://github.com/SigmaHQ/sigma-specification)
- [pgvector](https://github.com/pgvector/pgvector)
- [Sentence Transformers](https://www.sbert.net/)
- [pySIGMA Documentation](https://sigmahq-pysigma.readthedocs.io/)
- [Cosine Similarity](https://en.wikipedia.org/wiki/Cosine_similarity)

---

**Status**: ✅ Complete and Functional  
**Last Updated**: January 2025

