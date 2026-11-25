from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

_PREFIX = "dpapi:"
_ENTROPY = b"ressy.top/desktop/v1"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


if sys.platform == "win32":
    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def protect(plaintext: str) -> str:
    if not plaintext:
        return ""
    if sys.platform != "win32":
        return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    data_in, _keep1 = _blob(plaintext.encode("utf-8"))
    entropy, _keep2 = _blob(_ENTROPY)
    data_out = _Blob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(data_in), "Ressy", ctypes.byref(entropy), None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(data_out),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        encrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(data_out.pbData, ctypes.c_void_p))
    return _PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect(token: str) -> str:
    if not token:
        return ""
    if token.startswith("b64:"):
        return base64.b64decode(token[4:]).decode("utf-8")
    if not token.startswith(_PREFIX) or sys.platform != "win32":
        raise ValueError("unsupported secret format")
    raw = base64.b64decode(token[len(_PREFIX):])
    data_in, _keep1 = _blob(raw)
    entropy, _keep2 = _blob(_ENTROPY)
    data_out = _Blob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(data_in), None, ctypes.byref(entropy), None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(data_out),
    )
    if not ok:
        raise ValueError(f"cannot decrypt secret (WinError {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData).decode("utf-8")
    finally:
        _kernel32.LocalFree(ctypes.cast(data_out.pbData, ctypes.c_void_p))
