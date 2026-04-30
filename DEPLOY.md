# Deployment

## Docker (local o servidor)

```bash
docker compose up -d --build
```

Puertos por defecto: API en 8010, Agent en 8011.

## CI/CD

GitHub Actions en push a `main`:

1. SSH al droplet de DigitalOcean
2. `git pull`
3. `docker compose up -d --build`

Ruta remota: `/home/sample/tybacase_mailwindow`

## Ejecucion manual (desarrollo)

```bash
# Activar venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# Iniciar (API en 8000, Agent se inicia automaticamente en 8001)
litestar --app api.app:app run --reload

# Si el launcher de litestar falla en Windows:
python -m litestar --app api.app:app run --reload

# Agent standalone (debug):
python -m agent --port 8001 --reload
```

**Nota Windows**: el launcher del Agent (`agent/__main__.py`) configura `WindowsProactorEventLoopPolicy` requerido por Playwright. No usar `uvicorn agent.core:app` directamente.

## Migraciones

Las migraciones en `migrations/` se ejecutan manualmente contra PostgreSQL:

```
003_workload_dispatch.sql    — Tablas de dispatch + FKs de application_code
004_drop_extraction_mode.sql — Elimina extraction_mode de folder_config
005_specialist_folder.sql    — Tabla specialist_folders
006_conversation_level.sql   — Campo level en conversations
```
