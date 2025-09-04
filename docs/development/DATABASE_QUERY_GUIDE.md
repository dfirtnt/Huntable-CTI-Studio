# Database Query Instructions

This document provides instructions for directly querying the CTI Scraper database using PostgreSQL commands.

## Prerequisites

- Docker and Docker Compose installed
- CTI Scraper application running (`docker-compose up -d`)

## Database Connection Details

- **Host**: `localhost` (or `postgres` from within containers)
- **Port**: `5432`
- **Database**: `cti_scraper`
- **Username**: `cti_user`
- **Password**: `cti_password_2024`

## Connecting to the Database

### From Host Machine

```bash
# Connect using docker exec
docker exec cti_postgres psql -U cti_user -d cti_scraper

# Run a single query
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "YOUR_QUERY_HERE"
```

### From Within a Container

```bash
# Connect to the web container
docker exec -it cti_web bash

# Then connect to PostgreSQL
psql postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper
```

## Common Queries

### View All Sources

```sql
-- All sources with their details
SELECT id, name, url, rss_url, active, created_at
FROM sources
ORDER BY name;

-- Only active sources
SELECT name, url, rss_url, tier 
FROM sources 
WHERE active = true 
ORDER BY name;
```

### View Articles

```sql
-- Recent articles with source information
SELECT 
    a.id,
    a.title,
    s.name as source_name,
    a.published_at,
    a.created_at,
    CASE 
        WHEN a.metadata->>'training_category' = 'chosen' THEN '✅ Chosen'
        WHEN a.metadata->>'training_category' = 'rejected' THEN '❌ Rejected'
        ELSE '⏳ Unclassified'
    END as classification
FROM articles a
JOIN sources s ON a.source_id = s.id
ORDER BY a.created_at DESC
LIMIT 20;

-- Articles by source
SELECT 
    s.name as source_name,
    COUNT(*) as article_count,
    COUNT(CASE WHEN a.metadata->>'training_category' = 'chosen' THEN 1 END) as chosen_count,
    COUNT(CASE WHEN a.metadata->>'training_category' = 'rejected' THEN 1 END) as rejected_count,
    COUNT(CASE WHEN a.metadata->>'training_category' IS NULL THEN 1 END) as unclassified_count
FROM articles a
JOIN sources s ON a.source_id = s.id
GROUP BY s.id, s.name
ORDER BY article_count DESC;
```

### Search Articles

```sql
-- Search articles by title or content
SELECT 
    a.id,
    a.title,
    s.name as source_name,
    a.published_at
FROM articles a
JOIN sources s ON a.source_id = s.id
WHERE 
    a.title ILIKE '%malware%' OR 
    a.content ILIKE '%malware%'
ORDER BY a.published_at DESC
LIMIT 10;

-- Articles from specific sources
SELECT 
    a.id,
    a.title,
    a.published_at
FROM articles a
JOIN sources s ON a.source_id = s.id
WHERE s.name IN ('Cisco Talos Intelligence Blog', 'Mandiant Threat Research')
ORDER BY a.published_at DESC;
```

### Database Statistics

```sql
-- Overall statistics
SELECT 
    COUNT(*) as total_articles,
    COUNT(DISTINCT source_id) as total_sources,
    COUNT(CASE WHEN metadata->>'training_category' = 'chosen' THEN 1 END) as chosen_articles,
    COUNT(CASE WHEN metadata->>'training_category' = 'rejected' THEN 1 END) as rejected_articles,
    COUNT(CASE WHEN metadata->>'training_category' IS NULL THEN 1 END) as unclassified_articles
FROM articles;

-- Articles by date (last 30 days)
SELECT 
    DATE(created_at) as date,
    COUNT(*) as articles_added
FROM articles
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Source Management

```sql
-- Add a new source
INSERT INTO sources (id, name, url, rss_url, check_frequency, active, created_at, updated_at)
VALUES (
    'new_source_id',
    'New Source Name',
    'https://example.com',
    'https://example.com/feed/',
    2,
    1.0,
    1800,
    true,
    NOW(),
    NOW()
);

-- Update source status
UPDATE sources 
SET active = false, updated_at = NOW()
WHERE id = 'source_id_to_disable';

-- View source collection statistics
SELECT 
    s.name,
    COUNT(a.id) as total_articles,
    MAX(a.created_at) as last_article_date,
    s.active
FROM sources s
LEFT JOIN articles a ON s.id = a.source_id
GROUP BY s.id, s.name, s.active
ORDER BY total_articles DESC;
```

## Advanced Queries

### Content Analysis

```sql
-- Articles with specific content patterns
SELECT 
    a.id,
    a.title,
    s.name as source_name,
    LENGTH(a.content) as content_length,
    a.published_at
FROM articles a
JOIN sources s ON a.source_id = s.id
WHERE 
    a.content ILIKE '%ransomware%' AND
    a.content ILIKE '%critical infrastructure%'
ORDER BY a.published_at DESC;

-- Duplicate detection (similar titles)
SELECT 
    a1.id as id1,
    a1.title as title1,
    a2.id as id2,
    a2.title as title2,
    s1.name as source1,
    s2.name as source2
FROM articles a1
JOIN articles a2 ON a1.id < a2.id
JOIN sources s1 ON a1.source_id = s1.id
JOIN sources s2 ON a2.source_id = s2.id
WHERE 
    a1.title ILIKE a2.title OR
    SIMILARITY(a1.title, a2.title) > 0.8
ORDER BY SIMILARITY(a1.title, a2.title) DESC;
```

### Export Data

```sql
-- Export articles to CSV format
\copy (
    SELECT 
        a.id,
        a.title,
        s.name as source_name,
        a.canonical_url,
        a.published_at,
        a.created_at,
        a.metadata->>'training_category' as classification
    FROM articles a
    JOIN sources s ON a.source_id = s.id
    ORDER BY a.created_at DESC
) TO '/tmp/articles_export.csv' WITH CSV HEADER;

-- Export sources to CSV
\copy (
    SELECT 
        id,
        name,
        url,
        rss_url,
        active,
        created_at
    FROM sources
    ORDER BY name
) TO '/tmp/sources_export.csv' WITH CSV HEADER;
```

## Database Schema

### Main Tables

#### `sources`
- `id`: Primary key (string)
- `name`: Source name
- `url`: Main website URL
- `rss_url`: RSS feed URL
- `check_frequency`: How often to check this source (seconds)
- `active`: Whether source is active
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

#### `articles`
- `id`: Primary key (integer)
- `title`: Article title
- `content`: Article content
- `source_id`: Foreign key to sources
- `canonical_url`: Original article URL
- `published_at`: Publication date
- `created_at`: Collection timestamp
- `updated_at`: Last update timestamp
- `metadata`: JSON field with additional data

### Useful Views

```sql
-- Create a view for article statistics
CREATE VIEW article_stats AS
SELECT 
    s.name as source_name,
    COUNT(a.id) as total_articles,
    COUNT(CASE WHEN a.metadata->>'training_category' = 'chosen' THEN 1 END) as chosen_count,
    COUNT(CASE WHEN a.metadata->>'training_category' = 'rejected' THEN 1 END) as rejected_count,
    MAX(a.created_at) as last_collection
FROM sources s
LEFT JOIN articles a ON s.id = a.source_id
GROUP BY s.id, s.name;

-- Query the view
SELECT * FROM article_stats ORDER BY total_articles DESC;
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Ensure Docker containers are running
   ```bash
   docker-compose ps
   ```

2. **Permission Denied**: Use correct database credentials
   ```bash
   docker exec cti_postgres psql -U cti_user -d cti_scraper
   ```

3. **Table Not Found**: Check if database is initialized
   ```sql
   \dt  -- List all tables
   ```

### Performance Tips

- Use indexes for frequently queried columns
- Limit result sets with `LIMIT` clause
- Use `EXPLAIN ANALYZE` to analyze query performance
- Consider creating materialized views for complex aggregations

## Backup and Restore

```bash
# Create database backup
docker exec cti_postgres pg_dump -U cti_user cti_scraper > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
docker exec -i cti_postgres psql -U cti_user cti_scraper < backup_file.sql
```

## Security Notes

- Database credentials are stored in environment variables
- Access is limited to local connections by default
- Consider using connection pooling for production deployments
- Regularly rotate database passwords
- Monitor database access logs
