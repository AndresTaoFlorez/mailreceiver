import os
from pathlib import Path

PORT: int = int(os.environ.get("PORT", "8000"))
STORAGE_PATH: Path = Path(os.environ.get("STORAGE_PATH", "storage"))

HTML_PATH: Path = STORAGE_PATH / "html"
ATTACHMENTS_PATH: Path = STORAGE_PATH / "attachments"
EXCEL_PATH: Path = STORAGE_PATH / "emails.xlsx"
DB_PATH: Path = STORAGE_PATH / "emails.db"


def ensure_dirs() -> None:
    HTML_PATH.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_PATH.mkdir(parents=True, exist_ok=True)
