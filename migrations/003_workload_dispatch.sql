-- Migration 003: Workload Dispatch System
-- Tables: applications, work_windows, balance_snapshots, assignments
-- FK adjustments on: conversations, folder_config, tickets

BEGIN;

DROP TABLE IF EXISTS assignments CASCADE;
DROP TABLE IF EXISTS balance_snapshots CASCADE;
DROP TABLE IF EXISTS work_windows CASCADE;

-- 1. applications — central catalog
CREATE TABLE IF NOT EXISTS applications (
    code         VARCHAR(50) PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    description  TEXT,
    active       BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed existing apps from conversations so FK migration doesn't fail
INSERT INTO applications (code, name)
SELECT DISTINCT app, app FROM conversations
ON CONFLICT (code) DO NOTHING;

-- Also seed from folder_config
INSERT INTO applications (code, name)
SELECT DISTINCT application, application FROM folder_config
ON CONFLICT (code) DO NOTHING;

-- Also seed from tickets
INSERT INTO applications (code, name)
SELECT DISTINCT application, application FROM tickets
ON CONFLICT (code) DO NOTHING;

-- 2. Add application_code FK to conversations
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS application_code VARCHAR(50);

UPDATE conversations SET application_code = app WHERE application_code IS NULL;

ALTER TABLE conversations
    ALTER COLUMN application_code SET NOT NULL;

ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_application
    FOREIGN KEY (application_code) REFERENCES applications(code);

-- 3. Add application_code FK to folder_config
ALTER TABLE folder_config
    ADD COLUMN IF NOT EXISTS application_code VARCHAR(50);

UPDATE folder_config SET application_code = application WHERE application_code IS NULL;

ALTER TABLE folder_config
    ALTER COLUMN application_code SET NOT NULL;

ALTER TABLE folder_config
    ADD CONSTRAINT fk_folder_config_application
    FOREIGN KEY (application_code) REFERENCES applications(code);

-- 4. Add application_code FK to tickets
ALTER TABLE tickets
    ADD COLUMN IF NOT EXISTS application_code VARCHAR(50);

UPDATE tickets SET application_code = application WHERE application_code IS NULL;

ALTER TABLE tickets
    ALTER COLUMN application_code SET NOT NULL;

ALTER TABLE tickets
    ADD CONSTRAINT fk_tickets_application
    FOREIGN KEY (application_code) REFERENCES applications(code);

-- 5. work_windows
CREATE TABLE IF NOT EXISTS work_windows (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    especialist_code    VARCHAR(20) NOT NULL REFERENCES especialist(code),
    application_code    VARCHAR(50) NOT NULL REFERENCES applications(code),
    load_percentage     INTEGER,
    schedule            JSONB NOT NULL,
    active              BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. balance_snapshots
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    especialist_code    VARCHAR(20) NOT NULL REFERENCES especialist(code),
    application_code    VARCHAR(50) NOT NULL REFERENCES applications(code),
    work_window_id      UUID NOT NULL REFERENCES work_windows(id),
    cases_assigned      INTEGER NOT NULL DEFAULT 0,
    expected_cases      NUMERIC(10,2) NOT NULL DEFAULT 0,
    balance             NUMERIC(10,2) NOT NULL DEFAULT 0,
    last_reset_at       TIMESTAMPTZ,
    inherited_from      UUID REFERENCES balance_snapshots(id),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 7. assignments
CREATE TABLE IF NOT EXISTS assignments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id),
    especialist_code    VARCHAR(20) NOT NULL REFERENCES especialist(code),
    ticket_id           UUID REFERENCES tickets(id),
    application_code    VARCHAR(50) NOT NULL REFERENCES applications(code),
    level               INTEGER NOT NULL,
    work_window_id      UUID REFERENCES work_windows(id),
    assigned_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_assignments_app ON assignments(application_code);
CREATE INDEX IF NOT EXISTS idx_assignments_especialist ON assignments(especialist_code);
CREATE INDEX IF NOT EXISTS idx_assignments_conversation ON assignments(conversation_id);
CREATE INDEX IF NOT EXISTS idx_work_windows_app ON work_windows(application_code);
CREATE INDEX IF NOT EXISTS idx_work_windows_especialist ON work_windows(especialist_code);
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_window ON balance_snapshots(work_window_id);

COMMIT;
