-- Migration: Add lookback_days field to sources table
-- This migration adds a lookback_days column to the sources table
-- to configure how far back each source should look for articles

-- Add lookback_days column to sources table
ALTER TABLE sources ADD COLUMN lookback_days INTEGER NOT NULL DEFAULT 90;

-- Add constraint to ensure lookback_days is between 1 and 365
ALTER TABLE sources ADD CONSTRAINT check_lookback_days_range 
    CHECK (lookback_days >= 1 AND lookback_days <= 365);

-- Add comment to the column
COMMENT ON COLUMN sources.lookback_days IS 'Lookback window in days for article collection (1-365)';

-- Update existing sources with default lookback window
UPDATE sources SET lookback_days = 90 WHERE lookback_days IS NULL;
