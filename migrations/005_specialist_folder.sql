-- Maps each specialist to an Outlook folder per application.
-- Example: specialist "spec01" handles folder "ANDRES TAO (S20)" in app "justicia_xxi_web".

CREATE TABLE IF NOT EXISTS specialist_folders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_code VARCHAR(50) NOT NULL REFERENCES applications(code),
    especialist_code VARCHAR(20) NOT NULL REFERENCES especialist(code),
    folder_name      VARCHAR(200) NOT NULL,
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (application_code, especialist_code)
);
