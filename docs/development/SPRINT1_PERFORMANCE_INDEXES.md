# Sprint 1 Performance Optimization: Database Indexes

## Overview

This document describes the database performance optimization implemented in Sprint 1, focusing on critical indexes for search, deduplication, and temporal queries.

## Indexes Implemented

### 1. Full-Text Search Index (GIN)

**Index**: `idx_articles_content_gin`  
**Type**: GIN (Generalized Inverted Index)  
**Purpose**: Enables fast full-text search across article content

```sql
CREATE INDEX CONCURRENTLY idx_articles_content_gin 
ON articles USING gin(to_tsvector('english', content));
```

**Query Pattern**:
```sql
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', 'search_term')
```

**Performance**: ~2ms for complex text searches  
**Size**: 5.8MB (442% of table size - expected for GIN indexes)

### 2. Deduplication Index (Composite BTree)

**Index**: `idx_articles_url_hash_btree`  
**Type**: Composite BTree  
**Purpose**: Optimizes deduplication queries

```sql
CREATE INDEX CONCURRENTLY idx_articles_url_hash_btree 
ON articles USING btree (canonical_url, content_hash);
```

**Query Pattern**:
```sql
WHERE canonical_url = ? AND content_hash = ?
```

**Performance**: ~0.7ms for deduplication checks  
**Size**: 176KB (13% of table size)

### 3. Temporal Query Index (BTree)

**Index**: `ix_articles_published_at` (existing)  
**Type**: BTree  
**Purpose**: Optimizes temporal queries and sorting

**Query Pattern**:
```sql
WHERE published_at > ? ORDER BY published_at DESC
```

**Performance**: ~0.4ms for temporal queries  
**Size**: Optimized for date range queries

### 4. Source-based Query Index (Composite BTree)

**Index**: `idx_articles_source_published_btree`  
**Type**: Composite BTree  
**Purpose**: Optimizes source-based queries with temporal ordering

```sql
CREATE INDEX CONCURRENTLY idx_articles_source_published_btree 
ON articles USING btree (source_id, published_at DESC);
```

**Query Pattern**:
```sql
WHERE source_id = ? ORDER BY published_at DESC
```

**Performance**: ~0.03s for source queries  
**Size**: 48KB (3.6% of table size)

### 5. Processing Status Index (Composite BTree)

**Index**: `idx_articles_status_discovered_btree`  
**Type**: Composite BTree  
**Purpose**: Optimizes processing status queries

```sql
CREATE INDEX CONCURRENTLY idx_articles_status_discovered_btree 
ON articles USING btree (processing_status, discovered_at ASC);
```

**Query Pattern**:
```sql
WHERE processing_status = ? ORDER BY discovered_at ASC
```

**Performance**: Optimized for status-based filtering  
**Size**: 48KB (3.6% of table size)

### 6. Quality Score Index (Partial BTree)

**Index**: `idx_articles_quality_score_btree`  
**Type**: Partial BTree (only non-null values)  
**Purpose**: Optimizes quality-based queries

```sql
CREATE INDEX CONCURRENTLY idx_articles_quality_score_btree 
ON articles USING btree (quality_score DESC) 
WHERE quality_score IS NOT NULL;
```

**Query Pattern**:
```sql
WHERE quality_score > ? ORDER BY quality_score DESC
```

**Performance**: Optimized for quality filtering  
**Size**: 8KB (0.6% of table size)

### 7. Metadata Training Category Index (BTree)

**Index**: `idx_articles_metadata_training_category_btree`  
**Type**: BTree  
**Purpose**: Optimizes training category queries

```sql
CREATE INDEX CONCURRENTLY idx_articles_metadata_training_category_btree 
ON articles USING btree ((article_metadata->>'training_category'));
```

**Query Pattern**:
```sql
WHERE article_metadata->>'training_category' = ?
```

**Performance**: ~0.025s for metadata queries  
**Size**: 16KB (1.2% of table size)

### 8. Threat Hunting Score Index (Partial BTree)

**Index**: `idx_articles_metadata_threat_score_btree`  
**Type**: Partial BTree (only non-null values)  
**Purpose**: Optimizes threat hunting score queries

```sql
CREATE INDEX CONCURRENTLY idx_articles_metadata_threat_score_btree 
ON articles USING btree (((article_metadata->>'threat_hunting_score')::int)) 
WHERE article_metadata->>'threat_hunting_score' IS NOT NULL;
```

**Query Pattern**:
```sql
WHERE (article_metadata->>'threat_hunting_score')::int > ?
```

**Performance**: Optimized for threat score filtering  
**Size**: Minimal (only non-null values indexed)

## Performance Analysis

### Database-Level Performance Tests

| Test Type | Query Time | Rows Returned | Index Used |
|-----------|------------|---------------|------------|
| Full-text search | 1.973ms | 356 | idx_articles_content_gin |
| Deduplication | 0.653ms | 0 | idx_articles_url_hash_btree |
| Temporal query | 0.447ms | 100 | ix_articles_published_at |

### Application-Level Performance Tests

| Test Type | Query Time | Articles Returned | Index Used |
|-----------|------------|-------------------|------------|
| Temporal query | 84ms | 100 | ix_articles_published_at |
| Source query | 29ms | 50 | idx_articles_source_published_btree |
| Metadata query | 25ms | 50 | idx_articles_metadata_training_category_btree |

## Index Size Analysis

| Index Name | Type | Size | Table Ratio |
|------------|------|------|-------------|
| idx_articles_content_gin | GIN | 5.8MB | 442% |
| idx_articles_url_hash_btree | BTree | 176KB | 13% |
| idx_articles_simhash | BTree | 56KB | 4% |
| idx_articles_status_discovered_btree | BTree | 48KB | 4% |
| idx_articles_source_published_btree | BTree | 48KB | 4% |
| idx_articles_simhash_bucket | BTree | 16KB | 1% |
| idx_articles_metadata_training_category_btree | BTree | 16KB | 1% |
| idx_articles_quality_score_btree | BTree | 8KB | 1% |
| idx_articles_metadata_threat_score_btree | BTree | 0KB | 0% |

## Migration Details

### File Location
- **Migration Script**: `init.sql/migrations/003_sprint1_performance_indexes.sql`
- **Applied**: 2025-09-04
- **Status**: ✅ Complete

### Migration Features
- **CONCURRENTLY**: All indexes created without locking the table
- **IF NOT EXISTS**: Safe to re-run migration
- **Performance Functions**: Built-in testing and analysis functions
- **Documentation**: Comprehensive comments and documentation

### Performance Analysis Functions

#### `test_index_performance()`
Tests the performance of key indexes with realistic queries.

#### `get_index_stats()`
Provides detailed statistics about index sizes and ratios.

#### `analyze_index_usage()`
Analyzes index usage patterns (requires PostgreSQL statistics).

## Query Optimization Patterns

### 1. Full-Text Search
```sql
-- Optimized with GIN index
SELECT * FROM articles 
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', 'malware attack')
ORDER BY published_at DESC;
```

### 2. Deduplication
```sql
-- Optimized with composite BTree index
SELECT COUNT(*) FROM articles 
WHERE canonical_url = ? AND content_hash = ?;
```

### 3. Temporal Queries
```sql
-- Optimized with BTree index
SELECT * FROM articles 
WHERE published_at > '2024-01-01'::timestamp 
ORDER BY published_at DESC 
LIMIT 100;
```

### 4. Source-based Queries
```sql
-- Optimized with composite BTree index
SELECT * FROM articles 
WHERE source_id = ? 
ORDER BY published_at DESC 
LIMIT 50;
```

### 5. Metadata Queries
```sql
-- Optimized with BTree index on JSONB
SELECT * FROM articles 
WHERE article_metadata->>'training_category' = 'chosen'
ORDER BY published_at DESC;
```

## Benefits

### Performance Improvements
- **Full-text search**: 2ms response time for complex searches
- **Deduplication**: 0.7ms for duplicate detection
- **Temporal queries**: 0.4ms for date-based filtering
- **Source queries**: 29ms for source-based filtering
- **Metadata queries**: 25ms for JSONB key-value lookups

### Scalability Benefits
- **Concurrent Creation**: Indexes created without table locks
- **Partial Indexes**: Reduced storage for sparse data
- **Composite Indexes**: Optimized for multi-column queries
- **GIN Indexes**: Efficient for full-text search

### Maintenance Benefits
- **Self-Documenting**: Comprehensive comments and documentation
- **Performance Monitoring**: Built-in analysis functions
- **Migration Tracking**: Automatic migration logging
- **Safe Re-runs**: Idempotent migration scripts

## Future Considerations

### Monitoring
- Regular index usage analysis
- Performance trend monitoring
- Storage growth tracking

### Optimization Opportunities
- Additional composite indexes for common query patterns
- Partial indexes for frequently filtered columns
- Expression indexes for computed values

### Maintenance
- Regular VACUUM and ANALYZE operations
- Index bloat monitoring
- Query plan analysis

## Conclusion

The Sprint 1 performance optimization successfully implements critical database indexes that provide:

✅ **Fast full-text search** with GIN indexes  
✅ **Efficient deduplication** with composite BTree indexes  
✅ **Optimized temporal queries** with BTree indexes  
✅ **Improved source-based queries** with composite indexes  
✅ **Fast metadata queries** with JSONB indexes  
✅ **Comprehensive monitoring** with analysis functions  

All indexes are production-ready, well-documented, and provide significant performance improvements for the CTIScraper application.
