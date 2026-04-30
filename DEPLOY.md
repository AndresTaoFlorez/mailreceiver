# Deployment

## Ports

Configured via `.env`. Change if those ports are taken on the server:

```env
PORT=8020        # API port (used both inside the container and on the host)
AGENT_PORT=8021  # Agent port (same)
```

## Docker (production)

```bash
docker compose up -d --build
```

- API on `PORT`, Agent on `AGENT_PORT`.
- API talks to agent via Docker service name `agent` (not localhost).
- `MANAGE_AGENT=false` is set in `Dockerfile.api` — the API does not spawn the agent as a subprocess; the agent container handles that.

## CI/CD

GitHub Actions on push to `main`:
1. SSH to the Linode droplet
2. `git pull`
3. Writes `.env` from GitHub Secrets
4. `docker compose up -d --build`

Remote path: `/home/sample/tybacase_mailwindow`

## Local development

```bash
.venv\Scripts\activate

# Reads litestar.toml → port 8020, agent auto-starts on 8021
litestar run

# Or explicitly:
python -m litestar --app api.presentation.app:app run --host 0.0.0.0 --port 8020 --reload

# Agent standalone (debug only):
python -m agent --port 8021 --reload
```

**Windows note**: `agent/__main__.py` sets `WindowsProactorEventLoopPolicy` required by Playwright. Do not use `uvicorn agent.core:app` directly on Windows.

## GitHub Secrets required

| Secret | Description |
|---|---|
| `SSH_HOST` | Droplet IP |
| `SSH_USER` | SSH user |
| `SSH_KEY` | SSH private key |
| `PORT` | API port (e.g. `8020`) |
| `AGENT_PORT` | Agent port (e.g. `8021`) |
| `PG_USER` | PostgreSQL user |
| `PG_PASSWORD` | PostgreSQL password |
| `PG_DATABASE` | PostgreSQL database name |
| `MISSAQUEST_URL` | Missaquest service URL |
| `TUTELA_EN_LINEA_USER` | Outlook user |
| `TUTELA_EN_LINEA_PASSWORD` | Outlook password |
| `DEMANDA_EN_LINEA_USER` | Outlook user |
| `DEMANDA_EN_LINEA_PASSWORD` | Outlook password |
| `FIRMA_ELECTRONICA_USER` | Outlook user |
| `FIRMA_ELECTRONICA_PASSWORD` | Outlook password |
| `JUSTICIA_XXI_WEB_USER` | Outlook user |
| `JUSTICIA_XXI_WEB_PASSWORD` | Outlook password |
| `CIERRES_TYBA_USER` | Outlook user |
| `CIERRES_TYBA_PASSWORD` | Outlook password |

`PG_HOST` reuses `SSH_HOST` (same server). `PG_PORT` is hardcoded to `5432`.

## Migrations

Run manually against PostgreSQL in order:

```
001–006  — initial schema, workload dispatch, folder config, conversations level
007_uuid_fks.sql         — UUID FKs on assignments, work_windows, balance_snapshots
008_analyst_folders.sql  — Merge specialist_folders into folder_config
```
