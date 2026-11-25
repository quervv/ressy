from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Ressy"


def log_dir() -> Path:
    return app_dir() / "logs"


def config_path() -> Path:
    return app_dir() / "config.json"


def pictures_dir() -> Path:
    return Path.home() / "Pictures" / "Ressy"


def ensure_dirs() -> None:
    for folder in (app_dir(), log_dir()):
        folder.mkdir(parents=True, exist_ok=True)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(relative: str) -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "ressy" / relative
    return Path(__file__).resolve().parent / relative


def launch_command() -> list[str]:
    if is_frozen():
        return [sys.executable]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    return [str(interpreter), "-m", "ressy"]
