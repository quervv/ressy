from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..speech.textnorm import normalize, similarity
from . import platform_os, winapi
from .registry import Tool, ToolContext, ToolError, params
from ..i18n import tr

log = logging.getLogger("ressy.apps")

CREATE_NO_WINDOW = 0x08000000
MAX_AGE_S = 6 * 3600

ALIASES: dict[str, list[str]] = {
    "chrome": ["Google Chrome"],
    "cromo": ["Google Chrome"],
    "google": ["Google Chrome"],
    "edge": ["Microsoft Edge"],
    "firefox": ["Firefox", "Mozilla Firefox"],
    "vscode": ["Visual Studio Code"],
    "vs code": ["Visual Studio Code"],
    "visual studio code": ["Visual Studio Code"],
    "code": ["Visual Studio Code"],
    "word": ["Word"],
    "excel": ["Excel"],
    "powerpoint": ["PowerPoint"],
    "outlook": ["Outlook", "Outlook (new)"],
    "teams": ["Microsoft Teams", "Teams"],
    "blocco note": ["Blocco note", "Notepad"],
    "blocconote": ["Blocco note", "Notepad"],
    "notepad": ["Blocco note", "Notepad"],
    "calcolatrice": ["Calcolatrice", "Calculator"],
    "calculator": ["Calcolatrice", "Calculator"],
    "impostazioni": ["Impostazioni", "Settings"],
    "settings": ["Impostazioni", "Settings"],
    "esplora file": ["Esplora file", "File Explorer"],
    "esplora risorse": ["Esplora file", "File Explorer"],
    "gestione risorse": ["Esplora file", "File Explorer"],
    "file explorer": ["Esplora file", "File Explorer"],
    "gestione attivita": ["Gestione attività", "Task Manager"],
    "task manager": ["Gestione attività", "Task Manager"],
    "terminale": ["Terminale", "Terminal", "Windows Terminal"],
    "terminal": ["Terminale", "Terminal", "Windows Terminal"],
    "prompt dei comandi": ["Prompt dei comandi", "Command Prompt"],
    "telegram": ["Telegram Desktop", "Telegram"],
    "whatsapp": ["WhatsApp"],
    "uozzap": ["WhatsApp"],
    "wazzap": ["WhatsApp"],
    "discord": ["Discord", "Discord Canary", "Discord PTB"],
    "discorso": ["Discord", "Discord Canary", "Discord PTB"],
    "discordia": ["Discord", "Discord Canary", "Discord PTB"],
    "discordo": ["Discord", "Discord Canary", "Discord PTB"],
    "capcut": ["CapCut"],
    "cap cut": ["CapCut"],
    "capcat": ["CapCut"],
    "davinci": ["DaVinci Resolve"],
    "davinci resolve": ["DaVinci Resolve"],
    "resolve": ["DaVinci Resolve"],
    "spotify": ["Spotify"],
    "spotifai": ["Spotify"],
    "spotifi": ["Spotify"],
    "obs": ["OBS Studio"],
    "store": ["Microsoft Store"],
    "foto": ["Foto", "Photos"],
    "orologio": ["Orologio", "Clock"],
    "sveglia": ["Orologio", "Clock"],
    "posta": ["Posta", "Outlook", "Mail"],
    "camera": ["Fotocamera", "Camera"],
    "fotocamera": ["Fotocamera", "Camera"],
}

BUILTINS: dict[str, str] = {
    "blocco note": "notepad.exe",
    "notepad": "notepad.exe",
    "calcolatrice": "calc.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "esplora file": "explorer.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "gestione attivita": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "prompt dei comandi": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "pannello di controllo": "control.exe",
    "control panel": "control.exe",
    "impostazioni": "ms-settings:",
    "settings": "ms-settings:",
}

PROCESS_ALIASES: dict[str, list[str]] = {
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
    "outlook": ["outlook.exe", "olk.exe"],
    "teams": ["ms-teams.exe", "teams.exe"],
    "vscode": ["code.exe"],
    "visual studio code": ["code.exe"],
    "discord": ["discord.exe", "discordptb.exe", "discordcanary.exe"],
    "discord canary": ["discordcanary.exe"],
    "discord ptb": ["discordptb.exe"],
    "discorso": ["discord.exe", "discordptb.exe", "discordcanary.exe"],
    "capcut": ["capcut.exe", "capcut"],
    "cap cut": ["capcut.exe", "capcut"],
    "davinci": ["resolve.exe", "resolve"],
    "davinci resolve": ["resolve.exe", "resolve"],
    "spotify": ["spotify.exe"],
    "spotifai": ["spotify.exe"],
    "telegram": ["telegram.exe"],
    "whatsapp": ["whatsapp.exe", "whatsapp.root.exe"],
    "steam": ["steam.exe", "steamwebhelper.exe"],
    "blocco note": ["notepad.exe"],
    "notepad": ["notepad.exe"],
    "calcolatrice": ["calculatorapp.exe"],
    "calculator": ["calculatorapp.exe"],
    "obs": ["obs64.exe"],
}

PROTECTED = frozenset(
    {
        "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
        "lsass.exe", "svchost.exe", "dwm.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe",
        "lockapp.exe", "logonui.exe", "searchhost.exe", "startmenuexperiencehost.exe",
        "shellexperiencehost.exe", "textinputhost.exe", "runtimebroker.exe", "taskhostw.exe",
        "securityhealthsystray.exe", "msmpeng.exe",
    }
)
NEVER_KILL = frozenset({"explorer.exe"})

_NOISE = ("disinstalla", "uninstall", "readme", "leggimi", "guida", "help", "documentation", "documentazione",
          "sito web", "website", "release notes", "changelog", "promozione", "license", "licenza")


@dataclass(frozen=True)
class AppEntry:
    name: str
    app_id: str

    @property
    def norm(self) -> str:
        return normalize(self.name)


def _score(query: str, entry_norm: str) -> float:
    if not query or not entry_norm:
        return 0.0
    if query == entry_norm:
        return 1.0
    q_tokens, e_tokens = query.split(), entry_norm.split()
    score = similarity(query, entry_norm)
    if entry_norm.startswith(query + " "):
        score = max(score, 0.93 - 0.01 * (len(e_tokens) - len(q_tokens)))
    if all(t in e_tokens for t in q_tokens):
        score = max(score, 0.9 - 0.02 * (len(e_tokens) - len(q_tokens)))
    elif len(q_tokens) == 1 and len(query) >= 4:
        best_token = max((similarity(query, t) for t in e_tokens), default=0.0)
        score = max(score, best_token * 0.88)
    if any(noise in entry_norm and noise not in query for noise in _NOISE):
        score *= 0.5
    return score


_GAME_URL = ("com.epicgames.launcher://", "steam://")
_STEAM_TOOLS = ("steamworks", "redistributable", "proton", "steam linux runtime", "directx", "vcredist")


def _epic_games() -> list[AppEntry]:
    folder = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Epic/EpicGamesLauncher/Data/Manifests"
    games: list[AppEntry] = []
    for item in sorted(folder.glob("*.item")) if folder.is_dir() else []:
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name, app = str(data.get("DisplayName") or "").strip(), str(data.get("AppName") or "").strip()
        namespace, item_id = str(data.get("CatalogNamespace") or ""), str(data.get("CatalogItemId") or "")
        if not name or not app or data.get("bIsIncompleteInstall"):
            continue
        if data.get("MainGameAppName") and data.get("MainGameAppName") != app:
            continue
        target = f"{namespace}%3A{item_id}%3A{app}" if namespace and item_id else app
        games.append(AppEntry(name, f"com.epicgames.launcher://apps/{target}?action=launch&silent=true"))
    return games


def _steam_root() -> Path | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
            if path.is_dir():
                return path
    except OSError:
        pass
    default = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
    return default if default.is_dir() else None


def _steam_games() -> list[AppEntry]:
    root = _steam_root()
    if root is None:
        return []
    libraries = {root}
    try:
        vdf = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libraries.update(Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', vdf))
    except OSError:
        pass
    games: list[AppEntry] = []
    for library in libraries:
        for manifest in (library / "steamapps").glob("appmanifest_*.acf"):
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            name = re.search(r'"name"\s+"([^"]+)"', text)
            appid = re.search(r'"appid"\s+"(\d+)"', text)
            if not name or not appid or any(t in name.group(1).lower() for t in _STEAM_TOOLS):
                continue
            games.append(AppEntry(name.group(1), f"steam://rungameid/{appid.group(1)}"))
    return games


_NOT_APPS = ("uninstall", "disinstalla", "readme", "leggimi", "help", "guida", "manual", "license", "licenza",
             "website", "sito web", "release notes", "changelog", "documentation", "documentazione")


def _shortcut_roots() -> list[Path]:
    env = os.environ.get
    roots = [
        Path(env("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(env("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(env("APPDATA", "")) / "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar",
        Path(env("PUBLIC", r"C:\Users\Public")) / "Desktop",
        Path(env("USERPROFILE", "")) / "Desktop",
    ]
    desktop = winapi.known_folder("desktop") if hasattr(winapi, "known_folder") else None
    if desktop:
        roots.append(Path(desktop))
    out: list[Path] = []
    for root in roots:
        if str(root) not in {str(r) for r in out} and root.is_dir():
            out.append(root)
    return out


def scan_shortcuts(roots: list[Path] | None = None, max_depth: int = 4) -> list[AppEntry]:
    apps: list[AppEntry] = []
    seen: set[str] = set()
    for root in _shortcut_roots() if roots is None else roots:
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            if len(Path(dirpath).parts) - base_depth >= max_depth:
                dirnames[:] = []
            for filename in filenames:
                stem, ext = os.path.splitext(filename)
                if ext.lower() not in (".lnk", ".url") or any(w in stem.lower() for w in _NOT_APPS):
                    continue
                entry = AppEntry(stem.strip(), os.path.join(dirpath, filename))
                if entry.norm and entry.norm not in seen:
                    seen.add(entry.norm)
                    apps.append(entry)
    return apps


def installed_games() -> list[AppEntry]:
    games: list[AppEntry] = []
    for source in (_epic_games, _steam_games):
        try:
            games += source()
        except Exception:
            log.debug("game scan failed (%s)", source.__name__, exc_info=True)
    return games


class AppIndex:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._apps: list[AppEntry] = []
        self._loaded_at = 0.0
        self._lock = threading.Lock()
        self._refreshing = threading.Lock()
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            apps = [AppEntry(a["name"], a["app_id"]) for a in raw.get("apps", []) if a.get("name") and a.get("app_id")]
            with self._lock:
                self._apps = apps
                self._loaded_at = float(raw.get("loaded_at", 0))
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _save_cache(self) -> None:
        try:
            data = {"loaded_at": self._loaded_at, "apps": [{"name": a.name, "app_id": a.app_id} for a in self._apps]}
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.cache_path)
        except OSError:
            log.warning("could not save the app cache", exc_info=True)

    @staticmethod
    def _query_start_apps() -> list[AppEntry]:
        command = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        text = result.stdout.decode("utf-8-sig", errors="replace").strip()
        if not text:
            return []
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        apps: list[AppEntry] = []
        for item in data:
            name, app_id = str(item.get("Name") or "").strip(), str(item.get("AppID") or "").strip()
            if name and app_id:
                apps.append(AppEntry(name, app_id))
        return apps

    @staticmethod
    def _scan_start_menu() -> list[AppEntry]:
        roots = [
            Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        apps: list[AppEntry] = []
        for root in roots:
            if root.is_dir():
                for lnk in root.rglob("*.lnk"):
                    apps.append(AppEntry(lnk.stem, str(lnk)))
        return apps

    def refresh(self) -> int:
        if not self._refreshing.acquire(blocking=False):
            return len(self._apps)
        try:
            if sys.platform != "win32":
                apps = [AppEntry(name, target) for name, target in platform_os.find_unix_apps()]
            else:
                try:
                    apps = self._query_start_apps()
                except Exception:
                    log.warning("Get-StartApps failed, scanning the Start menu folders", exc_info=True)
                    apps = []
                if not apps:
                    apps = self._scan_start_menu()
                known = {a.norm for a in apps}
                for source in (installed_games, scan_shortcuts):
                    try:
                        extra = source()
                    except Exception:
                        log.debug("app source failed (%s)", source.__name__, exc_info=True)
                        continue
                    for entry in extra:
                        if entry.norm and entry.norm not in known:
                            known.add(entry.norm)
                            apps.append(entry)
            if apps:
                with self._lock:
                    self._apps = apps
                    self._loaded_at = time.time()
                self._save_cache()
            log.info("app index: %d entries", len(apps))
            return len(apps)
        finally:
            self._refreshing.release()

    def ensure_fresh(self, max_age: float = MAX_AGE_S) -> None:
        if not self._apps or time.time() - self._loaded_at > max_age:
            self.refresh()

    @property
    def apps(self) -> list[AppEntry]:
        with self._lock:
            return list(self._apps)

    def search(self, query: str, limit: int = 5) -> list[tuple[float, AppEntry]]:
        q = normalize(query)
        if not q:
            return []
        targets = [normalize(t) for t in ALIASES.get(q, [])] or [q]
        scored: list[tuple[float, AppEntry]] = []
        for entry in self.apps:
            norm = entry.norm
            score = max(_score(t, norm) for t in targets)
            if targets != [q]:
                score = max(score, _score(q, norm) * 0.95)
            if score > 0.45:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], len(item[1].name), item[1].name))
        return scored[:limit]

    def find(self, query: str) -> tuple[AppEntry | None, list[AppEntry]]:
        results = self.search(query)
        best_score = results[0][0] if results else 0.0
        if best_score < 0.72 and time.time() - self._loaded_at > 60:
            self.refresh()
            results = self.search(query)
        if not results:
            return None, []
        best_score, best = results[0]
        if best_score >= 0.72:
            return best, [e for _, e in results[1:]]
        return None, [e for _, e in results]


def launch(entry: AppEntry) -> None:
    target = entry.app_id
    if sys.platform != "win32":
        platform_os.launch_unix_target(target)
        return
    if target.lower().endswith((".lnk", ".url", ".exe")) and os.path.isfile(target):
        os.startfile(target)
        return
    if target.startswith(_GAME_URL):
        os.startfile(target)
        return
    if re.match(r"^[a-zA-Z]:\\", target) and Path(target).exists():
        os.startfile(target)
        return
    subprocess.Popen(
        ["explorer.exe", f"shell:AppsFolder\\{target}"], creationflags=CREATE_NO_WINDOW
    )


def _launch_builtin(query: str) -> str | None:
    if sys.platform != "win32":
        mac_builtins = {
            "calcolatrice": "Calculator", "calculator": "Calculator",
            "impostazioni": "System Settings", "settings": "System Settings",
            "blocco note": "TextEdit", "blocconote": "TextEdit", "notepad": "TextEdit",
            "terminale": "Terminal", "terminal": "Terminal",
        }
        linux_builtins = {
            "calcolatrice": "gnome-calculator", "calculator": "gnome-calculator",
            "terminale": "x-terminal-emulator", "terminal": "x-terminal-emulator",
            "impostazioni": "gnome-control-center", "settings": "gnome-control-center",
        }
        table = mac_builtins if sys.platform == "darwin" else linux_builtins
        cmd = table.get(normalize(query))
        if cmd:
            platform_os.launch_unix_target(cmd)
        return cmd
    command = BUILTINS.get(normalize(query))
    if command is None:
        return None
    os.startfile(command)
    return command


def _matching_windows(name: str) -> list[winapi.Window]:
    q = normalize(name)
    if not q:
        return []
    if sys.platform != "win32":
        q_tokens = q.split()
        out: list[winapi.Window] = []
        for item in platform_os.unix_top_windows():
            pnorm = normalize(str(item.get("process") or ""))
            tnorm = normalize(str(item.get("title") or ""))
            if pnorm == q or similarity(pnorm.replace(" ", ""), q.replace(" ", "")) >= 0.85 or all(t in tnorm.split() for t in q_tokens):
                out.append(winapi.Window(hwnd=int(item["handle"]), title=str(item["title"]), pid=int(item["pid"]), class_name=str(item["process"])))
        return out
    exe_names = {e.lower() for e in PROCESS_ALIASES.get(q, [])}
    q_tokens = q.split()
    matches: list[winapi.Window] = []
    for window in winapi.top_windows():
        proc = window.process_name.lower()
        proc_norm = normalize(proc.removesuffix(".exe"))
        title_norm = normalize(window.title)
        title_tokens = title_norm.split()
        if proc in exe_names:
            matches.append(window)
        elif proc_norm and (proc_norm == q or similarity(proc_norm, q.replace(" ", "")) >= 0.85):
            matches.append(window)
        elif all(t in title_tokens for t in q_tokens):
            matches.append(window)
    return matches


def _describe(window: winapi.Window) -> str:
    proc = window.process_name.removesuffix(".exe") or "?"
    return f"{proc}: {window.title[:80]}"


READY_TIMEOUT_S = 20.0
READY_AGAIN_S = 4.0


def _real_window(window: winapi.Window) -> bool:
    if sys.platform != "win32":
        return "updater" not in window.title.lower()
    width, height = winapi.window_size(window.hwnd)
    return width >= 240 and height >= 160 and "updater" not in window.title.lower()


def wait_until_ready(name: str, before: set[int], timeout: float = READY_TIMEOUT_S) -> winapi.Window | None:
    deadline = time.monotonic() + timeout
    while True:
        windows = [w for w in _matching_windows(name) if _real_window(w)]
        fresh = [w for w in windows if w.hwnd not in before]
        if sys.platform != "win32":
            if fresh:
                return fresh[0]
            if windows:
                return windows[0]
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.35)
            continue
        front = winapi.foreground_window()
        ready = fresh[0] if fresh else next((w for w in windows if w.hwnd == front), None)
        if ready is not None:
            winapi.wait_input_idle(ready.pid, max(0.5, min(5.0, deadline - time.monotonic())))
            return ready
        if time.monotonic() >= deadline:
            return windows[0] if windows else None
        time.sleep(0.3)


def _bring_up(name: str, before: set[int], timeout: float) -> bool:
    window = wait_until_ready(name, before, timeout)
    if window is None:
        return False
    if sys.platform != "win32":
        platform_os.unix_focus_window(window.hwnd, window.class_name)
        time.sleep(0.3)
        return True
    if winapi.input_desktop_available() and winapi.foreground_window() != window.hwnd:
        winapi.focus_window(window.hwnd)
    time.sleep(0.5)
    return True


def open_app(ctx: ToolContext, args: dict) -> str:
    name = args["name"].strip()
    index = ctx.services.apps
    entry, alternatives = index.find(name)
    if entry is not None:
        before = {w.hwnd for w in _matching_windows(entry.name)}
        launch(entry)
        if entry.app_id.startswith(_GAME_URL):
            return tr("Ho avviato {name}: il gioco si apre tra poco.").format(name=entry.name)
        if _bring_up(entry.name, before, READY_AGAIN_S if before else READY_TIMEOUT_S):
            return tr("Ho aperto {name}: è pronto.").format(name=entry.name)
        return tr("Ho avviato {name}, ma la sua finestra non si vede ancora (forse è nell'area di notifica).").format(name=entry.name)
    before = {w.hwnd for w in _matching_windows(name)}
    builtin = _launch_builtin(name)
    if builtin is not None:
        if _bring_up(name, before, READY_AGAIN_S if before else 8.0):
            return tr("Ho aperto {name}: è pronto.").format(name=name)
        return tr("Ho avviato {name}.").format(name=name)
    if alternatives:
        names = ", ".join(a.name for a in alternatives[:4])
        raise ToolError(tr("Non ho trovato '{name}' con certezza. Forse intendevi: {names}?").format(name=name, names=names))
    raise ToolError(tr("Non trovo nessun programma chiamato '{name}' nel menu Start.").format(name=name))


def close_app(ctx: ToolContext, args: dict) -> str:
    import psutil

    name = args["name"].strip()
    force = bool(args.get("force"))
    windows = [w for w in _matching_windows(name) if w.process_name.lower() not in PROTECTED]
    pids = {w.pid for w in windows}
    if force and not pids:
        q = normalize(name)
        exe_names = {e.lower() for e in PROCESS_ALIASES.get(q, [])} or {q.replace(" ", "") + ".exe"}
        for proc in psutil.process_iter(["pid", "name"]):
            pname = (proc.info.get("name") or "").lower()
            if pname in exe_names:
                pids.add(proc.info["pid"])
    if not windows and not pids:
        raise ToolError(tr("Non vedo finestre aperte di '{name}'.").format(name=name))

    own = os.getpid()
    if sys.platform != "win32":
        for window in windows:
            platform_os.unix_close_window(window.hwnd, window.class_name)
        if not force:
            time.sleep(1.2)
            still = [w for w in _matching_windows(name)]
            if still:
                return tr("Ho chiesto a {name} di chiudersi, ma {len} finestra/e è ancora aperta (forse chiede di salvare). Posso forzare la chiusura se vuoi, perdendo le modifiche non salvate.").format(name=name, len=len(still))
            return tr("Ho chiuso {name}.").format(name=name)
    else:
        for window in windows:
            winapi.close_window(window.hwnd)
        if not force:
            time.sleep(1.5)
            still = [w for w in windows if winapi.user32.IsWindow(w.hwnd) and winapi.user32.IsWindowVisible(w.hwnd)]
            if still:
                return (
                    tr("Ho chiesto a {name} di chiudersi, ma {len} finestra/e è ancora aperta (forse chiede di salvare). Posso forzare la chiusura se vuoi, perdendo le modifiche non salvate.").format(name=name, len=len(still))
                )
            alive = [pid for pid in pids if psutil.pid_exists(pid)]
            if alive:
                return tr("Ho chiuso le finestre di {name}; il programma resta attivo in background (area di notifica).").format(name=name)
            return tr("Ho chiuso {name}.").format(name=name)

    killed = 0
    for pid in pids:
        if pid == own:
            continue
        try:
            proc = psutil.Process(pid)
            pname = proc.name().lower()
            if pname in PROTECTED or pname in NEVER_KILL:
                continue
            proc.terminate()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not killed and not windows:
        raise ToolError(tr("Non sono riuscita a chiudere {name} (permessi insufficienti?).").format(name=name))
    return tr("Ho chiuso {name} forzatamente.").format(name=name)


def list_windows(ctx: ToolContext, args: dict) -> str:
    if sys.platform != "win32":
        wins = platform_os.unix_top_windows()
        if not wins:
            return tr("Non ci sono finestre aperte.")
        return tr("Finestre aperte:\n") + "\n".join(f"{w['process']}: {w['title'][:80]}" for w in wins[:25])
    windows = winapi.top_windows()
    if not windows:
        return tr("Non ci sono finestre aperte.")
    lines = [_describe(w) for w in windows[:25]]
    return tr("Finestre aperte:\n") + "\n".join(lines)


def _pick_target_window(app_name: str = "") -> winapi.Window:
    if app_name.strip():
        windows = _matching_windows(app_name)
        real = [w for w in windows if _real_window(w)]
        chosen = real[0] if real else (windows[0] if windows else None)
        if chosen is None:
            raise ToolError(tr("Non vedo finestre aperte di '{name}'.").format(name=app_name))
        return chosen
    if sys.platform != "win32":
        wins = platform_os.unix_top_windows()
        front_item = next((w for w in wins if w.get("front")), wins[0] if wins else None)
        if front_item is None:
            raise ToolError(tr("Non c'è nessuna finestra attiva."))
        return winapi.Window(hwnd=int(front_item["handle"]), title=str(front_item["title"]), pid=int(front_item["pid"]), class_name=str(front_item["process"]))
    hwnd = winapi.foreground_window()
    if not hwnd:
        raise ToolError(tr("Non c'è nessuna finestra attiva."))
    title = winapi.window_title(hwnd) or tr("la finestra attiva")
    return winapi.Window(hwnd=hwnd, title=title, pid=winapi.window_pid(hwnd), class_name=winapi.window_class(hwnd))


def focus_app(ctx: ToolContext, args: dict) -> str:
    name = args["name"].strip()
    windows = _matching_windows(name)
    if not windows:
        raise ToolError(tr("Non vedo finestre aperte di '{name}'.").format(name=name))
    if sys.platform != "win32":
        target = windows[0]
        if platform_os.unix_focus_window(target.hwnd, target.class_name):
            return tr("Ho portato in primo piano {value}.").format(value=target.title[:60])
        raise ToolError(tr("Windows non mi ha permesso di portare la finestra in primo piano."))
    if not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato: non posso cambiare finestra finché non viene sbloccato."))
    real = [w for w in windows if _real_window(w)]
    front = winapi.foreground_window()
    ordered = real or windows
    target = ordered[1] if len(ordered) > 1 and ordered[0].hwnd == front else ordered[0]
    if winapi.focus_window(target.hwnd):
        return tr("Ho portato in primo piano {value}.").format(value=target.title[:60])
    raise ToolError(tr("Windows non mi ha permesso di portare la finestra in primo piano."))


def window_action(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    app_name = (args.get("app") or "").strip()
    if sys.platform != "win32":
        if action == "switch_next":
            platform_os.send_hotkey("cmd" if sys.platform == "darwin" else "alt", "tab")
            return tr("Sono passata alla finestra precedente.")
        if action == "minimize_all":
            if sys.platform == "darwin":
                platform_os.send_hotkey("f11")
            else:
                platform_os.send_hotkey("super", "d")
            return tr("Ho mostrato il desktop riducendo a icona le finestre.")
        window = _pick_target_window(app_name)
        label = window.title[:50] or app_name or tr("la finestra")
        platform_os.unix_focus_window(window.hwnd, window.class_name)
        if action == "minimize":
            if sys.platform == "darwin":
                platform_os.send_hotkey("cmd", "m")
            else:
                platform_os.send_hotkey("alt", "f9")
            return tr("Ho ridotto a icona {label}.").format(label=label)
        if action == "maximize":
            if sys.platform == "darwin":
                platform_os.send_hotkey("ctrl", "cmd", "f")
            else:
                platform_os.send_hotkey("super", "up")
            return tr("Ho ingrandito {label}.").format(label=label)
        if action == "fullscreen":
            if sys.platform == "darwin":
                platform_os.send_hotkey("ctrl", "cmd", "f")
            else:
                platform_os.tap_key("f11")
            return tr("Ho attivato o tolto lo schermo intero su {label}.").format(label=label)
        if action == "snap_left":
            platform_os.send_hotkey("super" if sys.platform != "darwin" else "ctrl", "left")
            return tr("Ho affiancato {label} a sinistra.").format(label=label)
        if action == "snap_right":
            platform_os.send_hotkey("super" if sys.platform != "darwin" else "ctrl", "right")
            return tr("Ho affiancato {label} a destra.").format(label=label)
        return tr("Ho ripristinato {label}.").format(label=label)
    if not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato: non posso gestire le finestre finché non viene sbloccato."))
    if action == "minimize_all":
        winapi.wait_modifiers_released()
        winapi.hotkey(winapi.VK["win"], winapi.VK["d"])
        return tr("Ho mostrato il desktop riducendo a icona le finestre.")
    if action == "switch_next":
        winapi.wait_modifiers_released()
        winapi.hotkey(winapi.VK["alt"], winapi.VK["tab"])
        return tr("Sono passata alla finestra precedente.")

    window = _pick_target_window(app_name)
    label = window.title[:50] or app_name or tr("la finestra")
    if action == "minimize":
        winapi.minimize_window(window.hwnd)
        return tr("Ho ridotto a icona {label}.").format(label=label)
    if action == "maximize":
        winapi.focus_window(window.hwnd)
        winapi.maximize_window(window.hwnd)
        return tr("Ho ingrandito {label}.").format(label=label)
    if action == "restore":
        winapi.restore_window(window.hwnd)
        winapi.focus_window(window.hwnd)
        return tr("Ho ripristinato {label}.").format(label=label)
    if action == "always_on_top":
        pin = not winapi.is_topmost(window.hwnd)
        winapi.set_topmost(window.hwnd, pin)
        if pin:
            return tr("Tengo sempre in primo piano {label}.").format(label=label)
        return tr("{label} non è più fissata in primo piano.").format(label=label)
    if action in ("snap_left", "snap_right"):
        if not winapi.focus_window(window.hwnd):
            raise ToolError(tr("Non riesco a portare {label} in primo piano.").format(label=label))
        winapi.wait_modifiers_released()
        time.sleep(0.15)
        arrow = "left" if action == "snap_left" else "right"
        winapi.hotkey(winapi.VK["win"], winapi.VK[arrow])
        time.sleep(0.25)
        winapi.tap(winapi.VK["esc"])
        if action == "snap_left":
            return tr("Ho affiancato {label} a sinistra.").format(label=label)
        return tr("Ho affiancato {label} a destra.").format(label=label)
    if action == "fullscreen":
        if not winapi.focus_window(window.hwnd):
            raise ToolError(tr("Non riesco a portare {label} in primo piano.").format(label=label))
        winapi.wait_modifiers_released()
        time.sleep(0.15)
        winapi.tap(winapi.VK["f11"])
        return tr("Ho attivato o tolto lo schermo intero su {label}.").format(label=label)
    raise ToolError(tr("Azione finestra non valida."))


TOOLS = [
    Tool(
        "open_app",
        "Avvia un programma o un'app installata (es. Spotify, Discord, Calcolatrice, Word).",
        params({"name": {"type": "string", "description": "nome del programma"}}, ["name"]),
        open_app,
        timeout=40,
        uses_screen=True,
    ),
    Tool(
        "close_app",
        "Chiude un programma aperto. force=true lo termina anche se resta in background o non risponde.",
        params(
            {"name": {"type": "string"}, "force": {"type": "boolean", "description": "chiusura forzata"}},
            ["name"],
        ),
        close_app,
    ),
    Tool("list_windows", "Elenca le finestre aperte sul PC.", params(), list_windows),
    Tool(
        "focus_app",
        "Porta in primo piano la finestra di un programma già aperto.",
        params({"name": {"type": "string"}}, ["name"]),
        focus_app,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "window_action",
        "Gestisce le finestre per il multitasking: minimize, maximize, restore, snap_left, snap_right, "
        "minimize_all, always_on_top, fullscreen, switch_next.",
        params(
            {
                "action": {
                    "type": "string",
                    "enum": [
                        "minimize", "maximize", "restore", "snap_left", "snap_right",
                        "minimize_all", "always_on_top", "fullscreen", "switch_next",
                    ],
                },
                "app": {"type": "string", "description": "nome app (opzionale: default finestra attiva)"},
            },
            ["action"],
        ),
        window_action,
        snapshot_on_error=True,
        uses_screen=True,
    ),
]
