from __future__ import annotations

import ctypes
import logging
import os
import shlex
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from .paths import launch_command

log = logging.getLogger("ressy.system")

ERROR_ALREADY_EXISTS = 183
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "Ressy"
_MAC_PLIST_NAME = "top.ressy.desktop.plist"
_LINUX_DESKTOP_NAME = "ressy.desktop"


SYNCHRONIZE = 0x00100000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def wait_for_exit(pid: int, timeout: float = 30.0) -> None:
    if pid <= 0:
        return
    if sys.platform != "win32":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                pass
            time.sleep(0.15)
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        kernel32.WaitForSingleObject(handle, int(timeout * 1000))
    finally:
        kernel32.CloseHandle(handle)


def relaunch() -> bool:
    command = [*launch_command(), "--after", str(os.getpid())]
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                command, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True
            )
        else:
            subprocess.Popen(command, start_new_session=True, close_fds=True)
    except OSError:
        log.exception("cannot restart Ressy")
        return False
    return True


class SingleInstance:

    def __init__(self, name: str = "Local\\RessyDesktopSingleton") -> None:
        self.handle = None
        self._lock_file = None
        self.already_running = False
        if sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            self.handle = kernel32.CreateMutexW(None, False, name)
            self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
            return
        try:
            import fcntl

            safe = "".join(c if c.isalnum() else "-" for c in name).strip("-") or "ressy"
            lock_path = Path(tempfile.gettempdir()) / f"ressy-{safe}.lock"
            fh = lock_path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._lock_file = fh
            except BlockingIOError:
                fh.close()
                self.already_running = True
        except Exception:
            log.debug("POSIX single instance lock unavailable", exc_info=True)


def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / _MAC_PLIST_NAME


def _linux_autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / _LINUX_DESKTOP_NAME


def autostart_enabled() -> bool:
    if sys.platform == "darwin":
        return _mac_plist_path().is_file()
    if sys.platform != "win32":
        return _linux_autostart_path().is_file()
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_VALUE)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        log.exception("cannot read autostart key")
        return False


def set_autostart(enabled: bool) -> None:
    if sys.platform == "darwin":
        plist = _mac_plist_path()
        if enabled:
            plist.parent.mkdir(parents=True, exist_ok=True)
            args_xml = "\n".join(f"        <string>{xml_escape(arg)}</string>" for arg in launch_command() + ["--background"])
            plist.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n'
                "<dict>\n"
                "    <key>Label</key>\n"
                "    <string>top.ressy.desktop</string>\n"
                "    <key>ProgramArguments</key>\n"
                "    <array>\n"
                f"{args_xml}\n"
                "    </array>\n"
                "    <key>RunAtLoad</key>\n"
                "    <true/>\n"
                "</dict>\n"
                "</plist>\n",
                encoding="utf-8",
            )
        else:
            plist.unlink(missing_ok=True)
        return
    if sys.platform != "win32":
        desktop = _linux_autostart_path()
        if enabled:
            desktop.parent.mkdir(parents=True, exist_ok=True)
            exec_cmd = " ".join(shlex.quote(arg) for arg in launch_command() + ["--background"])
            desktop.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Ressy\n"
                "Comment=Ressy AI voice assistant\n"
                f"Exec={exec_cmd}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            desktop.unlink(missing_ok=True)
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = subprocess.list2cmdline(launch_command() + ["--background"])
            winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, _RUN_VALUE)
            except FileNotFoundError:
                pass
