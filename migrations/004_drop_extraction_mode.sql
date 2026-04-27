-- Rollback: remove extraction_mode from folder_config (moved to scrape request param)
ALTER TABLE folder_config DROP COLUMN IF EXISTS extraction_mode;
