# Backfill Chunk Analysis - Help Text

## Short Version (for help bubble)
**Backfill Chunk Analysis** processes existing articles with high threat hunting scores (>50) to generate ML vs Hunt comparison data. This populates historical analysis results for articles processed before the ML comparison system was implemented.

## Detailed Version (if needed)
The Backfill Chunk Analysis feature:

- **Targets**: Articles with `threat_hunting_score > 50`
- **Process**: Runs content through ML model to generate chunk-level predictions
- **Compares**: ML predictions vs existing Hunt scoring methodology
- **Stores**: Results in `chunk_analysis_results` table for analysis
- **Purpose**: Populate historical comparison data for model evaluation

**When to use**: After implementing the ML comparison system, run this to generate baseline comparison data from existing high-scoring articles.

**Parameters**:
- Min Hunt Score: 50.0 (default threshold)
- Min Confidence: 0.7 (ML confidence threshold)
- Limit: Optional processing limit for testing
