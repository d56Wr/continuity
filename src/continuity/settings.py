"""Tiny JSON settings store and autostart handling."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
FILE = CONFIG / "continuity" / "settings.json"
AUTOSTART = CONFIG / "autostart" / "continuity.desktop"

_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(FILE.read_text())
        except (OSError, ValueError):
            _cache = {}
    return _cache


def get(key: str, default: Any = None) -> Any:
    return _load().get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001 - mirrors get()
    data = _load()
    data[key] = value
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(FILE)


def _launcher() -> str:
    exe = shutil.which("continuity")
    local = Path.home() / ".local" / "bin" / "continuity"
    if not exe and local.exists():
        exe = str(local)
    return exe if exe else f"{sys.executable} -m continuity"


def autostart_enabled() -> bool:
    return AUTOSTART.exists()


def set_autostart(on: bool) -> None:
    if not on:
        AUTOSTART.unlink(missing_ok=True)
        return
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART.write_text(
        "[Desktop Entry]\nType=Application\nName=Continuity\n"
        f"Exec={_launcher()} --background\nIcon=continuity\n"
        "X-GNOME-Autostart-enabled=true\nNoDisplay=true\n")
