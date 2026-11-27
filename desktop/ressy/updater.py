from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from . import __version__
from .i18n import tr

log = logging.getLogger("ressy.update")

REPO = "quervv/ressy"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "Ressy-Setup.exe"
_HEADERS = {"User-Agent": f"Ressy/{__version__} (+https://ressy.top)", "Accept": "application/vnd.github+json"}

Progress = Callable[[int, int], None]


@dataclass
class Release:
    version: str
    url: str
    size: int
    sha256: str
    notes: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    if not a or not b:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def release_from(data: dict) -> Release | None:
    if data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name") or "").lstrip("v")
    for asset in data.get("assets") or []:
        if asset.get("name") != ASSET:
            continue
        digest = str(asset.get("digest") or "")
        url = str(asset.get("browser_download_url") or "")
        if not digest.startswith("sha256:") or not url.startswith(f"https://github.com/{REPO}/releases/download/"):
            return None
        return Release(version, url, int(asset.get("size") or 0), digest.split(":", 1)[1].lower(),
                       str(data.get("body") or ""))
    return None


def can_update() -> bool:
    from .paths import is_frozen

    return is_frozen() and sys.platform == "win32"


def check(timeout: float = 15.0) -> Release | None:
    try:
        response = httpx.get(LATEST_URL, headers=_HEADERS, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        release = release_from(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        log.info("update check failed: %s", exc)
        return None
    if release is None or not is_newer(release.version):
        return None
    log.info("update available: %s (running %s)", release.version, __version__)
    return release


def download(release: Release, progress: Progress | None = None, cancel: threading.Event | None = None) -> Path:
    folder = Path(tempfile.gettempdir()) / "Ressy-Update"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"Ressy-Setup-{release.version}.exe"
    part = target.with_suffix(".part")
    digest = hashlib.sha256()
    done = 0
    try:
        with httpx.stream("GET", release.url, headers={"User-Agent": _HEADERS["User-Agent"]},
                          follow_redirects=True, timeout=httpx.Timeout(30.0, connect=15.0)) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or release.size or 0)
            with part.open("wb") as fh:
                for chunk in response.iter_bytes(1 << 16):
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError("aggiornamento annullato")
                    fh.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
        if digest.hexdigest() != release.sha256:
            raise OSError(tr("il file scaricato non corrisponde a quello pubblicato: riprova più tardi"))
        os.replace(part, target)
        return target
    finally:
        part.unlink(missing_ok=True)


def install(setup: Path) -> None:
    from .install import DETACHED_PROCESS

    subprocess.Popen([str(setup), "--update"], creationflags=DETACHED_PROCESS, close_fds=True)
