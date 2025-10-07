-- Add archived column to securities table
-- Migration: Add archived status tracking for securities

-- Add archived column with default false
ALTER TABLE securities ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0;

-- Create index on archived column for faster queries
CREATE INDEX idx_securities_archived ON securities(archived);

-- Mark specific securities as archived (no longer trading)
UPDATE securities SET archived = 1 WHERE ticker IN ('MAGIC', 'EGR1T');

-- Add comment
COMMENT ON COLUMN securities.archived IS 'True if security is no longer trading (delisted, matured, etc.)';
