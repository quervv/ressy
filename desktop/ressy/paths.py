from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Ressy"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Ressy"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "Ressy"


def log_dir() -> Path:
    return app_dir() / "logs"


def config_path() -> Path:
    return app_dir() / "config.json"


def user_folder(kind: str) -> Path:
    defaults = {
        "desktop": "Desktop",
        "documents": "Documents",
        "downloads": "Downloads",
        "pictures": "Pictures",
        "music": "Music",
        "videos": "Movies" if sys.platform == "darwin" else "Videos",
    }
    key = kind.lower()
    if sys.platform == "win32":
        try:
            from .tools import winapi

            known = winapi.known_folder(key)
            if known:
                return Path(known)
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
        xdg_names = {
            "desktop": "XDG_DESKTOP_DIR",
            "documents": "XDG_DOCUMENTS_DIR",
            "downloads": "XDG_DOWNLOAD_DIR",
            "pictures": "XDG_PICTURES_DIR",
            "music": "XDG_MUSIC_DIR",
            "videos": "XDG_VIDEOS_DIR",
        }
        var = xdg_names.get(key)
        if var and cfg.is_file():
            try:
                for raw in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                    raw = raw.strip()
                    if raw.startswith(f"{var}="):
                        val = raw.split("=", 1)[1].strip().strip('"')
                        val = val.replace("$HOME", str(Path.home()))
                        if val:
                            return Path(val)
            except OSError:
                pass
    return Path.home() / defaults.get(key, key.title())


def pictures_dir() -> Path:
    return user_folder("pictures") / "Ressy"


def videos_dir() -> Path:
    return user_folder("videos") / "Ressy"


def chmod_private(path: Path) -> None:
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


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
    if sys.platform == "win32":
        pythonw = exe.with_name("pythonw.exe")
        interpreter = pythonw if pythonw.exists() else exe
        return [str(interpreter), "-m", "ressy"]
    return [str(exe), "-m", "ressy"]
