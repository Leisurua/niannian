"""Persist only the server origin; credentials stay in memory."""
import json
import os
from pathlib import Path

from .api import normalize_base_url


def _path(application: str) -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / application / "settings.json"


def load_base_url(application: str) -> str | None:
    try:
        payload = json.loads(_path(application).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return normalize_base_url(str(payload.get("base_url", "")))
    except (OSError, ValueError):
        pass
    return None


def save_base_url(application: str, value: str) -> None:
    payload = {"base_url": normalize_base_url(value)}
    path = _path(application)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
