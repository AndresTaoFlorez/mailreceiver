# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Two-service RPA system that scrapes emails from Outlook Web (outlook.office.com) using Playwright browser automation and persists them in PostgreSQL. Built with **Litestar** (not FastAPI/Django).

- **API** (`api/`): REST service on port 8000, manages the Agent as a subprocess
- **Agent** (`agent/`): Browser automation service on port 8001, runs a 5-step Playwright pipeline

## Running the project

```bash
# Activate venv first, then one command starts both services:
litestar --app api.app:app run --reload

# If litestar launcher is broken on Windows, use:
python -m litestar --app api.app:app run --reload

# Agent standalone (for debugging):
python -m agent --port 8001 --reload

# Docker:
docker compose up -d --build
```

The API's `on_startup` hook auto-starts the Agent as a subprocess via `AgentManager`. No need to launch both manually.

**Windows note:** The Agent launcher (`agent/__main__.py`) sets `WindowsProactorEventLoopPolicy` required by Playwright. Don't bypass it with plain `uvicorn agent.core:app`.

## Architecture

### Request flow

```
POST /{app}/unread-conversations (api/routes/tutela_en_linea.py)
  → AgentManager.ensure_running()
  → HTTP POST to Agent at localhost:8001/process
    → Pipeline 1 (login): LoginStep
    → Pipeline 2 (scrape): NavigateFolderStep → FilterUnreadStep → ScrapeConversationsStep → ExtractBodyStep
    → save_conversations() → PostgreSQL upsert
  → Query PostgreSQL → return paginated response
```

### Pipeline system

Each step extends `BaseStep` (`agent/browser/base_step.py`) with:
- `execute(ctx: StepContext) -> StepContext` — main logic
- `is_critical: bool` — if True, pipeline aborts on failure; if False, continues
- `StepContext` carries `page` (Playwright Page) and `shared` dict between steps

Steps are orchestrated by `StepPipeline` (`agent/browser/pipeline.py`).

### Key data flow through `ctx.shared`

- Step 2 sets `expected_unread`, `folder`
- Step 3 sets `filter_applied`
- Step 4 sets `conversations` (list of dicts), `scroll_exhausted`, `unread_count`
- Step 5 enriches each conversation dict with `body` (HTML)

### Browser sessions

`SessionManager` (`agent/browser/session.py`) manages one Chromium instance per application (e.g., `tutela_en_linea`, `justicia_xxi_web`). Sessions are created on demand and auto-restart if the browser dies. A per-app `asyncio.Lock` serializes concurrent requests.

### Outlook virtual scroll

Outlook Web uses Virtuoso virtual scroll — only ~15-20 email rows exist in the DOM at any time. Step 4 scrolls and parses incrementally. Step 5 must scroll back to find rows by `data-convid` since they may have left the DOM.

### Email parsing

`agent/browser/utils/email_parser.py` extracts fields via a single JS evaluate call on each `[role="option"]` row: `conversation_id`, `subject`, `sender`, `sender_email`, `date`, `tags`.

## Database

PostgreSQL (asyncpg + SQLAlchemy async). Models in `domain/models.py`. The `conversations` table has `UNIQUE(conversation_id)` — upsert logic in `domain/repository.py`.

## Configuration

- `.env`: Outlook credentials per app, PostgreSQL URL
- `storage/config.json`: Browser settings (viewport, headless, user agent)
- `storage/scraping_config.json`: Scroll loop params, timeouts — editable at runtime via `POST /scraping-config`

## Deployment

GitHub Actions on push to `main` → SSH to DigitalOcean droplet → `git pull && docker compose up -d --build`. Remote path: `/home/sample/tybacase_mailwindow`.

## Known issues

- Outlook dark mode: extracted HTML has `rgb(255, 255, 255)` text colors and `data-ogsc` attributes. The HTML file writer detects this and applies a dark background wrapper.
- Step 3 (filter unread) is `is_critical=False` — if Outlook changes filter button selectors, scraping continues without filtering (gets all emails, not just unread).
- Debug screenshots are saved to `storage/` on filter steps and on step failures.
- Saved HTML files in `storage/html/` are for development inspection only.
