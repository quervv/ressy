from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from ctypes import wintypes

from .paths import launch_command

log = logging.getLogger("ressy.system")

ERROR_ALREADY_EXISTS = 183
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "Ressy"


SYNCHRONIZE = 0x00100000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def wait_for_exit(pid: int, timeout: float = 30.0) -> None:
    if sys.platform != "win32" or pid <= 0:
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
        subprocess.Popen(
            command, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, close_fds=True
        )
    except OSError:
        log.exception("cannot restart Ressy")
        return False
    return True


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
