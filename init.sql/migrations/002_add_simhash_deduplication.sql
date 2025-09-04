-- Migration: Add SimHash deduplication support
-- Date: 2024-09-04
-- Description: Adds SimHash fields and tables for enhanced deduplication

-- Add SimHash fields to articles table
ALTER TABLE articles 
ADD COLUMN IF NOT EXISTS simhash BIGINT,
ADD COLUMN IF NOT EXISTS simhash_bucket INTEGER;

-- Create indexes for SimHash fields
CREATE INDEX IF NOT EXISTS idx_articles_simhash ON articles(simhash);
CREATE INDEX IF NOT EXISTS idx_articles_simhash_bucket ON articles(simhash_bucket);

-- Create SimHash buckets table
CREATE TABLE IF NOT EXISTS simhash_buckets (
    id SERIAL PRIMARY KEY,
    bucket_id INTEGER NOT NULL,
    simhash BIGINT NOT NULL,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_simhash_buckets_bucket_id (bucket_id),
    INDEX idx_simhash_buckets_simhash (simhash),
    INDEX idx_simhash_buckets_article_id (article_id),
    INDEX idx_simhash_buckets_first_seen (first_seen)
);

-- Add unique constraint to prevent duplicate SimHash entries
ALTER TABLE simhash_buckets 
ADD CONSTRAINT unique_simhash_article UNIQUE (simhash, article_id);

-- Add comments for documentation
COMMENT ON TABLE simhash_buckets IS 'Stores SimHash values and buckets for near-duplicate detection';
COMMENT ON COLUMN articles.simhash IS '64-bit SimHash for near-duplicate detection';
COMMENT ON COLUMN articles.simhash_bucket IS 'Bucket number for efficient SimHash lookup';
COMMENT ON COLUMN simhash_buckets.bucket_id IS 'SimHash bucket number for efficient lookup';
COMMENT ON COLUMN simhash_buckets.simhash IS '64-bit SimHash value';
COMMENT ON COLUMN simhash_buckets.first_seen IS 'When this SimHash was first encountered';

-- Create function to compute SimHash bucket
CREATE OR REPLACE FUNCTION compute_simhash_bucket(simhash_value BIGINT, num_buckets INTEGER DEFAULT 16)
RETURNS INTEGER AS $$
BEGIN
    RETURN simhash_value % num_buckets;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Create function to check for similar SimHashes
CREATE OR REPLACE FUNCTION hamming_distance(simhash1 BIGINT, simhash2 BIGINT)
RETURNS INTEGER AS $$
BEGIN
    RETURN length(replace(bitstring(simhash1 # simhash2), '0', ''));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Create function to find similar articles
CREATE OR REPLACE FUNCTION find_similar_articles(
    target_simhash BIGINT, 
    threshold INTEGER DEFAULT 3,
    max_results INTEGER DEFAULT 10
)
RETURNS TABLE(
    article_id INTEGER,
    simhash BIGINT,
    hamming_dist INTEGER,
    title TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.simhash,
        hamming_distance(a.simhash, target_simhash) as hamming_dist,
        a.title
    FROM articles a
    WHERE a.simhash IS NOT NULL
    AND hamming_distance(a.simhash, target_simhash) <= threshold
    ORDER BY hamming_distance(a.simhash, target_simhash)
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
