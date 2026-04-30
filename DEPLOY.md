# Deployment

## Ports

All ports are configured via `.env`. Change these if defaults conflict with other apps on the server:

```env
PORT=8020               # API internal port (inside process/container)
AGENT_PORT=8021         # Agent internal port

API_HOST_PORT=8020      # Host port exposed by Docker (external)
AGENT_HOST_PORT=8021    # Host port exposed by Docker (external)
```

## Docker (recommended for production)

```bash
docker compose up -d --build
```

- API listens on `API_HOST_PORT` externally, `PORT` internally.
- Agent listens on `AGENT_HOST_PORT` externally, `AGENT_PORT` internally.
- API talks to the agent via service name `agent` (Docker DNS), not localhost.
- `MANAGE_AGENT=false` is set automatically in `Dockerfile.api` — the API does NOT spawn the agent as a subprocess; the agent container is already running.

## CI/CD

GitHub Actions on push to `main`:

1. SSH to the Linode droplet
2. `git pull`
3. `docker compose up -d --build`

Remote path: `/home/sample/tybacase_mailwindow`

## Local development (without Docker)

```bash
# Activate venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# Start — reads port from litestar.toml (PORT=8020)
# Agent auto-starts on AGENT_PORT=8021 as a subprocess
litestar run

# Or explicitly:
python -m litestar --app api.presentation.app:app run --host 0.0.0.0 --port 8020 --reload

# Agent standalone (debug only):
python -m agent --port 8021 --reload
```

`litestar.toml` sets `port = 8020` and `host = "0.0.0.0"` so the short `litestar run` command just works.

**Windows note**: `agent/__main__.py` sets `WindowsProactorEventLoopPolicy` required by Playwright.
Do NOT use `uvicorn agent.core:app` directly on Windows.

## Environment variables (.env)

| Variable | Description | Default |
|---|---|---|
| `PORT` | API listening port | `8020` |
| `AGENT_PORT` | Agent listening port | `8021` |
| `API_HOST_PORT` | Docker host port for API | `8020` |
| `AGENT_HOST_PORT` | Docker host port for Agent | `8021` |
| `AGENT_HOST` | Host where agent runs | `localhost` |
| `MANAGE_AGENT` | `true` = API spawns agent subprocess (local dev); `false` = separate container (Docker) | `true` |
| `PG_HOST` / `PG_PORT` / `PG_USER` / `PG_PASSWORD` / `PG_DATABASE` | PostgreSQL connection | — |
| `MISSAQUEST_URL` | URL of the Missaquest service | — |

## Migrations

Run manually against PostgreSQL (in order):

```
001_initial.sql
002_...
003_workload_dispatch.sql    — Workload dispatch tables + application_code FKs
004_drop_extraction_mode.sql — Remove extraction_mode from folder_config
005_specialist_folder.sql    — specialist_folders table
006_conversation_level.sql   — level field on conversations
007_uuid_fks.sql             — UUID FKs on assignments, work_windows, balance_snapshots
008_analyst_folders.sql      — Merge specialist_folders into folder_config; add especialist_id
```
