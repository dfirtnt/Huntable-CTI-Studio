-- Migration: Add chunk-level filtering and labeling tables
-- Date: 2024-01-01
-- Description: Adds tables for chunk processing, scoring, labeling, and article quality

-- Create chunks table
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    text TEXT NOT NULL,
    hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_chunks_article_id (article_id),
    INDEX idx_chunks_hash (hash),
    INDEX idx_chunks_created_at (created_at)
);

-- Create chunk_scores table
CREATE TABLE IF NOT EXISTS chunk_scores (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    score FLOAT NOT NULL,
    hits JSONB NOT NULL DEFAULT '{}',
    noise_hits JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_chunk_scores_chunk_id (chunk_id),
    INDEX idx_chunk_scores_score (score),
    INDEX idx_chunk_scores_created_at (created_at)
);

-- Create chunk_labels table
CREATE TABLE IF NOT EXISTS chunk_labels (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_chunk_labels_chunk_id (chunk_id),
    INDEX idx_chunk_labels_created_at (created_at)
);

-- Create article_quality table
CREATE TABLE IF NOT EXISTS article_quality (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL UNIQUE REFERENCES articles(id) ON DELETE CASCADE,
    excellent BOOLEAN NOT NULL DEFAULT FALSE,
    excellent_prob FLOAT,
    rollup JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_article_quality_article_id (article_id),
    INDEX idx_article_quality_excellent (excellent),
    INDEX idx_article_quality_excellent_prob (excellent_prob),
    INDEX idx_article_quality_created_at (created_at)
);

-- Add comments for documentation
COMMENT ON TABLE chunks IS 'Stores text chunks extracted from articles for processing';
COMMENT ON TABLE chunk_scores IS 'Stores prefilter scores and pattern hits for chunks';
COMMENT ON TABLE chunk_labels IS 'Stores Label Studio annotations for chunks';
COMMENT ON TABLE article_quality IS 'Stores rollup quality scores for articles';

COMMENT ON COLUMN chunks.start_offset IS 'Starting character offset in original article';
COMMENT ON COLUMN chunks.end_offset IS 'Ending character offset in original article';
COMMENT ON COLUMN chunks.hash IS 'SHA-256 hash of chunk text for deduplication';
COMMENT ON COLUMN chunk_scores.score IS 'Prefilter quality score (0.0 to 1.0)';
COMMENT ON COLUMN chunk_scores.hits IS 'JSON object containing pattern matches';
COMMENT ON COLUMN chunk_scores.noise_hits IS 'JSON object containing noise pattern matches';
COMMENT ON COLUMN chunk_labels.payload IS 'Full Label Studio export format';
COMMENT ON COLUMN article_quality.excellent IS 'Whether article contains excellent chunks';
COMMENT ON COLUMN article_quality.excellent_prob IS 'Probability that article is excellent';
COMMENT ON COLUMN article_quality.rollup IS 'Metadata about rollup calculation';

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_article_quality_updated_at 
    BEFORE UPDATE ON article_quality 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Add some helpful views for analysis
CREATE OR REPLACE VIEW chunk_analysis AS
SELECT 
    c.id as chunk_id,
    c.article_id,
    c.start_offset,
    c.end_offset,
    c.text,
    c.hash,
    c.created_at as chunk_created_at,
    cs.score as prefilter_score,
    cs.hits as pattern_hits,
    cs.noise_hits as noise_patterns,
    cs.created_at as score_created_at,
    cl.payload as label_data,
    cl.created_at as label_created_at,
    aq.excellent as article_excellent,
    aq.excellent_prob as article_excellent_prob
FROM chunks c
LEFT JOIN chunk_scores cs ON c.id = cs.chunk_id
LEFT JOIN chunk_labels cl ON c.id = cl.chunk_id
LEFT JOIN article_quality aq ON c.article_id = aq.article_id;

CREATE OR REPLACE VIEW excellent_chunks AS
SELECT 
    c.*,
    cs.score,
    cs.hits,
    aq.excellent as article_excellent
FROM chunks c
JOIN chunk_scores cs ON c.id = cs.chunk_id
JOIN article_quality aq ON c.article_id = aq.article_id
WHERE aq.excellent = TRUE
ORDER BY cs.score DESC;

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON chunks TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON chunk_scores TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON chunk_labels TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON article_quality TO your_app_user;
-- GRANT SELECT ON chunk_analysis TO your_app_user;
-- GRANT SELECT ON excellent_chunks TO your_app_user;
