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


def make_version_file(name: str, original_filename: str, description: str) -> Path:
    sys.path.insert(0, str(DESKTOP))
    from ressy import __version__

    parts = [int(p) for p in __version__.split(".")[:3] if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    ver_tuple = f"({parts[0]}, {parts[1]}, {parts[2]}, {parts[3]})"
    ver_str = ".".join(str(p) for p in parts)
    BUILD.mkdir(parents=True, exist_ok=True)
    out = BUILD / f"version_{name.lower().replace('-', '_')}.txt"
    out.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Ressy Project (quervv/ressy)'),
         StringStruct('FileDescription', {description!r}),
         StringStruct('FileVersion', {ver_str!r}),
         StringStruct('InternalName', {name!r}),
         StringStruct('LegalCopyright', 'MIT License - Ressy Project'),
         StringStruct('OriginalFilename', {original_filename!r}),
         StringStruct('ProductName', 'Ressy'),
         StringStruct('ProductVersion', {ver_str!r})])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return out


EMBED_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
_DEV_SKIP_PREFIXES = (
    "pip", "setuptools", "wheel", "pkg_resources", "pytest", "_pytest", "pluggy", "iniconfig",
    "pyinstaller", "_pyinstaller_hooks_contrib", "altgraph", "pefile", "pywin32_ctypes", "__pycache__",
)


def build_signed_app(icon: Path) -> Path:
    import urllib.request

    embed_dir = BUILD / "py_embed"
    embed_dir.mkdir(parents=True, exist_ok=True)
    embed_zip = embed_dir / "python-3.12.10-embed-amd64.zip"
    if not embed_zip.is_file():
        urllib.request.urlretrieve(EMBED_URL, embed_zip)

    target = DIST / "Ressy"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(embed_zip) as zf:
        zf.extractall(target)

    for pth in target.glob("python*._pth"):
        pth.write_text("python312.zip\n.\napp\nimport site\n", encoding="utf-8")

    shutil.copy2(icon, target / "ressy.ico")
    app_dir = target / "app"
    app_dir.mkdir(parents=True, exist_ok=True)

    site_pkgs = Path(sys.executable).resolve().parents[1] / "Lib" / "site-packages"
    if not site_pkgs.is_dir():
        import site
        site_pkgs = Path(site.getsitepackages()[-1])
    for item in site_pkgs.iterdir():
        low = item.name.lower()
        if low.endswith(".pth") or any(
            low == p or low.startswith(p + "-") or low.startswith(p + "_") for p in _DEV_SKIP_PREFIXES
        ):
            continue
        dst = app_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "tests"))
        else:
            shutil.copy2(item, dst)

    shutil.copytree(DESKTOP / "ressy", app_dir / "ressy", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SERVER / "ressy_server", app_dir / "ressy_server", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if sys.platform == "win32" and csc.is_file():
        from ressy import __version__

        ver_parts = [p for p in __version__.split(".")[:3] if p.isdigit()]
        while len(ver_parts) < 4:
            ver_parts.append("0")
        ver_quad = ".".join(ver_parts)
        host_cs = BUILD / "RessyHost.cs"
        host_cs.write_text(
            f"""using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

[assembly: AssemblyTitle("Ressy")]
[assembly: AssemblyDescription("Ressy - Assistente Vocale AI")]
[assembly: AssemblyProduct("Ressy")]
[assembly: AssemblyCompany("Ressy Project")]
[assembly: AssemblyVersion("{ver_quad}")]
[assembly: AssemblyFileVersion("{ver_quad}")]

static class Program {{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool SetDllDirectory(string lpPathName);

    [DllImport("python312.dll", CallingConvention = CallingConvention.Cdecl)]
    static extern int Py_Main(int argc, IntPtr[] argv);

    [STAThread]
    static int Main(string[] args) {{
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        SetDllDirectory(baseDir);
        var pyArgs = new string[args.Length + 3];
        pyArgs[0] = Path.Combine(baseDir, "Ressy.exe");
        pyArgs[1] = "-m";
        pyArgs[2] = "ressy";
        Array.Copy(args, 0, pyArgs, 3, args.Length);
        IntPtr[] ptrs = new IntPtr[pyArgs.Length];
        for (int i = 0; i < pyArgs.Length; i++)
            ptrs[i] = Marshal.StringToHGlobalUni(pyArgs[i]);
        try {{
            return Py_Main(ptrs.Length, ptrs);
        }} finally {{
            for (int i = 0; i < ptrs.Length; i++) Marshal.FreeHGlobal(ptrs[i]);
        }}
    }}
}}
""",
            encoding="utf-8",
        )
        subprocess.run(
            [str(csc), "/nologo", "/platform:x64", "/target:winexe", "/optimize+", f"/win32icon:{icon}", f"/out:{target / 'Ressy.exe'}", str(host_cs)],
            check=True,
        )

    subprocess.run(
        [
            str(target / "python.exe"),
            "-c",
            "import ressy, ressy.app, ressy.tools.calls, ressy.tools.video, ressy_server, "
            "pywhispercpp.model, webrtcvad, sounddevice, miniaudio, edge_tts, discord, telegram, "
            "anthropic, httpx2, pynput; print('SIGNED_APP_OK')",
        ],
        check=True,
        cwd=target,
    )
    return target


def pyinstaller(icon: Path) -> Path:
    return build_signed_app(icon)


def setup_exe(icon: Path, payload: Path, out: Path) -> Path:
    sep = os.pathsep
    ver_file = make_version_file("Ressy-Setup", "Ressy-Setup.exe", "Programma di installazione di Ressy")
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--noupx", "--windowed", "--onefile",
        "--name", "Ressy-Setup",
        "--icon", str(icon),
        "--version-file", str(ver_file),
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
