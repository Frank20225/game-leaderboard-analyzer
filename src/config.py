"""Centralized configuration and directory paths."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ICON_DB_DIR = DATA_DIR / "icon_db"
ICON_TEMPLATES_DIR = ICON_DB_DIR / "templates"
LAYOUTS_DIR = DATA_DIR / "layouts"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_REPORTS_DIR = DOCS_DIR / "reports"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def ensure_base_dirs() -> None:
    """Create standard writable directories if they do not yet exist."""
    for d in (
        DATA_DIR,
        ICON_DB_DIR,
        ICON_TEMPLATES_DIR,
        LAYOUTS_DIR,
        OUTPUTS_DIR,
        DOCS_DIR,
        DOCS_REPORTS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
