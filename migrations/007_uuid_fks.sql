-- Migration 007: Replace string-based especialist FKs with UUID FKs
-- and rename assignments.conversation_id → thread_id (avoids clash with conversations.conversation_id)
--
-- Affected tables: assignments, work_windows, balance_snapshots, specialist_folders

BEGIN;

-- ============================================================
-- 1. assignments: rename conversation_id → thread_id
-- ============================================================
ALTER TABLE assignments RENAME COLUMN conversation_id TO thread_id;

-- ============================================================
-- 2. assignments: especialist_code (varchar FK) → especialist_id (uuid FK)
-- ============================================================
ALTER TABLE assignments ADD COLUMN especialist_id uuid;

UPDATE assignments a
SET especialist_id = e.id
FROM especialist e
WHERE e.code = a.especialist_code;

-- Fail loudly if any row couldn't be matched
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM assignments WHERE especialist_id IS NULL) THEN
        RAISE EXCEPTION 'assignments: found rows with no matching especialist — aborting';
    END IF;
END $$;

ALTER TABLE assignments ALTER COLUMN especialist_id SET NOT NULL;
ALTER TABLE assignments ADD CONSTRAINT fk_assignments_especialist_id
    FOREIGN KEY (especialist_id) REFERENCES especialist(id);
ALTER TABLE assignments DROP COLUMN especialist_code;

-- ============================================================
-- 3. work_windows: especialist_code → especialist_id
-- ============================================================
ALTER TABLE work_windows ADD COLUMN especialist_id uuid;

UPDATE work_windows w
SET especialist_id = e.id
FROM especialist e
WHERE e.code = w.especialist_code;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM work_windows WHERE especialist_id IS NULL) THEN
        RAISE EXCEPTION 'work_windows: found rows with no matching especialist — aborting';
    END IF;
END $$;

ALTER TABLE work_windows ALTER COLUMN especialist_id SET NOT NULL;
ALTER TABLE work_windows ADD CONSTRAINT fk_work_windows_especialist_id
    FOREIGN KEY (especialist_id) REFERENCES especialist(id);
ALTER TABLE work_windows DROP COLUMN especialist_code;

-- ============================================================
-- 4. balance_snapshots: especialist_code → especialist_id
-- ============================================================
ALTER TABLE balance_snapshots ADD COLUMN especialist_id uuid;

UPDATE balance_snapshots b
SET especialist_id = e.id
FROM especialist e
WHERE e.code = b.especialist_code;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM balance_snapshots WHERE especialist_id IS NULL) THEN
        RAISE EXCEPTION 'balance_snapshots: found rows with no matching especialist — aborting';
    END IF;
END $$;

ALTER TABLE balance_snapshots ALTER COLUMN especialist_id SET NOT NULL;
ALTER TABLE balance_snapshots ADD CONSTRAINT fk_balance_snapshots_especialist_id
    FOREIGN KEY (especialist_id) REFERENCES especialist(id);
ALTER TABLE balance_snapshots DROP COLUMN especialist_code;

-- ============================================================
-- 5. specialist_folders: especialist_code → especialist_id
-- ============================================================
ALTER TABLE specialist_folders ADD COLUMN especialist_id uuid;

UPDATE specialist_folders sf
SET especialist_id = e.id
FROM especialist e
WHERE e.code = sf.especialist_code;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM specialist_folders WHERE especialist_id IS NULL) THEN
        RAISE EXCEPTION 'specialist_folders: found rows with no matching especialist — aborting';
    END IF;
END $$;

ALTER TABLE specialist_folders ALTER COLUMN especialist_id SET NOT NULL;
ALTER TABLE specialist_folders ADD CONSTRAINT fk_specialist_folders_especialist_id
    FOREIGN KEY (especialist_id) REFERENCES especialist(id);

-- Drop old unique constraint that includes especialist_code, recreate with especialist_id
ALTER TABLE specialist_folders DROP CONSTRAINT uq_app_specialist;
ALTER TABLE specialist_folders ADD CONSTRAINT uq_app_specialist
    UNIQUE (application_code, especialist_id);
ALTER TABLE specialist_folders DROP COLUMN especialist_code;

COMMIT;
