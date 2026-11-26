from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import httpx

from ..paths import app_dir, user_folder
from ..speech.textnorm import normalize
from . import platform_os, screen, winapi
from .apps import _matching_windows, launch
from .registry import Tool, ToolContext, ToolError, params
from ..i18n import N_, language, tr

log = logging.getLogger("ressy.more")

CREATE_NO_WINDOW = 0x08000000
MAX_FILE_CHARS = 500_000
READ_LIMIT = 12_000

FOLDERS = {
    "desktop": "desktop", "scrivania": "desktop",
    "documenti": "documents", "documents": "documents",
    "download": "downloads", "downloads": "downloads", "scaricati": "downloads",
    "immagini": "pictures", "foto": "pictures", "pictures": "pictures",
    "musica": "music", "music": "music",
    "video": "videos", "videos": "videos",
}
_BAD_NAME = re.compile(r'[<>:"|?*\x00-\x1f]')


def _home() -> Path:
    return Path(os.path.expanduser("~")).resolve()


def resolve_path(name: str, folder: str = "") -> Path:
    name = name.strip().strip('"')
    if not name:
        raise ToolError(tr("Manca il nome del file."))
    if not folder.strip() and not Path(name).is_absolute():
        raw_name = name.replace("/", "\\") if sys.platform == "win32" else name
        name_parts = Path(raw_name).parts
        if len(name_parts) >= 2 and normalize(name_parts[0]) in FOLDERS:
            folder = name_parts[0]
            name = os.path.join(*name_parts[1:])
    key = normalize(folder) if folder else ""
    if key in FOLDERS:
        base = Path(winapi.known_folder(FOLDERS[key]) or _home() / "Desktop") if sys.platform == "win32" else user_folder(FOLDERS[key])
    elif folder.strip():
        raw_txt = folder.strip().strip('"')
        if sys.platform == "win32":
            raw_txt = raw_txt.replace("/", "\\")
        raw = Path(os.path.expandvars(os.path.expanduser(raw_txt)))
        if raw.is_absolute():
            base = raw
        else:
            first = normalize(raw.parts[0]) if raw.parts else ""
            if first in FOLDERS:
                first_base = Path(winapi.known_folder(FOLDERS[first]) or _home() / raw.parts[0]) if sys.platform == "win32" else user_folder(FOLDERS[first])
                base = first_base.joinpath(*raw.parts[1:])
            else:
                desktop_base = Path(winapi.known_folder("desktop") or _home() / "Desktop") if sys.platform == "win32" else user_folder("desktop")
                base = desktop_base / raw
    else:
        base = Path(winapi.known_folder("desktop") or _home() / "Desktop") if sys.platform == "win32" else user_folder("desktop")
    path = Path(name)
    was_absolute = path.is_absolute() or (folder.strip() and Path(os.path.expandvars(os.path.expanduser(folder.strip().strip('"')))).is_absolute())
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if any(_BAD_NAME.search(part) for part in path.parts[1:]):
        raise ToolError(tr("Il nome del file contiene caratteri non ammessi."))
    home = _home()
    low_parts = [p.lower() for p in path.parts]
    sys_dirs = {"windows", "program files", "program files (x86)", "programdata", "system32", "syswow64", "usr", "bin", "sbin", "etc", "var", "boot", "system"}
    if any(part in sys_dirs for part in low_parts[1:3]) or (len(path.parts) <= 1):
        raise ToolError(tr("Non modifico le cartelle di sistema del sistema operativo."))
    if not was_absolute and path != home and home not in path.parents:
        raise ToolError(tr("Per sicurezza creo e leggo file solo dentro la tua cartella utente."))
    if home in path.parents and any(part.lower() in ("appdata",) for part in path.relative_to(home).parts[:1]):
        raise ToolError(tr("Non tocco i file di sistema delle app (AppData)."))
    return path


def create_file(ctx: ToolContext, args: dict) -> str:
    content = args.get("content") or ""
    if len(content) > MAX_FILE_CHARS:
        raise ToolError(tr("Il contenuto è troppo lungo."))
    path = resolve_path(args["name"], args.get("folder") or "")
    if not path.suffix:
        path = path.with_suffix(".txt")
    mode = args.get("mode") or "create"
    if path.exists() and mode == "create":
        raise ToolError(tr("Esiste già un file {name}: dimmi se sovrascriverlo (overwrite) o aggiungere in fondo (append).").format(name=path.name))
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and path.exists():
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(("\n" if not content.startswith("\n") else "") + content)
        done = tr("Ho aggiunto il testo a {name} in {parent}.")
    else:
        encoding = "utf-8-sig" if path.suffix.lower() in (".txt", ".csv") else "utf-8"
        path.write_text(content, encoding=encoding, newline="")
        done = tr("Ho creato {name} in {parent}.")
    if args.get("open"):
        platform_os.open_path(path)
    return done.format(name=path.name, parent=path.parent)


_PLACES = {"desktop": (N_("sul Desktop"), N_("Desktop")), "documents": (N_("in Documenti"), N_("Documenti")),
           "downloads": (N_("in Download"), N_("Download")), "pictures": (N_("in Immagini"), N_("Immagini")),
           "music": (N_("in Musica"), N_("Musica")), "videos": (N_("in Video"), N_("Video"))}


def _known_places() -> list[tuple[Path, str, str]]:
    places = []
    for key, (said, shown) in _PLACES.items():
        known = winapi.known_folder(key) if sys.platform == "win32" else str(user_folder(key))
        if known:
            places.append((Path(known).resolve(), tr(said), tr(shown)))
    return places


def where(folder: Path) -> str:
    for base, said, shown in _known_places():
        if folder == base:
            return said
        if base in folder.parents:
            return f"in {shown}{os.sep}{folder.relative_to(base)}"
    return f"in {folder}"


def create_folder(ctx: ToolContext, args: dict) -> str:
    path = resolve_path(args["name"], args.get("folder") or "")
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if existed:
        return tr("La cartella {name} esisteva già {where}.").format(name=path.name, where=where(path.parent))
    return tr("La cartella {name} è stata creata {where}.").format(name=path.name, where=where(path.parent))


def file_action(ctx: ToolContext, args: dict) -> str:
    import shutil

    action = args["action"]
    source = resolve_path(args["name"], args.get("folder") or "")
    if not source.exists():
        raise ToolError(tr("Non trovo «{name}» {where}.").format(name=source.name, where=where(source.parent)))
    if action == "open":
        platform_os.open_path(source)
        kind = tr("la cartella") if source.is_dir() else tr("il file")
        return tr("Ho aperto {kind} {name}.").format(kind=kind, name=source.name)
    protected = {_home(), *(base for base, _, _ in _known_places())}
    if action in ("delete", "rename", "move") and (source in protected or (source.parent == _home() and source.is_dir())):
        raise ToolError(tr("È una delle cartelle principali del tuo utente: non la sposto e non la cancello."))
    kind = tr("la cartella") if source.is_dir() else tr("il file")
    if action == "delete":
        ok = winapi.recycle(str(source)) if sys.platform == "win32" else platform_os.unix_recycle(source)
        if not ok:
            raise ToolError(tr("Windows non mi ha permesso di cestinare {kind} {name}.").format(kind=kind, name=source.name))
        return tr("Ho spostato {kind} {name} nel Cestino (si può ripristinare da lì).").format(kind=kind, name=source.name)
    if action == "rename":
        new_name = (args.get("new_name") or "").strip()
        if not new_name or _BAD_NAME.search(new_name) or "\\" in new_name or "/" in new_name:
            raise ToolError(tr("Dimmi il nuovo nome (senza caratteri come / : * ?)."))
        if source.is_file() and not Path(new_name).suffix:
            new_name += source.suffix
        target = source.with_name(new_name)
        if target.exists():
            raise ToolError(tr("Esiste già qualcosa che si chiama {new_name} lì.").format(new_name=new_name))
        source.rename(target)
        return tr("Ho rinominato {kind} {name} in {name2}.").format(kind=kind, name=source.name, name2=target.name)
    if action == "zip":
        dest_dir = resolve_path(".", args["destination"]) if (args.get("destination") or "").strip() else source.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        archive_name = (args.get("new_name") or "").strip() or (source.stem if source.is_file() else source.name)
        if not archive_name.lower().endswith(".zip"):
            archive_name += ".zip"
        target = dest_dir / archive_name
        if target.exists():
            raise ToolError(tr("Esiste già l'archivio {name}.").format(name=target.name))
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            if source.is_file():
                zf.write(source, source.name)
            else:
                for root_dir, _, files in os.walk(source):
                    for fn in files:
                        full = Path(root_dir) / fn
                        zf.write(full, str(Path(source.name) / full.relative_to(source)))
        return tr("Ho compresso {name} in {archive}.").format(name=source.name, archive=target.name)
    if action == "unzip":
        if not source.is_file() or source.suffix.lower() != ".zip":
            raise ToolError(tr("{name} non è un archivio .zip.").format(name=source.name))
        dest_dir = (
            resolve_path(".", args["destination"])
            if (args.get("destination") or "").strip()
            else source.parent / source.stem
        )
        dest_dir.mkdir(parents=True, exist_ok=True)
        base_resolved = dest_dir.resolve()
        with zipfile.ZipFile(source, "r") as zf:
            for member in zf.infolist():
                member_path = (base_resolved / member.filename).resolve()
                if member_path != base_resolved and base_resolved not in member_path.parents:
                    raise ToolError(tr("L'archivio contiene percorsi non sicuri."))
            zf.extractall(base_resolved)
        return tr("Ho estratto {name} {where}.").format(name=source.name, where=where(dest_dir))
    destination = (args.get("destination") or "").strip()
    if not destination:
        raise ToolError(tr("In quale cartella devo metterlo?"))
    folder = resolve_path(".", destination)
    if folder == source or source in folder.parents:
        raise ToolError(tr("Non posso metterlo dentro se stesso."))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    if target.exists():
        raise ToolError(tr("In {name} c'è già {name2}.").format(name=folder.name, name2=target.name))
    if action == "move":
        shutil.move(str(source), str(target))
        return tr("Ho spostato {kind} {name} {where}.").format(kind=kind, name=source.name, where=where(folder))
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    return tr("Ho copiato {kind} {name} {where}.").format(kind=kind, name=source.name, where=where(folder))


_SKIP_SEARCH = {"appdata", "node_modules", ".git", "__pycache__", ".venv", "venv", "$recycle.bin", ".cache"}


def find_files(ctx: ToolContext, args: dict) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        raise ToolError(tr("Cosa devo cercare nei file?"))
    folder_arg = (args.get("folder") or "").strip()
    if folder_arg:
        roots = [resolve_path(".", folder_arg)]
    else:
        roots = [Path(p) for k in ("desktop", "documents", "downloads", "pictures", "music", "videos")
                 if (p := winapi.known_folder(k))]
        if not roots:
            roots = [_home()]
    q_low = query.lower().lstrip("*")
    q_norm = normalize(query)
    deadline = time.monotonic() + 2.5
    matches: list[tuple[int, float, Path]] = []
    seen: set[str] = set()
    queue: list[tuple[Path, int]] = [(r, 0) for r in roots if r.is_dir()]
    while queue and time.monotonic() < deadline and len(matches) < 25:
        folder, depth = queue.pop(0)
        key = os.path.normcase(str(folder.resolve()))
        if key in seen:
            continue
        seen.add(key)
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            low = entry.name.lower()
            if low in _SKIP_SEARCH or low.startswith("."):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                mtime = entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                continue
            if q_low in low or (q_norm and q_norm in normalize(entry.name)):
                rank = 0 if low == q_low else (1 if low.startswith(q_low) else 2)
                matches.append((rank, -mtime, Path(entry.path)))
            if is_dir and depth + 1 < 4:
                queue.append((Path(entry.path), depth + 1))
    if not matches:
        return tr("Non ho trovato nessun file o cartella per «{query}».").format(query=query)
    matches.sort(key=lambda item: (item[0], item[1], len(item[2].name)))
    if args.get("open"):
        best = matches[0][2]
        platform_os.open_path(best)
        return tr("Ho trovato e aperto {name} ({where}).").format(name=best.name, where=where(best.parent))
    lines = [f"- {p.name} ({where(p.parent)}) — {p}" for _, _, p in matches[:12]]
    return tr("Ho trovato {count} risultato/i:\n").format(count=len(matches)) + "\n".join(lines)


def _notes_path() -> Path:
    return app_dir() / "notes.json"


def _load_notes() -> list[dict[str, str]]:
    try:
        data = json.loads(_notes_path().read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("text")]
    except (OSError, ValueError):
        return []


def _save_notes(items: list[dict[str, str]]) -> None:
    tmp = _notes_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _notes_path())


def notes_tool(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    cat = (args.get("category") or "").strip().lower()
    items = _load_notes()
    if action == "add":
        text = (args.get("text") or "").strip()
        if not text:
            raise ToolError(tr("Cosa devo segnare?"))
        category = cat or "generale"
        items.append({"text": text, "category": category})
        _save_notes(items)
        if category == "generale":
            return tr("Segnato nelle note: {text}.").format(text=text)
        return tr("Segnato in {category}: {text}.").format(category=category, text=text)
    if action == "list":
        filtered = [i for i in items if not cat or i.get("category", "generale") == cat]
        if not filtered:
            return tr("Non ci sono note in {category}.").format(category=cat) if cat else tr("Non hai nessuna nota salvata.")
        lines = [
            f"- {i['text']}" + (f" [{i['category']}]" if not cat and i.get("category", "generale") != "generale" else "")
            for i in filtered
        ]
        return tr("Ecco le note:\n") + "\n".join(lines)
    if action == "remove":
        wanted = normalize(args.get("text") or "")
        if not wanted:
            raise ToolError(tr("Quale nota devo togliere?"))
        remaining = []
        removed_text = ""
        for item in items:
            if not removed_text and (not cat or item.get("category", "generale") == cat) and (
                wanted in normalize(item["text"])
            ):
                removed_text = item["text"]
                continue
            remaining.append(item)
        if not removed_text:
            raise ToolError(tr("Non trovo quella nota."))
        _save_notes(remaining)
        return tr("Ho tolto «{text}» dalle note.").format(text=removed_text)
    if action == "clear":
        if cat:
            remaining = [i for i in items if i.get("category", "generale") != cat]
            _save_notes(remaining)
            return tr("Ho svuotato la lista {category}.").format(category=cat)
        _save_notes([])
        return tr("Ho cancellato tutte le note.")
    raise ToolError(tr("Azione non valida per le note."))


def wait(ctx: ToolContext, args: dict) -> str:
    from .apps import wait_until_ready

    app = (args.get("app") or "").strip()
    if app:
        seconds = max(1.0, min(90.0, float(args.get("seconds") or 60)))
        window = wait_until_ready(app, set(), seconds)
        if window is None:
            raise ToolError(tr("{app} non si è aperto entro {int} secondi.").format(app=app, int=int(seconds)))
        return tr("{app} è aperto e pronto.").format(app=app)
    seconds = float(args.get("seconds") or 0)
    if seconds <= 0:
        raise ToolError(tr("Quanti secondi devo aspettare?"))
    seconds = min(seconds, 120.0)
    time.sleep(seconds)
    return tr("Ho aspettato {seconds:g} secondi.").format(seconds=seconds)


def read_file(ctx: ToolContext, args: dict) -> str:
    path = resolve_path(args["name"], args.get("folder") or "")
    if not path.is_file():
        raise ToolError(tr("Non trovo il file {name}.").format(name=path.name))
    if path.stat().st_size > 5_000_000:
        raise ToolError(tr("Il file è troppo grande da leggere."))
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise ToolError(tr("Non è un file di testo."))
    text = data.decode("utf-8-sig", errors="replace")
    more = f"\n[… altri {len(text) - READ_LIMIT} caratteri]" if len(text) > READ_LIMIT else ""
    return tr("Contenuto di {name}:\n{value}{more}").format(name=path.name, value=text[:READ_LIMIT], more=more)


def list_folder(ctx: ToolContext, args: dict) -> str:
    path = resolve_path(args.get("name") or ".", args.get("folder") or "desktop")
    if not path.is_dir():
        raise ToolError(tr("Non è una cartella."))
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    names = [(p.name + "\\") if p.is_dir() else p.name for p in entries[:60]]
    more = f" (e altri {len(entries) - 60})" if len(entries) > 60 else ""
    return tr("In {path}: ").format(path=path) + (", ".join(names) if names else "vuota") + more


def _wait_window(name: str, timeout: float) -> winapi.Window | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = [w for w in _matching_windows(name) if winapi.window_size(w.hwnd)[0] > 200]
        if windows:
            return windows[0]
        time.sleep(0.4)
    return None


def write_in_app(ctx: ToolContext, args: dict) -> str:
    app = args["app"].strip()
    text = args["text"]
    if len(text) > 20_000:
        raise ToolError(tr("Testo troppo lungo."))
    if sys.platform != "win32":
        window = _wait_window(app, 0)
        if window is None:
            entry, alternatives = ctx.services.apps.find(app)
            if entry is None:
                names = ", ".join(a.name for a in alternatives[:4])
                raise ToolError(tr("Non trovo l'app '{app}'.").format(app=app) + (tr(" Forse: {names}?").format(names=names) if names else ""))
            launch(entry)
            window = _wait_window(app, 25)
            if window is None:
                raise ToolError(tr("{app} non si è aperto in tempo.").format(app=app))
            time.sleep(1.2)
        platform_os.unix_focus_window(window.hwnd, window.class_name)
        time.sleep(0.35)
        mod = platform_os.mod_key()
        if args.get("new_document"):
            platform_os.send_hotkey(mod, "n")
            time.sleep(1.0)
        platform_os.type_text(text)
        time.sleep(0.25)
        if args.get("press_enter"):
            platform_os.tap_key("enter")
            time.sleep(0.2)
        if args.get("save_as"):
            platform_os.send_hotkey(mod, "s")
            time.sleep(1.0)
            platform_os.type_text(args["save_as"], newline="enter")
            platform_os.tap_key("enter")
            time.sleep(0.6)
        return tr("Ho scritto il testo in {app}.").format(app=app)
    if not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato: non posso scrivere finché non viene sbloccato."))
    window = _wait_window(app, 0)
    if window is None:
        entry, alternatives = ctx.services.apps.find(app)
        if entry is None:
            builtin = {"blocco note": "notepad.exe", "notepad": "notepad.exe", "wordpad": "write.exe"}.get(normalize(app))
            if builtin is None:
                names = ", ".join(a.name for a in alternatives[:4])
                raise ToolError(tr("Non trovo l'app '{app}'.").format(app=app) + (tr(" Forse: {names}?").format(names=names) if names else ""))
            os.startfile(builtin)
        else:
            launch(entry)
        window = _wait_window(app, 25)
        if window is None:
            raise ToolError(tr("{app} non si è aperto in tempo.").format(app=app))
        time.sleep(1.5)
    winapi.wait_modifiers_released()
    if not winapi.focus_window(window.hwnd):
        raise ToolError(tr("Non riesco a portare {app} in primo piano.").format(app=app))
    time.sleep(0.4)
    if args.get("new_document"):
        winapi.hotkey(winapi.VK["ctrl"], winapi.VK["n"])
        time.sleep(1.2)
    target = winapi.foreground_window()
    if len(text) > 400:
        winapi.set_clipboard_text(text)
        winapi.hotkey(winapi.VK["ctrl"], winapi.VK["v"])
    else:
        winapi.type_text(text)
    time.sleep(0.3)
    if winapi.foreground_window() != target:
        raise ToolError(tr("{app} ha perso il focus mentre scrivevo: controlla il testo.").format(app=app))
    if args.get("press_enter"):
        winapi.tap(winapi.VK["enter"])
        time.sleep(0.2)
    if args.get("save_as"):
        winapi.hotkey(winapi.VK["ctrl"], winapi.VK["s"])
        time.sleep(1.2)
        winapi.type_text(args["save_as"], newline="enter")
        winapi.tap(winapi.VK["enter"])
        time.sleep(0.8)
    title = winapi.window_title(winapi.foreground_window())
    return tr("Ho scritto il testo in «{value}».").format(value=title[:60]) if title else tr("Ho scritto il testo in {app}.").format(app=app)


def read_screen(ctx: ToolContext, args: dict) -> str:
    if not screen.ocr_available():
        raise ToolError(tr("Il riconoscimento del testo sullo schermo non è disponibile."))
    region = None
    if args.get("app"):
        windows = _matching_windows(args["app"])
        if not windows:
            raise ToolError(tr("Non vedo finestre di '{value}'.").format(value=args['app']))
        if sys.platform == "win32":
            region = winapi.window_rect(windows[0].hwnd)
        else:
            platform_os.unix_focus_window(windows[0].hwnd, windows[0].class_name)
            time.sleep(0.25)
    lines = screen.read_text(region)
    text = "\n".join(line.text for line in lines)
    if not text.strip():
        return tr("Non leggo testo sullo schermo.")
    return tr("Testo visibile (OCR, può contenere errori):\n") + text[:READ_LIMIT]


def click_text(ctx: ToolContext, args: dict) -> str:
    wanted = args["text"].strip()
    if not wanted:
        raise ToolError(tr("Cosa devo cliccare?"))
    if not screen.ocr_available():
        raise ToolError(tr("Il riconoscimento del testo sullo schermo non è disponibile."))
    if sys.platform != "win32":
        region = None
        if args.get("app"):
            windows = _matching_windows(args["app"])
            if not windows:
                raise ToolError(tr("Non vedo finestre di '{value}'.").format(value=args['app']))
            platform_os.unix_focus_window(windows[0].hwnd, windows[0].class_name)
            time.sleep(0.35)
        found = screen.find_text(screen.read_text(region), wanted, threshold=0.8)
        if found is None:
            raise ToolError(tr("Non vedo «{wanted}» sullo schermo.").format(wanted=wanted))
        _score, line, (x, y) = found
        platform_os.click_mouse(x, y, double=bool(args.get("double")), right=bool(args.get("right")))
        time.sleep(0.5)
        return tr("Ho cliccato su «{value}».").format(value=line.text[:60])
    if not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato."))
    region = None
    if args.get("app"):
        windows = _matching_windows(args["app"])
        if not windows:
            raise ToolError(tr("Non vedo finestre di '{value}'.").format(value=args['app']))
        winapi.focus_window(windows[0].hwnd)
        time.sleep(0.4)
        region = winapi.window_rect(windows[0].hwnd)
    found = screen.find_text(screen.read_text(region), wanted, threshold=0.8)
    if found is None:
        raise ToolError(tr("Non vedo «{wanted}» sullo schermo.").format(wanted=wanted))
    score, line, (x, y) = found
    winapi.click(x, y, double=bool(args.get("double")), right=bool(args.get("right")))
    time.sleep(0.5)
    return tr("Ho cliccato su «{value}».").format(value=line.text[:60])


WEATHER_CODES = {
    0: N_("sereno"), 1: N_("quasi sereno"), 2: N_("parzialmente nuvoloso"), 3: N_("nuvoloso"), 45: N_("nebbia"), 48: N_("nebbia con brina"),
    51: N_("pioviggine leggera"), 53: N_("pioviggine"), 55: N_("pioviggine intensa"), 56: N_("pioviggine gelata"), 57: N_("pioviggine gelata"),
    61: N_("pioggia leggera"), 63: N_("pioggia"), 65: N_("pioggia forte"), 66: N_("pioggia gelata"), 67: N_("pioggia gelata forte"),
    71: N_("neve leggera"), 73: N_("neve"), 75: N_("neve forte"), 77: N_("nevischio"), 80: N_("rovesci leggeri"), 81: N_("rovesci"),
    82: N_("rovesci violenti"), 85: N_("rovesci di neve"), 86: N_("forti rovesci di neve"), 95: N_("temporale"),
    96: N_("temporale con grandine"), 99: N_("temporale con grandine forte"),
}


def _place_cache() -> Path:
    return app_dir() / "place.json"


def _geocode(city: str) -> tuple[float, float, str]:
    response = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": language(), "format": "json"},
        timeout=8,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ToolError(tr("Non trovo la città «{city}».").format(city=city))
    r = results[0]
    label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
    return float(r["latitude"]), float(r["longitude"]), label


def _home_place(ctx: ToolContext) -> tuple[float, float, str]:
    city = (getattr(ctx.services.settings, "home_city", "") or "").strip()
    if city:
        return _geocode(city)
    cache = _place_cache()
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        if time.time() - data.get("at", 0) < 7 * 86400:
            return float(data["lat"]), float(data["lon"]), data["label"]
    except (OSError, ValueError, KeyError):
        pass
    response = httpx.get("https://ipapi.co/json/", timeout=8, headers={"User-Agent": "Ressy"})
    response.raise_for_status()
    data = response.json()
    if "latitude" not in data:
        raise ToolError(tr("Non so dove sei: dimmi la città."))
    label = ", ".join(x for x in (data.get("city"), data.get("region")) if x) or tr("la tua zona")
    place = {"lat": data["latitude"], "lon": data["longitude"], "label": label, "at": time.time()}
    try:
        cache.write_text(json.dumps(place), encoding="utf-8")
    except OSError:
        pass
    return float(place["lat"]), float(place["lon"]), label


def weather(ctx: ToolContext, args: dict) -> str:
    try:
        if args.get("city"):
            lat, lon, label = _geocode(args["city"])
        else:
            lat, lon, label = _home_place(ctx)
        days = max(1, min(7, int(args.get("days") or 2)))
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": days,
            },
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise ToolError(tr("Il servizio meteo non risponde, riprova tra poco.")) from exc
    cur = data["current"]
    sky = WEATHER_CODES.get(int(cur["weather_code"]))
    parts = [
        tr("Meteo a {label} adesso: {sky}, {temp}°C (percepiti {feels}°C), umidità {humidity}%, vento {wind} km/h.").format(
            label=label, sky=tr(sky) if sky else tr("condizioni variabili"), temp=round(cur["temperature_2m"]),
            feels=round(cur["apparent_temperature"]), humidity=cur["relative_humidity_2m"],
            wind=round(cur["wind_speed_10m"]))
    ]
    daily = data["daily"]
    names = [tr("oggi"), tr("domani")]
    for i, day in enumerate(daily["time"]):
        when = names[i] if i < 2 else dt.date.fromisoformat(day).strftime(tr("%d/%m"))
        rain = daily["precipitation_probability_max"][i]
        sky = WEATHER_CODES.get(int(daily["weather_code"][i]))
        parts.append(
            tr("{capitalize}: {get}, min {round}° max {round2}°").format(capitalize=when.capitalize(), get=tr(sky) if sky else tr("variabile"), round=round(daily['temperature_2m_min'][i]), round2=round(daily['temperature_2m_max'][i]))
            + (tr(", pioggia {rain}%").format(rain=rain) if rain is not None else "")
            + "."
        )
    return " ".join(parts)


_DANGEROUS = re.compile(
    r"(format-volume|\bformat\s+[a-z]:|diskpart|clear-disk|initialize-disk|remove-partition|bcdedit|"
    r"cipher\s+/w|vssadmin|wbadmin|reg\s+delete\s+hklm|remove-item[^|;]*\s-recurse[^|;]*\s([a-z]:\\?\s*$|[a-z]:\\windows|\$env:systemroot)|"
    r"rd\s+/s|rmdir\s+/s|del\s+/[sq]|set-mppreference|disable-windowsoptionalfeature|stop-computer|restart-computer|"
    r"invoke-webrequest[^|;]*\|\s*iex|iex\s*\(|downloadstring|-encodedcommand|\-enc\s)",
    re.IGNORECASE,
)


def run_powershell(ctx: ToolContext, args: dict) -> str:
    command = args["command"].strip()
    if not command:
        raise ToolError(tr("Comando vuoto."))
    if len(command) > 16_000:
        raise ToolError(tr("Comando troppo lungo."))
    if sys.platform != "win32":
        log.info("unix shell: %d characters", len(command))
        try:
            rc, out, err = platform_os.run_unix_shell(command, _home(), timeout=120)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolError(tr("Il comando ha impiegato più di 120 secondi ed è stato interrotto.")) from exc
        text = out[:READ_LIMIT] or tr("(nessun output)")
        if rc != 0:
            raise ToolError(tr("Il comando è fallito (codice {returncode}): {value}").format(returncode=rc, value=(err or out)[:1500]))
        return text + (tr("\n[avvisi: {value}]").format(value=err[:500]) if err else "")
    if _DANGEROUS.search(command):
        raise ToolError(tr("Questo comando può danneggiare il PC o i dati: non lo eseguo. Fallo tu se sei sicuro."))
    log.info("powershell: %d characters", len(command))
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command],
            capture_output=True,
            timeout=120,
            creationflags=CREATE_NO_WINDOW,
            cwd=str(_home()),
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(tr("Il comando ha impiegato più di 120 secondi ed è stato interrotto.")) from exc
    out = result.stdout.decode("utf-8", errors="replace").strip()
    err = result.stderr.decode("utf-8", errors="replace").strip()
    text = out[:READ_LIMIT] or tr("(nessun output)")
    if result.returncode != 0:
        raise ToolError(tr("Il comando è fallito (codice {returncode}): {value}").format(returncode=result.returncode, value=(err or out)[:1500]))
    return text + (tr("\n[avvisi: {value}]").format(value=err[:500]) if err else "")


_PY_DANGEROUS = re.compile(
    r"(shutil\.rmtree\s*\(\s*['\"](?:[a-zA-Z]:\\\\|/)['\"]|os\.system\s*\(\s*['\"](?:format|diskpart|rm\s+-rf\s+/))",
    re.IGNORECASE,
)


def run_python(ctx: ToolContext, args: dict) -> str:
    import tempfile

    code = (args.get("code") or "").rstrip()
    if not code:
        raise ToolError(tr("Manca il codice Python da eseguire."))
    if len(code) > 25_000:
        raise ToolError(tr("Codice Python troppo lungo."))
    if _PY_DANGEROUS.search(code):
        raise ToolError(tr("Questo script può danneggiare il sistema: non lo eseguo."))
    timeout = max(5, min(180, int(args.get("timeout") or 120)))
    cwd = _home()
    if args.get("workdir"):
        cand = Path(os.path.expandvars(os.path.expanduser(str(args["workdir"])))).resolve()
        if cand.is_dir():
            cwd = cand
    fd, tmp_name = tempfile.mkstemp(prefix="ressy-py-", suffix=".py")
    os.close(fd)
    script = Path(tmp_name)
    try:
        script.write_text(code, encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            cwd=str(cwd),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(tr("Lo script Python ha superato il limite di tempo ({s}s).").format(s=timeout)) from exc
    finally:
        script.unlink(missing_ok=True)
    out = result.stdout.decode("utf-8", errors="replace").strip()
    err = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        raise ToolError(tr("Lo script Python è fallito (codice {returncode}): {value}").format(returncode=result.returncode, value=(err or out)[:1500]))
    return (out[:READ_LIMIT] or tr("(eseguito senza output)")) + (tr("\n[avvisi: {value}]").format(value=err[:500]) if err else "")


def download_file(ctx: ToolContext, args: dict) -> str:
    from .web import _check_public_host, normalize_url

    url = normalize_url(args.get("url") or "")
    _check_public_host(url)
    name = (args.get("filename") or "").strip()
    if not name:
        tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        name = tail if tail and "." in tail else "download.bin"
    folder = (args.get("folder") or "download").strip()
    dst = resolve_path(name, folder)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    max_bytes = 500 * 1024 * 1024
    written = 0
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0),
                          headers={"User-Agent": "Ressy/1.3"}) as r:
            _check_public_host(str(r.url))
            r.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in r.iter_bytes(65536):
                    written += len(chunk)
                    if written > max_bytes:
                        raise ToolError(tr("File troppo grande (massimo 500 MB)."))
                    fh.write(chunk)
        os.replace(tmp, dst)
    except httpx.HTTPError as exc:
        raise ToolError(tr("Download non riuscito: {err}").format(err=exc)) from exc
    finally:
        tmp.unlink(missing_ok=True)
    if args.get("open"):
        platform_os.open_path(dst)
    size_mb = written / 1_048_576
    return tr("Ho scaricato {name} ({size:.1f} MB) in {folder}.").format(name=dst.name, size=size_mb, folder=dst.parent)


TOOLS = [
    Tool(
        "create_file",
        "Crea un file (txt, md, csv, html, py, json…) nelle cartelle utente. open=true lo apre.",
        params(
            {
                "name": {"type": "string"},
                "content": {"type": "string"},
                "folder": {"type": "string", "description": "desktop (default), documenti, download o percorso"},
                "mode": {"type": "string", "enum": ["create", "overwrite", "append"]},
                "open": {"type": "boolean"},
            },
            ["name", "content"],
        ),
        create_file,
    ),
    Tool(
        "create_folder",
        "Crea una cartella (default Desktop).",
        params({"name": {"type": "string"}, "folder": {"type": "string"}}, ["name"]),
        create_folder,
    ),
    Tool(
        "file_action",
        "Rinomina, sposta, copia, cestina, apre, comprime o estrae file/cartella.",
        params(
            {
                "action": {"type": "string", "enum": ["rename", "move", "copy", "delete", "zip", "unzip", "open"]},
                "name": {"type": "string"},
                "folder": {"type": "string"},
                "new_name": {"type": "string"},
                "destination": {"type": "string"},
            },
            ["action", "name"],
        ),
        file_action,
        timeout=120,
    ),
    Tool(
        "find_files",
        "Cerca file o cartelle nelle cartelle utente (open=true apre il primo).",
        params(
            {
                "query": {"type": "string"},
                "folder": {"type": "string"},
                "open": {"type": "boolean"},
            },
            ["query"],
        ),
        find_files,
    ),
    Tool(
        "notes",
        "Note rapide e liste: add, list, remove, clear.",
        params(
            {
                "action": {"type": "string", "enum": ["add", "list", "remove", "clear"]},
                "text": {"type": "string"},
                "category": {"type": "string"},
            },
            ["action"],
        ),
        notes_tool,
    ),
    Tool(
        "wait",
        "Attende seconds (1-120) o apertura app.",
        params({"seconds": {"type": "number"}, "app": {"type": "string"}}),
        wait,
        timeout=130,
    ),
    Tool(
        "read_file",
        "Legge un file di testo dell'utente.",
        params({"name": {"type": "string"}, "folder": {"type": "string"}}, ["name"]),
        read_file,
    ),
    Tool(
        "list_folder",
        "Elenca i file di una cartella (desktop, documenti, download o percorso).",
        params({"folder": {"type": "string"}, "name": {"type": "string"}}),
        list_folder,
    ),
    Tool(
        "write_in_app",
        "Apre o usa un'app (Blocco note, Word, WhatsApp...) e ci scrive text.",
        params(
            {
                "app": {"type": "string"},
                "text": {"type": "string"},
                "new_document": {"type": "boolean"},
                "press_enter": {"type": "boolean"},
                "save_as": {"type": "string"},
            },
            ["app", "text"],
        ),
        write_in_app,
        timeout=120,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "read_screen",
        "Legge il testo visibile sullo schermo o in un'app.",
        params({"app": {"type": "string"}}),
        read_screen,
    ),
    Tool(
        "click_text",
        "Clicca un testo o pulsante visibile sullo schermo.",
        params(
            {
                "text": {"type": "string"},
                "app": {"type": "string"},
                "double": {"type": "boolean"},
                "right": {"type": "boolean"},
            },
            ["text"],
        ),
        click_text,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "weather",
        "Meteo attuale e previsioni.",
        params({"city": {"type": "string"}, "days": {"type": "integer"}}),
        weather,
        timeout=25,
    ),
    Tool(
        "run_powershell",
        "Esegue comandi PowerShell (Windows) o shell per automazioni e controlli.",
        params({"command": {"type": "string"}}, ["command"]),
        run_powershell,
        timeout=130,
    ),
    Tool(
        "run_python",
        "Esegue script Python sul PC (file, grafici, PDF, media, conversioni, automazioni).",
        params(
            {
                "code": {"type": "string"},
                "workdir": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            ["code"],
        ),
        run_python,
        timeout=190,
    ),
    Tool(
        "download_file",
        "Scarica un file da URL in Download o folder.",
        params(
            {
                "url": {"type": "string"},
                "filename": {"type": "string"},
                "folder": {"type": "string"},
                "open": {"type": "boolean"},
            },
            ["url"],
        ),
        download_file,
        timeout=130,
    ),
]
