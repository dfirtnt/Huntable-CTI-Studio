-- =============================================================================
-- Article Deduplication Migration
-- Removes 137 excess rows from 111 duplicate canonical_url groups.
--
-- STRATEGY: per group, keep the article with the lowest id (first ingested).
--   All dependent rows (workflow execs, annotations, evaluations) are
--   re-homed to the keeper before deletion — no history is lost.
--
-- SAFE TO RUN: no cascade drops; all FK rows are explicitly re-homed or
--   cleaned up before the DELETE. Wrap in a transaction and inspect the
--   dry-run SELECT before committing.
--
-- USAGE:
--   psql $DATABASE_URL -f scripts/maintenance/dedup_articles.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Dry run: show what would be kept vs deleted
--    Review this output before proceeding.
-- ---------------------------------------------------------------------------
WITH ranked AS (
    SELECT
        a.id,
        a.canonical_url,
        a.source_id,
        a.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY a.canonical_url
            ORDER BY a.id ASC
        ) AS rn
    FROM articles a
    WHERE a.canonical_url IN (
        SELECT canonical_url FROM articles
        GROUP BY canonical_url
        HAVING COUNT(*) > 1
    )
)
SELECT
    canonical_url,
    id,
    source_id,
    created_at,
    CASE WHEN rn = 1 THEN 'KEEP' ELSE 'DELETE' END AS action
FROM ranked
ORDER BY canonical_url, rn;

-- ---------------------------------------------------------------------------
-- 1. Build a temp table of (dupe_id → keep_id) mappings
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _article_dedup AS
WITH ranked AS (
    SELECT
        a.id,
        a.canonical_url,
        ROW_NUMBER() OVER (
            PARTITION BY a.canonical_url
            ORDER BY a.id ASC
        ) AS rn
    FROM articles a
    WHERE a.canonical_url IN (
        SELECT canonical_url FROM articles
        GROUP BY canonical_url
        HAVING COUNT(*) > 1
    )
),
keepers AS (
    SELECT id AS keep_id, canonical_url FROM ranked WHERE rn = 1
)
SELECT
    r.id     AS dupe_id,
    k.keep_id,
    r.canonical_url
FROM ranked r
JOIN keepers k ON k.canonical_url = r.canonical_url
WHERE r.rn > 1;

-- Sanity check: how many rows will be deleted?
SELECT COUNT(*) AS rows_to_delete FROM _article_dedup;

-- ---------------------------------------------------------------------------
-- 2. Re-home agentic_workflow_executions
-- ---------------------------------------------------------------------------
UPDATE agentic_workflow_executions
SET article_id = d.keep_id
FROM _article_dedup d
WHERE article_id = d.dupe_id;

-- ---------------------------------------------------------------------------
-- 3. Re-home article_annotations
-- ---------------------------------------------------------------------------
UPDATE article_annotations
SET article_id = d.keep_id
FROM _article_dedup d
WHERE article_id = d.dupe_id;

-- ---------------------------------------------------------------------------
-- 4. Re-home subagent_evaluations
-- ---------------------------------------------------------------------------
UPDATE subagent_evaluations
SET article_id = d.keep_id
FROM _article_dedup d
WHERE article_id = d.dupe_id;

-- ---------------------------------------------------------------------------
-- 5. Delete child rows that don't need re-homing (no meaningful state)
-- ---------------------------------------------------------------------------
DELETE FROM chunk_analysis_results
WHERE article_id IN (SELECT dupe_id FROM _article_dedup);

DELETE FROM chunk_classification_feedback
WHERE article_id IN (SELECT dupe_id FROM _article_dedup);

DELETE FROM article_sigma_matches
WHERE article_id IN (SELECT dupe_id FROM _article_dedup);

DELETE FROM simhash_buckets
WHERE article_id IN (SELECT dupe_id FROM _article_dedup);

-- ---------------------------------------------------------------------------
-- 6. Delete the duplicate articles
-- ---------------------------------------------------------------------------
DELETE FROM articles
WHERE id IN (SELECT dupe_id FROM _article_dedup);

-- Verify: should return 0
SELECT COUNT(*) AS remaining_duplicates
FROM articles
GROUP BY canonical_url
HAVING COUNT(*) > 1;

-- ---------------------------------------------------------------------------
-- 7. Prevent recurrence: add a unique index on canonical_url
--    (DROP the index if it already exists, then recreate)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS uq_articles_canonical_url;
CREATE UNIQUE INDEX uq_articles_canonical_url ON articles (canonical_url);

-- ---------------------------------------------------------------------------
-- If everything looks correct, commit. Otherwise ROLLBACK.
-- ---------------------------------------------------------------------------
-- COMMIT;
-- ROLLBACK;
