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


def runtime_exe(install_dir: Path) -> Path:
    pyw = install_dir / "pythonw.exe"
    if pyw.is_file() and (install_dir / "app" / "ressy").is_dir():
        return pyw
    return install_dir / APP_EXE


def runtime_cmd(install_dir: Path, *extra: str) -> list[str]:
    exe = runtime_exe(install_dir)
    if exe.name.lower() == "pythonw.exe":
        return [str(exe), "-m", "ressy", *extra]
    return [str(exe), *extra]


def runtime_icon(install_dir: Path) -> str:
    ico = install_dir / "ressy.ico"
    if ico.is_file():
        return str(ico)
    return f"{runtime_exe(install_dir)},0"


def set_run(name: str, command: str | None) -> None:
    _reg_set(RUN_KEY, name, command)


def register_uninstall(install_dir: Path, size_kb: int) -> None:
    values: dict[str, str | int] = {
        "DisplayName": "Ressy",
        "DisplayVersion": __version__,
        "Publisher": "Ressy (open source, MIT)",
        "DisplayIcon": runtime_icon(install_dir),
        "InstallLocation": str(install_dir),
        "UninstallString": subprocess.list2cmdline(runtime_cmd(install_dir, "--uninstall")),
        "QuietUninstallString": subprocess.list2cmdline(runtime_cmd(install_dir, "--uninstall", "--quiet")),
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
    import ctypes
    from ctypes import POINTER, Structure, c_int, c_long, c_void_p, c_wchar_p, wintypes

    link.parent.mkdir(parents=True, exist_ok=True)

    class GUID(Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    def _guid(s: str) -> GUID:
        import uuid
        return GUID.from_buffer_copy(uuid.UUID(s).bytes_le)

    CLSID_ShellLink = _guid("00021401-0000-0000-C000-000000000046")
    IID_IShellLinkW = _guid("000214F9-0000-0000-C000-000000000046")
    IID_IPersistFile = _guid("0000010b-0000-0000-C000-000000000046")

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx(None, 2)
    sl_ptr = c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(CLSID_ShellLink), None, 1, ctypes.byref(IID_IShellLinkW), ctypes.byref(sl_ptr)
    )
    if hr != 0 or not sl_ptr:
        raise OSError(f"CoCreateInstance IShellLinkW failed: {hr:#x}")

    def _vcall(obj_ptr: c_void_p, index: int, restype: Any, *argtypes: Any):
        vtbl = ctypes.cast(obj_ptr, POINTER(POINTER(c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[index])

    try:
        _vcall(sl_ptr, 20, c_long, c_wchar_p)(sl_ptr, str(target))
        if args:
            _vcall(sl_ptr, 11, c_long, c_wchar_p)(sl_ptr, args)
        _vcall(sl_ptr, 9, c_long, c_wchar_p)(sl_ptr, str(target.parent))
        ico = target.parent / "ressy.ico"
        icon_loc = str(ico) if ico.is_file() else f"{target},0"
        _vcall(sl_ptr, 17, c_long, c_wchar_p, c_int)(sl_ptr, icon_loc, 0)
        if description:
            _vcall(sl_ptr, 7, c_long, c_wchar_p)(sl_ptr, description)

        pf_ptr = c_void_p()
        hr = _vcall(sl_ptr, 0, c_long, POINTER(GUID), POINTER(c_void_p))(
            sl_ptr, ctypes.byref(IID_IPersistFile), ctypes.byref(pf_ptr)
        )
        if hr != 0 or not pf_ptr:
            raise OSError(f"QueryInterface IPersistFile failed: {hr:#x}")
        try:
            _vcall(pf_ptr, 6, c_long, c_wchar_p, wintypes.BOOL)(pf_ptr, str(link), True)
        finally:
            _vcall(pf_ptr, 2, wintypes.ULONG)(pf_ptr)
    finally:
        _vcall(sl_ptr, 2, wintypes.ULONG)(sl_ptr)


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

    targets = [folder / APP_EXE, folder / "pythonw.exe", folder / "python312.dll"]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        locked = False
        for exe in targets:
            if not exe.exists():
                continue
            try:
                with open(exe, "r+b"):
                    pass
            except OSError:
                locked = True
                break
        if not locked:
            return True
        time.sleep(0.3)
    return False


def schedule_folder_removal(folder: Path) -> None:
    escaped = str(folder).replace('"', '""')
    cmd = f'ping -n 3 127.0.0.1 >nul & rmdir /s /q "{escaped}"'
    subprocess.Popen(
        ["cmd.exe", "/c", cmd],
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
    if runtime_exe(folder).exists():
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
