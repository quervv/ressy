from __future__ import annotations

import ctypes
import logging
import sys
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass

from ..i18n import tr

log = logging.getLogger("ressy.winapi")

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        dwmapi = None
else:
    user32 = None
    kernel32 = None
    shell32 = None
    ole32 = None
    dwmapi = None

ULONG_PTR = ctypes.c_size_t

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_VSC = 0


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


if sys.platform == "win32":
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short

VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "invio": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "pause": 0x13, "capslock": 0x14,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "spazio": 0x20, "pageup": 0x21, "pagedown": 0x22,
    "end": 0x23, "fine": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "stamp": 0x2C, "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "canc": 0x2E, "del": 0x2E,
    "win": 0x5B, "windows": 0x5B, "lwin": 0x5B, "rwin": 0x5C, "menu": 0x5D, "apps": 0x5D,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
VK.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({str(d): 0x30 + d for d in range(10)})

_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D,
             0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}
MODIFIERS = {0x10, 0x11, 0x12, 0x5B, 0x5C}


class InputError(RuntimeError):
    pass


def key_input(vk: int, up: bool = False) -> INPUT:
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0)
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC) & 0xFF
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def unicode_input(code_unit: int, up: bool = False) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, code_unit, flags, 0, 0)))


def send_inputs(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    array = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        err = ctypes.get_last_error()
        raise InputError(
            tr("Windows ha bloccato la tastiera simulata (finestra di un amministratore o PC bloccato?)")
            if err in (0, 5) else tr("SendInput non riuscito (errore {err})").format(err=err)
        )


def tap(vk: int) -> None:
    send_inputs([key_input(vk), key_input(vk, up=True)])


def hotkey(*vks: int) -> None:
    downs = [key_input(vk) for vk in vks]
    ups = [key_input(vk, up=True) for vk in reversed(vks)]
    send_inputs(downs + ups)


def parse_keys(spec: str) -> list[int]:
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("combinazione vuota")
    codes: list[int] = []
    for part in parts:
        if part not in VK:
            raise ValueError(tr("tasto sconosciuto: {key}").format(key=part))
        codes.append(VK[part])
    return codes


def type_text(text: str, *, newline: str = "enter", chunk: int = 48, pause: float = 0.012) -> None:
    batch: list[INPUT] = []

    def flush() -> None:
        nonlocal batch
        if batch:
            send_inputs(batch)
            batch = []
            time.sleep(pause)

    for char in text.replace("\r\n", "\n").replace("\r", "\n"):
        if char == "\n":
            flush()
            if newline == "shift_enter":
                hotkey(VK["shift"], VK["enter"])
            else:
                tap(VK["enter"])
            time.sleep(pause)
            continue
        if char == "\t":
            flush()
            tap(VK["tab"])
            continue
        data = char.encode("utf-16-le")
        for i in range(0, len(data), 2):
            unit = data[i] | (data[i + 1] << 8)
            batch.append(unicode_input(unit))
            batch.append(unicode_input(unit, up=True))
        if len(batch) >= chunk * 2:
            flush()
    flush()


def modifiers_held() -> bool:
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


def wait_modifiers_released(timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while modifiers_held():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.03)
    return True


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM) if sys.platform == "win32" else None
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
WS_EX_TOPMOST = 0x00000008
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
WM_CLOSE = 0x0010
DWMWA_CLOAKED = 14
PM_NOREMOVE = 0x0000
_MASK_KEY = 0xE8

if sys.platform == "win32":
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                    wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.LockWorkStation.argtypes = []
    user32.LockWorkStation.restype = wintypes.BOOL
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                                                 ctypes.POINTER(wintypes.DWORD)]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.GetCurrentProcessId.argtypes = []
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    if dwmapi is not None:
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    pid: int
    class_name: str

    @property
    def process_name(self) -> str:
        return process_name(self.pid)


def process_name(pid: int) -> str:
    try:
        import psutil

        return psutil.Process(pid).name()
    except Exception:
        return ""


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0, 0, 0, 0
    return rect.left, rect.top, rect.right, rect.bottom


def click(x: int, y: int, *, right: bool = False, double: bool = False) -> None:
    INPUT_MOUSE = 0
    down, up = (0x0008, 0x0010) if right else (0x0002, 0x0004)
    if not user32.SetCursorPos(int(x), int(y)):
        raise InputError(tr("Non riesco a spostare il mouse."))
    time.sleep(0.05)
    presses = []
    for _ in range(2 if double else 1):
        for flag in (down, up):
            presses.append(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flag, 0, 0))))
    send_inputs(presses)


MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
WHEEL_DELTA = 120


def scroll(*, dx: int = 0, dy: int = 0) -> None:
    INPUT_MOUSE = 0
    events: list[INPUT] = []
    if dy:
        events.append(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, ctypes.c_uint32(int(dy) * WHEEL_DELTA).value, MOUSEEVENTF_WHEEL, 0, 0)
        )))
    if dx:
        events.append(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, ctypes.c_uint32(int(dx) * WHEEL_DELTA).value, MOUSEEVENTF_HWHEEL, 0, 0)
        )))
    if events:
        send_inputs(events)


def window_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0, 0
    return rect.right - rect.left, rect.bottom - rect.top


def _cloaked(hwnd: int) -> bool:
    if dwmapi is None:
        return False
    value = wintypes.DWORD(0)
    result = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return result == 0 and value.value != 0


SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                           "Windows.UI.Core.CoreWindow"})


def top_windows() -> list[Window]:
    own_pid = kernel32.GetCurrentProcessId()
    found: list[Window] = []

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        try:
            if not hwnd or not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindow(hwnd, GW_OWNER):
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            title = window_title(hwnd)
            if not title or _cloaked(hwnd):
                return True
            pid = window_pid(hwnd)
            if pid == own_pid:
                return True
            class_name = window_class(hwnd)
            if class_name in SHELL_CLASSES:
                return True
            found.append(Window(int(hwnd), title, pid, class_name))
        except Exception:
            log.debug("window enumeration hiccup", exc_info=True)
        return True

    user32.EnumWindows(callback, 0)
    return found


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def _ensure_message_queue() -> None:
    msg = wintypes.MSG()
    user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)


def focus_window(hwnd: int, timeout: float = 1.5) -> bool:
    if not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.SetForegroundWindow(hwnd) and _wait_foreground(hwnd, 0.3):
        return True

    _ensure_message_queue()
    current = kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    foreground = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached: list[int] = []
    try:
        for thread in {fg_thread, target_thread}:
            if thread and thread != current and user32.AttachThreadInput(current, thread, True):
                attached.append(thread)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        for thread in attached:
            user32.AttachThreadInput(current, thread, False)
    if _wait_foreground(hwnd, 0.4):
        return True

    try:
        send_inputs([key_input(VK["alt"])])
        user32.SetForegroundWindow(hwnd)
        send_inputs([key_input(_MASK_KEY), key_input(_MASK_KEY, up=True)])
    finally:
        send_inputs([key_input(VK["alt"], up=True)])
    return _wait_foreground(hwnd, timeout)


def _wait_foreground(hwnd: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if foreground_window() == int(hwnd):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def close_window(hwnd: int) -> bool:
    return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def minimize_window(hwnd: int) -> bool:
    return bool(user32.ShowWindow(hwnd, SW_MINIMIZE))


def maximize_window(hwnd: int) -> bool:
    return bool(user32.ShowWindow(hwnd, SW_MAXIMIZE))


def restore_window(hwnd: int) -> bool:
    return bool(user32.ShowWindow(hwnd, SW_RESTORE))


def is_topmost(hwnd: int) -> bool:
    return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)


def set_topmost(hwnd: int, topmost: bool) -> bool:
    insert_after = wintypes.HWND(-1 if topmost else -2)
    return bool(user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))


def lock_workstation() -> bool:
    return bool(user32.LockWorkStation())


DESKTOP_READOBJECTS = 0x0001
UOI_NAME = 2


def input_desktop_available() -> bool:
    handle = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not handle:
        return False
    try:
        buffer = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD(0)
        if not user32.GetUserObjectInformationW(handle, UOI_NAME, buffer, ctypes.sizeof(buffer),
                                                ctypes.byref(needed)):
            return True
        return buffer.value.lower() == "default"
    finally:
        user32.CloseDesktop(handle)


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

if sys.platform == "win32":
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL


def _open_clipboard() -> None:
    for _ in range(20):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise OSError(tr("gli appunti sono occupati da un altro programma"))


def set_clipboard_text(text: str) -> None:
    data = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError(tr("memoria insufficiente per gli appunti"))
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise OSError(tr("impossibile preparare gli appunti"))
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    try:
        _open_clipboard()
    except OSError:
        kernel32.GlobalFree(handle)
        raise
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("impossibile scrivere negli appunti")
    finally:
        user32.CloseClipboard()


def get_clipboard_text() -> str:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return ""
    _open_clipboard()
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def clear_clipboard() -> None:
    _open_clipboard()
    try:
        user32.EmptyClipboard()
    finally:
        user32.CloseClipboard()


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


if sys.platform == "win32":
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_wchar_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

KNOWN_FOLDERS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


def known_folder(key: str) -> str | None:
    guid_text = KNOWN_FOLDERS.get(key)
    if guid_text is None:
        return None
    guid = GUID.from_buffer_copy(uuid.UUID(guid_text).bytes_le)
    path = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path))
    try:
        if result != 0:
            return None
        return path.value
    finally:
        if path:
            ole32.CoTaskMemFree(ctypes.cast(path, ctypes.c_void_p))


powrprof = None


def suspend() -> bool:
    global powrprof
    if powrprof is None:
        powrprof = ctypes.WinDLL("powrprof", use_last_error=True)
        powrprof.SetSuspendState.argtypes = [wintypes.BOOLEAN, wintypes.BOOLEAN, wintypes.BOOLEAN]
        powrprof.SetSuspendState.restype = wintypes.BOOLEAN
    return bool(powrprof.SetSuspendState(False, False, False))


SYNCHRONIZE = 0x00100000
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_TIMEOUT = 0x102
if sys.platform == "win32":
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    user32.WaitForInputIdle.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    user32.WaitForInputIdle.restype = wintypes.DWORD


def wait_input_idle(pid: int, timeout: float = 5.0) -> bool:
    handle = None
    for access in (SYNCHRONIZE | PROCESS_QUERY_INFORMATION, SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION):
        handle = kernel32.OpenProcess(access, False, pid)
        if handle:
            break
    if not handle:
        return False
    try:
        return user32.WaitForInputIdle(handle, max(0, int(timeout * 1000))) == 0
    finally:
        kernel32.CloseHandle(handle)


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
if sys.platform == "win32":
    shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    shell32.SHFileOperationW.restype = ctypes.c_int


def recycle(path: str) -> bool:
    op = SHFILEOPSTRUCTW(
        hwnd=None, wFunc=FO_DELETE, pFrom=path + "\0", pTo=None,
        fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
    )
    return shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004
if sys.platform == "win32":
    shell32.SHEmptyRecycleBinW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD]
    shell32.SHEmptyRecycleBinW.restype = ctypes.c_long


def empty_recycle_bin() -> bool:
    hr = shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
    return hr in (0, -2147418113)
