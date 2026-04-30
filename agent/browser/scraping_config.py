"""
scraping_config.py — Domain-level scraping configuration.

Defines the parameters that control how the agent scrapes conversations
from Outlook Web. Values are persisted in a JSON file (infrastructure layer)
and can be updated at runtime via the API.
"""
from __future__ import annotations

import json
from pathlib import Path

from api.presentation.config import STORAGE_PATH

SCRAPING_CONFIG_PATH: Path = STORAGE_PATH / "scraping_config.json"

DEFAULTS: dict = {
    # Scroll loop
    "max_scroll_iterations": 200,
    "no_new_rows_limit": 10,
    "scroll_wait_ms": 1500,
    "scroll_amount_px": 600,

    # Limits
    "max_conversations": 0,  # 0 = unlimited
    "batch_size": 10,  # flush to disk every N conversations

    # Timeouts
    "listbox_timeout_ms": 15000,
    "row_render_wait_ms": 2000,
    "filter_wait_ms": 3000,
}


def _ensure_file() -> None:
    SCRAPING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SCRAPING_CONFIG_PATH.exists():
        SCRAPING_CONFIG_PATH.write_text(
            json.dumps(DEFAULTS, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load() -> dict:
    _ensure_file()
    data = json.loads(SCRAPING_CONFIG_PATH.read_text(encoding="utf-8"))
    return {**DEFAULTS, **data}


def save(data: dict) -> dict:
    _ensure_file()
    current = load()
    current.update(data)
    SCRAPING_CONFIG_PATH.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return current


def get(key: str):
    return load()[key]
