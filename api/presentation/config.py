import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Infra (env-only, don't change at runtime) ---
PORT: int = int(os.getenv("PORT", "8000"))
STORAGE_PATH: Path = Path(os.getenv("STORAGE_PATH", "storage"))
AGENT_HOST: str = os.getenv("AGENT_HOST", "localhost")
AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8001"))
MISSAQUEST_URL: str = os.getenv("MISSAQUEST_URL", "http://localhost:8010")

# --- Application credentials (env-only, never in config.json) ---
_APP_CREDENTIALS: dict[str, dict[str, str]] = {
    "tutela_en_linea": {
        "outlook_user": os.getenv("TUTELA_EN_LINEA_USER", ""),
        "outlook_password": os.getenv("TUTELA_EN_LINEA_PASSWORD", ""),
    },
    "demanda_en_linea": {
        "outlook_user": os.getenv("DEMANDA_EN_LINEA_USER", ""),
        "outlook_password": os.getenv("DEMANDA_EN_LINEA_PASSWORD", ""),
    },
    "firma_electronica": {
        "outlook_user": os.getenv("FIRMA_ELECTRONICA_USER", ""),
        "outlook_password": os.getenv("FIRMA_ELECTRONICA_PASSWORD", ""),
    },
    "justicia_xxi_web": {
        "outlook_user": os.getenv("JUSTICIA_XXI_WEB_USER", ""),
        "outlook_password": os.getenv("JUSTICIA_XXI_WEB_PASSWORD", ""),
    },
    "cierres_tyba": {
        "outlook_user": os.getenv("CIERRES_TYBA_USER", ""),
        "outlook_password": os.getenv("CIERRES_TYBA_PASSWORD", ""),
    },
}

# --- Storage paths ---
HTML_PATH: Path = STORAGE_PATH / "html"
ATTACHMENTS_PATH: Path = STORAGE_PATH / "attachments"
EXCEL_PATH: Path = STORAGE_PATH / "conversations.xlsx"
DB_PATH: Path = STORAGE_PATH / "conversations.db"
CONFIG_PATH: Path = STORAGE_PATH / "config.json"

# --- Defaults for config.json (dynamic, non-sensitive) ---
_DEFAULTS: dict = {
    "headless": False,
    "viewport_width": 1280,
    "viewport_height": 720,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "default_timeout": 10000,
    "navigation_timeout": 15000,
    "default_page": 1,
    "default_per_page": 20,
    "max_per_page": 100,
}


def _ensure_config_file() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(_DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8")


def load_config() -> dict:
    _ensure_config_file()
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    merged = {**_DEFAULTS, **data}
    return merged


def save_config(data: dict) -> dict:
    _ensure_config_file()
    current = load_config()
    current.update(data)
    CONFIG_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def get(key: str):
    return load_config()[key]


def get_app_credentials(app_name: str) -> dict:
    creds = _APP_CREDENTIALS.get(app_name)
    if not creds or not creds.get("outlook_user"):
        raise KeyError(f"Application '{app_name}' not found or missing credentials in .env")
    return creds


def ensure_dirs() -> None:
    HTML_PATH.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_PATH.mkdir(parents=True, exist_ok=True)
