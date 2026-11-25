from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from . import theme

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> int:
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return r | (g << 8) | (b << 16)


def style_title_bar(widget) -> None:
    if sys.platform != "win32":
        return
    try:
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hwnd = wintypes.HWND(int(widget.winId()))
        dark = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), ctypes.sizeof(dark))
        caption = wintypes.DWORD(_colorref(theme.PLATE))
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption))
        text = wintypes.DWORD(_colorref(theme.LEGEND))
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text))
    except (OSError, AttributeError, ValueError):
        pass
