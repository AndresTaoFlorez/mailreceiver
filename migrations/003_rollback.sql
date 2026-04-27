-- Rollback 003: drop new tables and remove application_code columns from existing tables
-- Run this BEFORE re-executing 003_workload_dispatch.sql

BEGIN;

-- 1. Drop new tables (order matters due to FKs)
DROP TABLE IF EXISTS assignments CASCADE;
DROP TABLE IF EXISTS balance_snapshots CASCADE;
DROP TABLE IF EXISTS work_windows CASCADE;

-- 2. Remove application_code from existing tables
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS fk_conversations_application;
ALTER TABLE conversations DROP COLUMN IF EXISTS application_code;

ALTER TABLE folder_config DROP CONSTRAINT IF EXISTS fk_folder_config_application;
ALTER TABLE folder_config DROP COLUMN IF EXISTS application_code;

ALTER TABLE tickets DROP CONSTRAINT IF EXISTS fk_tickets_application;
ALTER TABLE tickets DROP COLUMN IF EXISTS application_code;

-- 3. Drop applications catalog
DROP TABLE IF EXISTS applications CASCADE;

-- 4. Drop indexes (in case tables were already dropped with CASCADE, these are just safety)
DROP INDEX IF EXISTS idx_assignments_app;
DROP INDEX IF EXISTS idx_assignments_especialist;
DROP INDEX IF EXISTS idx_assignments_conversation;
DROP INDEX IF EXISTS idx_work_windows_app;
DROP INDEX IF EXISTS idx_work_windows_especialist;
DROP INDEX IF EXISTS idx_balance_snapshots_window;

COMMIT;
