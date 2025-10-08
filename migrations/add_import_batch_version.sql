-- Migration: Add version column to import_batches for optimistic locking
-- Date: 2025-01-08
-- Purpose: Prevent race conditions during concurrent import operations
--
-- This migration adds a `version` column to the import_batches table
-- to support optimistic locking. SQLAlchemy will automatically increment
-- this column on each UPDATE, preventing concurrent modifications.

-- Add version column with default value 0
ALTER TABLE import_batches ADD COLUMN version INTEGER NOT NULL DEFAULT 0;

-- Update existing rows to have version = 0
UPDATE import_batches SET version = 0 WHERE version IS NULL;

-- Note: SQLite does not support COMMENT ON COLUMN
-- Version number for optimistic locking - prevents concurrent modification conflicts
