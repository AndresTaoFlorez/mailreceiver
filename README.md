# mailwindow

Two-service RPA: **API** (REST endpoints) + **Agent** (Outlook browser automation with Playwright).

## Quick start

```bash
# API (port 8000)
uvicorn main:app --reload --port 8000

# Agent (port 8001)
uvicorn agent.core:app --reload --port 8001
```

Swagger UI: `http://localhost:8000/schema/swagger`

## Flow

```
1. Client sends POST /tutela-en-linea/unread-conversations { folder, page, per_page }
2. API calls Agent /process → Agent opens Outlook, scrapes conversations
3. Agent saves new conversations to PostgreSQL (duplicates skipped by conversation_id)
4. API queries PostgreSQL and returns paginated results
```

```
API (port 8000)  ──HTTP──>  Agent (port 8001)
     │                           │
     │ POST /{app}/unread-conversations │ POST /process
     │                           │   └─ login → navigate → filter → scrape
     │                           │   └─ save to PostgreSQL
     │                           │
     └─ Query PostgreSQL ────────└─ Playwright (Chromium)
         return paginated
```

## API endpoints

### Tutela en Linea

**`POST /tutela-en-linea/unread-conversations`**

```json
{ "folder": "Bandeja de entrada", "page": 1, "per_page": 20 }
```

### Justicia XXI Web

**`POST /justicia-xxi-web/unread-conversations`**

```json
{ "folder": "Bandeja de entrada", "page": 1, "per_page": 20 }
```

### Response (paginated)

```json
{
  "status": "ok",
  "page": 1,
  "per_page": 20,
  "total": 78,
  "pages": 4,
  "new_saved": 5,
  "conversations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "conversation_id": "AAQkADJm...",
      "subject": "SOLICITUD URGENTE",
      "sender": "Juzgado 01 Laboral",
      "sender_email": "j01lactociena@cendoj.ramajudicial.gov.co",
      "date": { "year": 2026, "month": 4, "day": 21, "hour": 19 },
      "created_at": "2026-04-21T19:11:00+00:00"
    }
  ]
}
```

- `new_saved`: conversations saved this scrape (0 if all were duplicates)
- `total`: total conversations in DB for this app+folder
- `pages`: total pages available

### Config

**`GET /config`** — Read current config.

**`POST /config`** — Update config (partial merge).

## Database

PostgreSQL on `159.223.160.218:5432`, database `mailreceiver`.

Table `conversations`:
- `id` UUID PK
- `conversation_id` unique (prevents duplicates)
- `app`, `folder`, `subject`, `sender`, `sender_email`
- `year`, `month`, `day`, `hour`
- `created_at` timestamptz

## Configuration

Credentials in `.env` (never committed):

```
TUTELA_EN_LINEA_USER=...
TUTELA_EN_LINEA_PASSWORD=...
JUSTICIA_XXI_WEB_USER=...
JUSTICIA_XXI_WEB_PASSWORD=...
POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/mailreceiver
```

Dynamic config in `storage/config.json` and `storage/scraping_config.json`.

## Docker

```bash
docker compose up -d --build
```

API on port 8010, Agent on port 8011.
