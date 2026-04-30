-- Add level column to conversations table.
-- Level is determined by the Outlook folder the conversation was scraped from
-- (e.g. SOPORTE BASICO = level 1, SOPORTE AVANZADO = level 2).

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS level INTEGER;
