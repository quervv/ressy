from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from ctypes import wintypes

from .paths import launch_command

log = logging.getLogger("ressy.system")

ERROR_ALREADY_EXISTS = 183
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "Ressy"


class SingleInstance:

    def __init__(self, name: str = "Local\\RessyDesktopSingleton") -> None:
        self.handle = None
        self.already_running = False
        if sys.platform != "win32":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        self.handle = kernel32.CreateMutexW(None, False, name)
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
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
    if sys.platform != "win32":
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
