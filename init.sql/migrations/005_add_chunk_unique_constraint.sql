-- Migration: Add unique constraint to prevent duplicate chunk storage
-- Created: 2025-10-15
-- Purpose: Prevent storing the same chunk multiple times for the same article and model version

-- First, remove any existing duplicates (keeping the oldest record)
DELETE FROM chunk_analysis_results a
USING chunk_analysis_results b
WHERE a.id > b.id 
  AND a.article_id = b.article_id 
  AND a.model_version = b.model_version
  AND a.chunk_start = b.chunk_start 
  AND a.chunk_end = b.chunk_end;

-- Add unique constraint to prevent future duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_chunk_per_article_version 
ON chunk_analysis_results(article_id, model_version, chunk_start, chunk_end);

-- Add comment to document the constraint
COMMENT ON INDEX idx_unique_chunk_per_article_version IS 
'Ensures each chunk (defined by start/end positions) is stored only once per article and model version';

