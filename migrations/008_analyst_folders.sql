-- Migration 008: Merge specialist_folders into folder_config
-- Adds especialist_id (nullable) to folder_config so the table holds both
-- level folders (especialist_id IS NULL) and analyst folders (especialist_id NOT NULL).
-- Then migrates existing specialist_folders rows and drops that table.

BEGIN;

-- 1. Add especialist_id column
ALTER TABLE folder_config
    ADD COLUMN IF NOT EXISTS especialist_id uuid REFERENCES especialist(id);

-- 2. Make level nullable (analyst folders have no level)
ALTER TABLE folder_config
    ALTER COLUMN level DROP NOT NULL;

-- 3. Drop the old (folder_name, application) unique constraint
ALTER TABLE folder_config
    DROP CONSTRAINT IF EXISTS uq_folder_app;

-- 4. Partial unique index: one analyst folder per specialist per app
CREATE UNIQUE INDEX IF NOT EXISTS uq_folder_analyst
    ON folder_config (application_code, especialist_id)
    WHERE especialist_id IS NOT NULL;

-- 5. Partial unique index: unique folder name per app (level folders only)
CREATE UNIQUE INDEX IF NOT EXISTS uq_folder_level
    ON folder_config (folder_name, application)
    WHERE especialist_id IS NULL;

-- 6. Migrate specialist_folders rows into folder_config (only if table still exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'specialist_folders') THEN
        INSERT INTO folder_config (id, folder_name, level, application, application_code, especialist_id, active, created_at)
        SELECT
            gen_random_uuid(),
            sf.folder_name,
            NULL,
            sf.application_code,
            sf.application_code,
            sf.especialist_id,
            sf.active,
            sf.created_at
        FROM specialist_folders sf
        ON CONFLICT DO NOTHING;
    END IF;
END $$;

-- 7. Drop specialist_folders (data is now in folder_config)
DROP TABLE IF EXISTS specialist_folders;

COMMIT;
