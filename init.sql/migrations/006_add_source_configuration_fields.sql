-- Migration: Add configurable fields to sources table
-- Description: Adds fields for user-configurable polling frequency, lookback window, and last manual poll timestamp

-- Add new columns to sources table
ALTER TABLE sources 
ADD COLUMN IF NOT EXISTS user_polling_frequency INTEGER DEFAULT NULL,
ADD COLUMN IF NOT EXISTS user_lookback_days INTEGER DEFAULT NULL,
ADD COLUMN IF NOT EXISTS last_manual_poll TIMESTAMP DEFAULT NULL,
ADD COLUMN IF NOT EXISTS manual_poll_enabled BOOLEAN DEFAULT TRUE;

-- Add comments for documentation
COMMENT ON COLUMN sources.user_polling_frequency IS 'User-configured polling frequency in seconds (overrides check_frequency)';
COMMENT ON COLUMN sources.user_lookback_days IS 'User-configured lookback window in days (overrides default collection period)';
COMMENT ON COLUMN sources.last_manual_poll IS 'Timestamp of last manual poll triggered by user';
COMMENT ON COLUMN sources.manual_poll_enabled IS 'Whether manual polling is enabled for this source';

-- Create index for efficient querying of sources needing manual polls
CREATE INDEX IF NOT EXISTS idx_sources_manual_poll ON sources(manual_poll_enabled, last_manual_poll) WHERE manual_poll_enabled = TRUE;

-- Update existing sources to have default values
UPDATE sources 
SET user_polling_frequency = check_frequency,
    user_lookback_days = 90,
    manual_poll_enabled = TRUE
WHERE user_polling_frequency IS NULL;
