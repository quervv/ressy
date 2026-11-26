from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__, dpapi
from .paths import app_dir, chmod_private

log = logging.getLogger("ressy.install")

APP_EXE = "Ressy.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Ressy"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_APP = "Ressy"
RUN_SERVER = "Ressy Server"
SERVER_STOP_EVENT = "Local\\RessyServerStop"
SERVER_MUTEX = "Local\\RessyServerSingleton"
DEFAULT_SERVER_PORT = 8765
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / "Ressy"


def start_menu_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Ressy"


def desktop_dir() -> Path:
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
            return Path(buf.value)
    except (AttributeError, OSError):
        pass
    return Path.home() / "Desktop"


def _reg_set(key_path: str, name: str, value: str | int | None) -> None:
    import winreg

    if value is None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
        winreg.SetValueEx(key, name, 0, kind, value)


def set_run(name: str, command: str | None) -> None:
    _reg_set(RUN_KEY, name, command)


def register_uninstall(install_dir: Path, size_kb: int) -> None:
    exe = install_dir / APP_EXE
    values: dict[str, str | int] = {
        "DisplayName": "Ressy",
        "DisplayVersion": __version__,
        "Publisher": "Ressy (open source, MIT)",
        "DisplayIcon": f'"{exe}",0',
        "InstallLocation": str(install_dir),
        "UninstallString": subprocess.list2cmdline([str(exe), "--uninstall"]),
        "QuietUninstallString": subprocess.list2cmdline([str(exe), "--uninstall", "--quiet"]),
        "URLInfoAbout": "https://ressy.top",
        "EstimatedSize": int(size_kb),
        "NoModify": 1,
        "NoRepair": 1,
    }
    for name, value in values.items():
        _reg_set(UNINSTALL_KEY, name, value)


def unregister_uninstall() -> None:
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass


def installed_dir() -> Path | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
            return Path(value) if value else None
    except OSError:
        return None


def create_shortcut(link: Path, target: Path, args: str = "", description: str = "") -> None:
    link.parent.mkdir(parents=True, exist_ok=True)

    def q(text: str) -> str:
        return "'" + text.replace("'", "''") + "'"

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + q(str(link)) + ");"
        "$s.TargetPath = " + q(str(target)) + ";"
        "$s.Arguments = " + q(args) + ";"
        "$s.WorkingDirectory = " + q(str(target.parent)) + ";"
        "$s.IconLocation = " + q(f"{target},0") + ";"
        "$s.Description = " + q(description) + ";"
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True, creationflags=CREATE_NO_WINDOW, capture_output=True, timeout=60,
    )


def remove_shortcuts() -> None:
    shutil.rmtree(start_menu_dir(), ignore_errors=True)
    for name in ("Ressy.lnk", "Ressy Server.lnk"):
        try:
            (desktop_dir() / name).unlink()
        except FileNotFoundError:
            pass


@dataclass
class ServerConfig:
    telegram_token: str = ""
    discord_token: str = ""
    discord_invite_url: str = ""
    port: int = DEFAULT_SERVER_PORT

    @staticmethod
    def path() -> Path:
        return app_dir() / "server.json"

    @classmethod
    def load(cls) -> "ServerConfig":
        cfg = cls()
        try:
            raw = json.loads(cls.path().read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return cfg
        for name in ("telegram_token", "discord_token"):
            enc = raw.get(f"{name}_enc") or ""
            if enc:
                try:
                    setattr(cfg, name, dpapi.unprotect(enc))
                except Exception:
                    log.warning("cannot decrypt %s", name)
        cfg.discord_invite_url = str(raw.get("discord_invite_url") or "")
        try:
            cfg.port = max(1, min(65535, int(raw.get("port") or DEFAULT_SERVER_PORT)))
        except (TypeError, ValueError):
            cfg.port = DEFAULT_SERVER_PORT
        return cfg

    def save(self) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "telegram_token_enc": dpapi.protect(self.telegram_token) if self.telegram_token else "",
            "discord_token_enc": dpapi.protect(self.discord_token) if self.discord_token else "",
            "discord_invite_url": self.discord_invite_url,
            "port": int(self.port),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        chmod_private(tmp)
        os.replace(tmp, path)


def lan_addresses() -> list[str]:
    import socket

    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def _kernel32():
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenEventW.restype = wintypes.HANDLE
    k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateEventW.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    return k


def stop_server() -> bool:
    if sys.platform != "win32":
        return False
    k = _kernel32()
    handle = k.OpenEventW(0x0002, False, SERVER_STOP_EVENT)
    if not handle:
        return False
    k.SetEvent(handle)
    k.CloseHandle(handle)
    return True


def ask_app_to_quit(timeout_ms: int = 4000) -> bool:
    from PySide6.QtNetwork import QLocalSocket

    from .app import _server_name

    socket = QLocalSocket()
    socket.connectToServer(_server_name())
    if not socket.waitForConnected(1500):
        return False
    socket.write(b"quit\n")
    socket.waitForBytesWritten(1000)
    socket.waitForDisconnected(timeout_ms)
    return True


def wait_unlocked(folder: Path, seconds: float = 10.0) -> bool:
    import time

    exe = folder / APP_EXE
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not exe.exists():
            return True
        try:
            with open(exe, "r+b"):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def schedule_folder_removal(folder: Path) -> None:
    pid = os.getpid()
    script = (
        f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500; "
        "Remove-Item -LiteralPath '" + str(folder).replace("'", "''") + "' -Recurse -Force -ErrorAction SilentlyContinue"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True,
    )


def uninstall(folder: Path, remove_data: bool) -> None:
    stop_server()
    set_run(RUN_APP, None)
    set_run(RUN_SERVER, None)
    remove_shortcuts()
    unregister_uninstall()
    if remove_data:
        shutil.rmtree(app_dir(), ignore_errors=True)
    if (folder / APP_EXE).exists():
        schedule_folder_removal(folder)


def run_server() -> int:
    from logging.handlers import RotatingFileHandler

    from .log import RedactFilter
    from .paths import ensure_dirs, log_dir
    from .remote.local_bot import _import_server

    ensure_dirs()
    from .system_integration import SingleInstance

    instance = SingleInstance(SERVER_MUTEX)
    if instance.already_running:
        return 0
    handler = RotatingFileHandler(log_dir() / "server.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore", "telegram", "discord", "aiohttp.access", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg = ServerConfig.load()
    if not (cfg.telegram_token or cfg.discord_token):
        log.error("Ressy Server: no bot token in %s", ServerConfig.path())
        return 2
    server_main = _import_server()
    from ressy_server.settings import Settings as ServerSettings

    folder = app_dir() / "server"
    folder.mkdir(parents=True, exist_ok=True)
    settings = ServerSettings(
        telegram_token=cfg.telegram_token,
        discord_token=cfg.discord_token,
        discord_invite_url=cfg.discord_invite_url,
        host="0.0.0.0",
        port=cfg.port,
        db_path=str(folder / "ressy.db"),
    )

    import asyncio
    import threading

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        if sys.platform == "win32":
            k = _kernel32()
            event = k.CreateEventW(None, True, False, SERVER_STOP_EVENT)

            def watch() -> None:
                k.WaitForSingleObject(event, 0xFFFFFFFF)
                loop.call_soon_threadsafe(stop.set)

            threading.Thread(target=watch, name="server-stop", daemon=True).start()
        await server_main.serve(settings, stop)

    log.info("Ressy Server %s starting on port %d", __version__, cfg.port)
    try:
        asyncio.run(main())
    except Exception:
        log.exception("Ressy Server stopped with an error")
        return 1
    return 0
