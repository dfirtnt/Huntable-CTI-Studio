-- Migration: Fix agent_prompt_versions table schema to match model
-- Date: 2025-01-30
-- Issue: Database columns don't match SQLAlchemy model expectations

-- Drop foreign key constraint first (it references id, but we're storing version numbers)
ALTER TABLE agent_prompt_versions DROP CONSTRAINT IF EXISTS agent_prompt_versions_config_version_id_fkey;

-- Rename columns to match model
ALTER TABLE agent_prompt_versions RENAME COLUMN prompt_text TO prompt;
ALTER TABLE agent_prompt_versions RENAME COLUMN version_number TO version;
ALTER TABLE agent_prompt_versions RENAME COLUMN config_version_id TO workflow_config_version;

-- Add missing instructions column
ALTER TABLE agent_prompt_versions ADD COLUMN IF NOT EXISTS instructions TEXT;

-- Update agent_name column length (model expects 255)
ALTER TABLE agent_prompt_versions ALTER COLUMN agent_name TYPE VARCHAR(255);

-- Drop old indexes with old column names
DROP INDEX IF EXISTS idx_agent_prompt_versions_version_number;
DROP INDEX IF EXISTS idx_agent_prompt_versions_config_version_id;
DROP INDEX IF EXISTS ix_agent_prompt_versions_version_number;
DROP INDEX IF EXISTS ix_agent_prompt_versions_config_version_id;

-- Recreate indexes with correct column names (if they don't already exist)
CREATE INDEX IF NOT EXISTS idx_agent_prompt_versions_version ON agent_prompt_versions(version);
CREATE INDEX IF NOT EXISTS idx_agent_prompt_versions_workflow_config_version ON agent_prompt_versions(workflow_config_version);

-- Note: Foreign key constraint removed because workflow_config_version stores version numbers,
-- not IDs. Foreign keys typically reference primary keys, but version numbers are not unique.

