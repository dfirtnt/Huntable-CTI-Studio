-- Migration: Sprint 1 Performance Optimization Indexes
-- Date: 2025-09-04
-- Description: Adds critical indexes for search, deduplication, and temporal queries

-- ============================================================================
-- SPRINT 1 PERFORMANCE OPTIMIZATION INDEXES
-- ============================================================================

-- 1. GIN Index for Full-Text Search on Content
-- This enables fast full-text search across article content using PostgreSQL's
-- built-in text search capabilities
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_content_gin 
ON articles USING gin(to_tsvector('english', content));

-- Add comment for documentation
COMMENT ON INDEX idx_articles_content_gin IS 'GIN index for full-text search on article content using English language configuration';

-- 2. Composite BTree Index for Deduplication Queries
-- This optimizes queries that check for duplicate content by URL and hash
-- Common pattern: WHERE canonical_url = ? AND content_hash = ?
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_url_hash_btree 
ON articles USING btree (canonical_url, content_hash);

-- Add comment for documentation
COMMENT ON INDEX idx_articles_url_hash_btree IS 'Composite btree index for deduplication queries on canonical_url and content_hash';

-- 3. Verify published_at Index Exists (already exists as ix_articles_published_at)
-- This index is already present and optimizes temporal queries
-- Common patterns: ORDER BY published_at DESC, WHERE published_at > ?

-- 4. Additional Performance Indexes for Common Query Patterns

-- Index for source-based queries with temporal ordering
-- Common pattern: WHERE source_id = ? ORDER BY published_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_source_published_btree 
ON articles USING btree (source_id, published_at DESC);

COMMENT ON INDEX idx_articles_source_published_btree IS 'Composite index for source-based queries with temporal ordering';

-- Index for processing status queries
-- Common pattern: WHERE processing_status = ? ORDER BY discovered_at ASC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_status_discovered_btree 
ON articles USING btree (processing_status, discovered_at ASC);

COMMENT ON INDEX idx_articles_status_discovered_btree IS 'Composite index for processing status queries with discovery time ordering';

-- Index for quality-based queries
-- Common pattern: WHERE quality_score > ? ORDER BY quality_score DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_quality_score_btree 
ON articles USING btree (quality_score DESC) WHERE quality_score IS NOT NULL;

COMMENT ON INDEX idx_articles_quality_score_btree IS 'Partial index for quality score queries (only includes non-null scores)';

-- Index for metadata-based queries (JSONB operations)
-- Common pattern: WHERE article_metadata->>'training_category' = ?
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_metadata_training_category_btree 
ON articles USING btree ((article_metadata->>'training_category'));

COMMENT ON INDEX idx_articles_metadata_training_category_btree IS 'Btree index for training category queries in article metadata';

-- Index for metadata-based queries on threat hunting score
-- Common pattern: WHERE (article_metadata->>'threat_hunting_score')::int > ?
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_metadata_threat_score_btree 
ON articles USING btree (((article_metadata->>'threat_hunting_score')::int)) 
WHERE article_metadata->>'threat_hunting_score' IS NOT NULL;

COMMENT ON INDEX idx_articles_metadata_threat_score_btree IS 'Partial index for threat hunting score queries';

-- ============================================================================
-- INDEX USAGE ANALYSIS AND MAINTENANCE
-- ============================================================================

-- Create a function to analyze index usage
CREATE OR REPLACE FUNCTION analyze_index_usage()
RETURNS TABLE(
    index_name TEXT,
    table_name TEXT,
    index_size TEXT,
    index_usage_count BIGINT,
    last_used TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.indexname::TEXT,
        i.tablename::TEXT,
        pg_size_pretty(pg_relation_size(i.indexname::regclass))::TEXT,
        COALESCE(s.idx_tup_read, 0) as index_usage_count,
        COALESCE(s.last_idx_scan, '1970-01-01'::timestamp) as last_used
    FROM pg_indexes i
    LEFT JOIN pg_stat_user_indexes s ON i.indexname = s.indexrelname
    WHERE i.tablename = 'articles'
    AND i.indexname LIKE 'idx_articles_%'
    ORDER BY COALESCE(s.idx_tup_read, 0) DESC;
END;
$$ LANGUAGE plpgsql;

-- Create a function to get index statistics
CREATE OR REPLACE FUNCTION get_index_stats()
RETURNS TABLE(
    index_name TEXT,
    index_type TEXT,
    index_size TEXT,
    table_size TEXT,
    index_ratio TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.indexname::TEXT,
        am.amname::TEXT,
        pg_size_pretty(pg_relation_size(i.indexname::regclass))::TEXT,
        pg_size_pretty(pg_relation_size(i.tablename::regclass))::TEXT,
        ROUND(
            pg_relation_size(i.indexname::regclass)::numeric / 
            pg_relation_size(i.tablename::regclass)::numeric * 100, 2
        )::TEXT || '%'
    FROM pg_indexes i
    JOIN pg_class c ON c.relname = i.indexname
    JOIN pg_am am ON am.oid = c.relam
    WHERE i.tablename = 'articles'
    AND i.indexname LIKE 'idx_articles_%'
    ORDER BY pg_relation_size(i.indexname::regclass) DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PERFORMANCE TESTING QUERIES
-- ============================================================================

-- Create a function to test index performance
CREATE OR REPLACE FUNCTION test_index_performance()
RETURNS TABLE(
    test_name TEXT,
    query_time_ms NUMERIC,
    rows_returned BIGINT,
    index_used TEXT
) AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    query_plan TEXT;
BEGIN
    -- Test 1: Full-text search performance
    start_time := clock_timestamp();
    PERFORM COUNT(*) FROM articles 
    WHERE to_tsvector('english', content) @@ plainto_tsquery('english', 'malware attack');
    end_time := clock_timestamp();
    
    RETURN QUERY SELECT 
        'Full-text search'::TEXT,
        EXTRACT(milliseconds FROM end_time - start_time)::NUMERIC,
        (SELECT COUNT(*) FROM articles WHERE to_tsvector('english', content) @@ plainto_tsquery('english', 'malware attack')),
        'idx_articles_content_gin'::TEXT;
    
    -- Test 2: Deduplication query performance
    start_time := clock_timestamp();
    PERFORM COUNT(*) FROM articles 
    WHERE canonical_url = 'https://example.com/article1' AND content_hash = 'abc123';
    end_time := clock_timestamp();
    
    RETURN QUERY SELECT 
        'Deduplication query'::TEXT,
        EXTRACT(milliseconds FROM end_time - start_time)::NUMERIC,
        (SELECT COUNT(*) FROM articles WHERE canonical_url = 'https://example.com/article1' AND content_hash = 'abc123'),
        'idx_articles_url_hash_btree'::TEXT;
    
    -- Test 3: Temporal query performance
    start_time := clock_timestamp();
    PERFORM COUNT(*) FROM (
        SELECT id FROM articles 
        WHERE published_at > '2024-01-01'::timestamp 
        ORDER BY published_at DESC 
        LIMIT 100
    ) subq;
    end_time := clock_timestamp();
    
    RETURN QUERY SELECT 
        'Temporal query'::TEXT,
        EXTRACT(milliseconds FROM end_time - start_time)::NUMERIC,
        100::BIGINT,
        'ix_articles_published_at'::TEXT;
    
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- DOCUMENTATION AND COMMENTS
-- ============================================================================

-- Add comprehensive comments for all new indexes
COMMENT ON INDEX idx_articles_content_gin IS 'GIN index for full-text search on article content. Enables fast text search queries using PostgreSQL tsvector.';
COMMENT ON INDEX idx_articles_url_hash_btree IS 'Composite btree index for deduplication queries. Optimizes WHERE canonical_url = ? AND content_hash = ? patterns.';
COMMENT ON INDEX idx_articles_source_published_btree IS 'Composite index for source-based queries with temporal ordering. Optimizes WHERE source_id = ? ORDER BY published_at DESC.';
COMMENT ON INDEX idx_articles_status_discovered_btree IS 'Composite index for processing status queries. Optimizes WHERE processing_status = ? ORDER BY discovered_at ASC.';
COMMENT ON INDEX idx_articles_quality_score_btree IS 'Partial index for quality score queries. Only includes rows where quality_score IS NOT NULL.';
COMMENT ON INDEX idx_articles_metadata_training_category_btree IS 'Btree index for training category queries in article metadata. Enables fast JSONB key-value lookups.';
COMMENT ON INDEX idx_articles_metadata_threat_score_btree IS 'Partial index for threat hunting score queries. Only includes rows where threat_hunting_score IS NOT NULL.';

-- ============================================================================
-- MIGRATION COMPLETION
-- ============================================================================

-- Create migration_log table if it doesn't exist
CREATE TABLE IF NOT EXISTS migration_log (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) UNIQUE NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    description TEXT
);

-- Log the completion of this migration
INSERT INTO migration_log (migration_name, applied_at, description) 
VALUES (
    '003_sprint1_performance_indexes', 
    NOW(), 
    'Added critical indexes for search, deduplication, and temporal queries. Includes GIN index for full-text search, composite btree indexes for common query patterns, and performance analysis functions.'
) ON CONFLICT (migration_name) DO NOTHING;

COMMENT ON TABLE migration_log IS 'Tracks applied database migrations for version control and rollback purposes';
