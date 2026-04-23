-- ============================================================================
-- Database: mailreceiver
-- Full schema reference — all tables for tybacase_mailwindow
-- ============================================================================

-- 1. Conversations — scraped email conversations from Outlook
--
--    conversation_id : Exchange thread ID (unique, prevents duplicates)
--    app             : application key (tutela_en_linea, justicia_xxi_web, etc.)
--    folder          : Outlook folder name where it was found
--    subject         : email subject line
--    sender          : sender display name
--    sender_email    : sender email address
--    body            : full HTML body (extracted in second pass via /extract-bodies)
--    tags            : email tags/categories
--    to_address      : recipient address
--    from_address    : sender address (explicit field)
--    year/month/day/hour : parsed date components from the email
--
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id VARCHAR NOT NULL,
    app             VARCHAR(50) NOT NULL,
    folder          VARCHAR(200) NOT NULL,
    subject         VARCHAR NOT NULL DEFAULT '',
    sender          VARCHAR NOT NULL DEFAULT '',
    sender_email    VARCHAR NOT NULL DEFAULT '',
    body            TEXT NOT NULL DEFAULT '',
    tags            TEXT NOT NULL DEFAULT '',
    to_address      VARCHAR NOT NULL DEFAULT '',
    from_address    VARCHAR NOT NULL DEFAULT '',
    year            INTEGER,
    month           INTEGER,
    day             INTEGER,
    hour            INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_conversation_id UNIQUE (conversation_id)
);

-- 2. Especialist — catalog of analysts/specialists
--
--    code            : unique short code (s20, s15, s14, etc.)
--    name            : full name
--    level           : 1 = SOPORTE BÁSICO, 2 = SOPORTE AVANZADO
--    load_percentage : NULL = auto-distribute equally, value = fixed % (e.g. 30)
--    priority        : lower number = higher priority (used for tiebreaking)
--    active          : whether this specialist receives case assignments
--
CREATE TABLE IF NOT EXISTS especialist (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(20) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    level           INTEGER NOT NULL,
    load_percentage INTEGER DEFAULT NULL,
    priority        INTEGER DEFAULT 0,
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Tickets — cases created in Judit (Ivanti HEAT) via TybaCase RPA
--
--    code            : ticket number returned by Judit
--    type            : case type / template used
--    application     : application key
--    conversation_id : FK to conversations(id)
--    especialist_code: FK to especialist(code) — assigned analyst
--
CREATE TABLE IF NOT EXISTS tickets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             VARCHAR(50),
    type             VARCHAR(100),
    application      VARCHAR(50) NOT NULL,
    conversation_id  UUID REFERENCES conversations(id),
    especialist_code VARCHAR(20) REFERENCES especialist(code),
    date_time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Folder config — maps Outlook folder names to support levels
--
--    folder_name : exact Outlook folder name (e.g. "SOPORTE BÁSICO")
--    level       : 1 = nivel 1 (básico), 2 = nivel 2 (avanzado)
--    application : application key
--    active      : whether this mapping is in use
--
CREATE TABLE IF NOT EXISTS folder_config (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_name VARCHAR(200) NOT NULL,
    level       INTEGER NOT NULL,
    application VARCHAR(50) NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_folder_app UNIQUE (folder_name, application)
);
