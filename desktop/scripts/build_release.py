from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DESKTOP = Path(__file__).resolve().parents[1]
REPO = DESKTOP.parent
BUILD = DESKTOP / "build"
DIST = DESKTOP / "dist"

HIDDEN = [
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "PySide6.QtSvg",
]
COLLECT = [
    "edge_tts", "webrtcvad", "_sounddevice_data", "miniaudio",
    "winrt",
    "pywhispercpp",
    "anthropic", "httpx2",
    "discord",
]
SERVER = REPO / "server"
SUBMODULES = ["ressy_server", "telegram", "aiosqlite"]
DATA = ["tzdata", "certifi"]
SETUP_EXCLUDES = ["edge_tts", "telegram", "discord", "aiosqlite", "pynput", "PIL", "qrcode", "psutil", "winrt"]
SETUP_COLLECT = ["_sounddevice_data", "webrtcvad", "pywhispercpp", "anthropic", "httpx2"]

SOURCE_SKIP_DIRS = {
    ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", ".git", ".impeccable",
    ".claude", "download", "data", "node_modules",
}
SOURCE_SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".sqlite3", ".db", ".spec"}
SOURCE_SKIP_NAMES = {".env", "config.json"}


def make_icon() -> Path:
    sys.path.insert(0, str(DESKTOP))
    from PySide6.QtGui import QGuiApplication

    from ressy.ui import logo, theme

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    theme.family()
    BUILD.mkdir(parents=True, exist_ok=True)
    icon = BUILD / "ressy.ico"
    logo.save_ico(str(icon))
    del app
    return icon


def pyinstaller(icon: Path) -> Path:
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", "Ressy",
        "--icon", str(icon),
        "--workpath", str(BUILD / "pyinstaller"),
        "--distpath", str(DIST),
        "--specpath", str(BUILD),
        "--add-data", f"{DESKTOP / 'ressy' / 'assets'}{sep}ressy/assets",
        "--paths", str(SERVER),
    ]
    for name in HIDDEN:
        args += ["--hidden-import", name]
    for name in COLLECT:
        args += ["--collect-all", name]
    for name in SUBMODULES:
        args += ["--collect-submodules", name]
    for name in DATA:
        args += ["--collect-data", name]
    args.append(str(DESKTOP / "ressy" / "__main__.py"))
    subprocess.run(args, check=True, cwd=DESKTOP)
    exe = DIST / "Ressy" / "Ressy.exe"
    if not exe.exists():
        raise SystemExit(f"build failed: {exe} missing")
    return DIST / "Ressy"


def setup_exe(icon: Path, payload: Path, out: Path) -> Path:
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "Ressy-Setup",
        "--icon", str(icon),
        "--workpath", str(BUILD / "pyinstaller-setup"),
        "--distpath", str(DIST),
        "--specpath", str(BUILD),
        "--paths", str(DESKTOP),
        "--add-data", f"{DESKTOP / 'ressy' / 'assets'}{sep}ressy/assets",
        "--add-data", f"{payload}{sep}payload",
        "--hidden-import", "PySide6.QtSvg",
    ]
    for name in SETUP_EXCLUDES:
        args += ["--exclude-module", name]
    for name in SETUP_COLLECT:
        args += ["--collect-all", name]
    args.append(str(DESKTOP / "installer" / "setup_app.py"))
    subprocess.run(args, check=True, cwd=DESKTOP)
    exe = DIST / "Ressy-Setup.exe"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, out)
    return out


def zip_tree(folder: Path, target: Path, arc_root: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, f"{arc_root}/{path.relative_to(folder).as_posix()}")
    tmp.replace(target)


def source_files() -> list[Path]:
    files = []
    for path in sorted(REPO.rglob("*")):
        rel = path.relative_to(REPO)
        if any(part in SOURCE_SKIP_DIRS for part in rel.parts):
            continue
        if not path.is_file() or path.suffix in SOURCE_SKIP_SUFFIXES or path.name in SOURCE_SKIP_NAMES:
            continue
        files.append(path)
    return files


def zip_source(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in source_files():
            zf.write(path, f"ressy/{path.relative_to(REPO).as_posix()}")
    tmp.replace(target)


def tar_unix(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with tarfile.open(tmp, "w:gz") as tf:
        for path in source_files():
            arc = f"ressy/{path.relative_to(REPO).as_posix()}"
            info = tf.gettarinfo(str(path), arcname=arc)
            info.mode = 0o755 if path.suffix == ".sh" else 0o644
            with path.open("rb") as fh:
                tf.addfile(info, fh)
    tmp.replace(target)


def main() -> None:
    web = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO / "web"
    out = web / "download"
    icon = make_icon()
    app_dir = pyinstaller(icon)
    zip_tree(app_dir, out / "Ressy-win64.zip", "Ressy")
    setup_exe(icon, out / "Ressy-win64.zip", out / "Ressy-Setup.exe")
    tar_unix(out / "Ressy-unix.tar.gz")
    zip_source(out / "Ressy-source.zip")
    for name in ("Ressy-Setup.exe", "Ressy-win64.zip", "Ressy-unix.tar.gz", "Ressy-source.zip"):
        size = (out / name).stat().st_size / 1_048_576
        print(f"wrote {out / name} ({size:.1f} MB)")
    shutil.rmtree(BUILD / "pyinstaller", ignore_errors=True)
    shutil.rmtree(BUILD / "pyinstaller-setup", ignore_errors=True)


if __name__ == "__main__":
    main()
