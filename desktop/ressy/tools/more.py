from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

import httpx

from ..paths import app_dir
from ..speech.textnorm import normalize
from . import screen, winapi
from .apps import _matching_windows, launch
from .registry import Tool, ToolContext, ToolError, params

log = logging.getLogger("ressy.more")

CREATE_NO_WINDOW = 0x08000000
MAX_FILE_CHARS = 200_000
READ_LIMIT = 6000

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
        raise ToolError("Manca il nome del file.")
    key = normalize(folder) if folder else ""
    if key in FOLDERS:
        base = Path(winapi.known_folder(FOLDERS[key]) or _home() / "Desktop")
    elif folder.strip():
        raw = Path(os.path.expandvars(os.path.expanduser(folder.strip().strip('"').replace("/", "\\"))))
        if raw.is_absolute():
            base = raw
        else:
            first = normalize(raw.parts[0]) if raw.parts else ""
            if first in FOLDERS:
                base = Path(winapi.known_folder(FOLDERS[first]) or _home() / raw.parts[0]).joinpath(*raw.parts[1:])
            else:
                base = Path(winapi.known_folder("desktop") or _home() / "Desktop") / raw
    else:
        base = Path(winapi.known_folder("desktop") or _home() / "Desktop")
    path = Path(name)
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if any(_BAD_NAME.search(part) for part in path.parts[1:]):
        raise ToolError("Il nome del file contiene caratteri non ammessi.")
    home = _home()
    if path != home and home not in path.parents:
        raise ToolError("Per sicurezza creo e leggo file solo dentro la tua cartella utente.")
    if any(part.lower() in ("appdata",) for part in path.relative_to(home).parts[:1]):
        raise ToolError("Non tocco i file di sistema delle app (AppData).")
    return path


def create_file(ctx: ToolContext, args: dict) -> str:
    content = args.get("content") or ""
    if len(content) > MAX_FILE_CHARS:
        raise ToolError("Il contenuto è troppo lungo.")
    path = resolve_path(args["name"], args.get("folder") or "")
    if not path.suffix:
        path = path.with_suffix(".txt")
    mode = args.get("mode") or "create"
    if path.exists() and mode == "create":
        raise ToolError(f"Esiste già un file {path.name}: dimmi se sovrascriverlo (overwrite) o aggiungere in fondo (append).")
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and path.exists():
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(("\n" if not content.startswith("\n") else "") + content)
        verb = "Ho aggiunto il testo a"
    else:
        encoding = "utf-8-sig" if path.suffix.lower() in (".txt", ".csv") else "utf-8"
        path.write_text(content, encoding=encoding, newline="")
        verb = "Ho creato"
    if args.get("open"):
        os.startfile(str(path))
    return f"{verb} {path.name} in {path.parent}."


def create_folder(ctx: ToolContext, args: dict) -> str:
    path = resolve_path(args["name"], args.get("folder") or "")
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    return f"La cartella {path.name} {'esisteva già' if existed else 'è stata creata'} in {path.parent}."


def read_file(ctx: ToolContext, args: dict) -> str:
    path = resolve_path(args["name"], args.get("folder") or "")
    if not path.is_file():
        raise ToolError(f"Non trovo il file {path.name}.")
    if path.stat().st_size > 5_000_000:
        raise ToolError("Il file è troppo grande da leggere.")
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise ToolError("Non è un file di testo.")
    text = data.decode("utf-8-sig", errors="replace")
    more = f"\n[… altri {len(text) - READ_LIMIT} caratteri]" if len(text) > READ_LIMIT else ""
    return f"Contenuto di {path.name}:\n{text[:READ_LIMIT]}{more}"


def list_folder(ctx: ToolContext, args: dict) -> str:
    path = resolve_path(args.get("name") or ".", args.get("folder") or "desktop")
    if not path.is_dir():
        raise ToolError("Non è una cartella.")
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    names = [(p.name + "\\") if p.is_dir() else p.name for p in entries[:60]]
    more = f" (e altri {len(entries) - 60})" if len(entries) > 60 else ""
    return f"In {path}: " + (", ".join(names) if names else "vuota") + more


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
        raise ToolError("Testo troppo lungo.")
    if not winapi.input_desktop_available():
        raise ToolError("Il PC è bloccato: non posso scrivere finché non viene sbloccato.")
    window = _wait_window(app, 0)
    if window is None:
        entry, alternatives = ctx.services.apps.find(app)
        if entry is None:
            builtin = {"blocco note": "notepad.exe", "notepad": "notepad.exe", "wordpad": "write.exe"}.get(normalize(app))
            if builtin is None:
                names = ", ".join(a.name for a in alternatives[:4])
                raise ToolError(f"Non trovo l'app '{app}'." + (f" Forse: {names}?" if names else ""))
            os.startfile(builtin)
        else:
            launch(entry)
        window = _wait_window(app, 25)
        if window is None:
            raise ToolError(f"{app} non si è aperto in tempo.")
        time.sleep(1.5)
    winapi.wait_modifiers_released()
    if not winapi.focus_window(window.hwnd):
        raise ToolError(f"Non riesco a portare {app} in primo piano.")
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
        raise ToolError(f"{app} ha perso il focus mentre scrivevo: controlla il testo.")
    if args.get("save_as"):
        winapi.hotkey(winapi.VK["ctrl"], winapi.VK["s"])
        time.sleep(1.2)
        winapi.type_text(args["save_as"], newline="enter")
        winapi.tap(winapi.VK["enter"])
        time.sleep(0.8)
    title = winapi.window_title(winapi.foreground_window())
    return f"Ho scritto il testo in «{title[:60]}»." if title else f"Ho scritto il testo in {app}."


def read_screen(ctx: ToolContext, args: dict) -> str:
    if not screen.ocr_available():
        raise ToolError("Il riconoscimento del testo di Windows non è disponibile.")
    region = None
    if args.get("app"):
        windows = _matching_windows(args["app"])
        if not windows:
            raise ToolError(f"Non vedo finestre di '{args['app']}'.")
        region = winapi.window_rect(windows[0].hwnd)
    lines = screen.read_text(region)
    text = "\n".join(line.text for line in lines)
    if not text.strip():
        return "Non leggo testo sullo schermo."
    return "Testo visibile (OCR, può contenere errori):\n" + text[:READ_LIMIT]


def click_text(ctx: ToolContext, args: dict) -> str:
    wanted = args["text"].strip()
    if not wanted:
        raise ToolError("Cosa devo cliccare?")
    if not winapi.input_desktop_available():
        raise ToolError("Il PC è bloccato.")
    region = None
    if args.get("app"):
        windows = _matching_windows(args["app"])
        if not windows:
            raise ToolError(f"Non vedo finestre di '{args['app']}'.")
        winapi.focus_window(windows[0].hwnd)
        time.sleep(0.4)
        region = winapi.window_rect(windows[0].hwnd)
    found = screen.find_text(screen.read_text(region), wanted, threshold=0.8)
    if found is None:
        raise ToolError(f"Non vedo «{wanted}» sullo schermo.")
    score, line, (x, y) = found
    winapi.click(x, y, double=bool(args.get("double")), right=bool(args.get("right")))
    time.sleep(0.5)
    return f"Ho cliccato su «{line.text[:60]}»."


WEATHER_CODES = {
    0: "sereno", 1: "quasi sereno", 2: "parzialmente nuvoloso", 3: "nuvoloso", 45: "nebbia", 48: "nebbia con brina",
    51: "pioviggine leggera", 53: "pioviggine", 55: "pioviggine intensa", 56: "pioviggine gelata", 57: "pioviggine gelata",
    61: "pioggia leggera", 63: "pioggia", 65: "pioggia forte", 66: "pioggia gelata", 67: "pioggia gelata forte",
    71: "neve leggera", 73: "neve", 75: "neve forte", 77: "nevischio", 80: "rovesci leggeri", 81: "rovesci",
    82: "rovesci violenti", 85: "rovesci di neve", 86: "forti rovesci di neve", 95: "temporale",
    96: "temporale con grandine", 99: "temporale con grandine forte",
}


def _place_cache() -> Path:
    return app_dir() / "place.json"


def _geocode(city: str) -> tuple[float, float, str]:
    response = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "it", "format": "json"},
        timeout=8,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ToolError(f"Non trovo la città «{city}».")
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
        raise ToolError("Non so dove sei: dimmi la città.")
    label = ", ".join(x for x in (data.get("city"), data.get("region")) if x) or "la tua zona"
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
        raise ToolError("Il servizio meteo non risponde, riprova tra poco.") from exc
    cur = data["current"]
    parts = [
        f"Meteo a {label} adesso: {WEATHER_CODES.get(int(cur['weather_code']), 'condizioni variabili')}, "
        f"{round(cur['temperature_2m'])}°C (percepiti {round(cur['apparent_temperature'])}°C), "
        f"umidità {cur['relative_humidity_2m']}%, vento {round(cur['wind_speed_10m'])} km/h."
    ]
    daily = data["daily"]
    names = ["oggi", "domani"]
    for i, day in enumerate(daily["time"]):
        when = names[i] if i < 2 else dt.date.fromisoformat(day).strftime("%d/%m")
        rain = daily["precipitation_probability_max"][i]
        parts.append(
            f"{when.capitalize()}: {WEATHER_CODES.get(int(daily['weather_code'][i]), 'variabile')}, "
            f"min {round(daily['temperature_2m_min'][i])}° max {round(daily['temperature_2m_max'][i])}°"
            + (f", pioggia {rain}%" if rain is not None else "")
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
        raise ToolError("Comando vuoto.")
    if len(command) > 4000:
        raise ToolError("Comando troppo lungo.")
    if _DANGEROUS.search(command):
        raise ToolError("Questo comando può danneggiare il PC o i dati: non lo eseguo. Fallo tu se sei sicuro.")
    log.info("powershell: %d characters", len(command))
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command],
            capture_output=True,
            timeout=60,
            creationflags=CREATE_NO_WINDOW,
            cwd=str(_home()),
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError("Il comando ha impiegato più di 60 secondi ed è stato interrotto.") from exc
    out = result.stdout.decode("utf-8", errors="replace").strip()
    err = result.stderr.decode("utf-8", errors="replace").strip()
    text = out[:READ_LIMIT] or "(nessun output)"
    if result.returncode != 0:
        raise ToolError(f"Il comando è fallito (codice {result.returncode}): {(err or out)[:1500]}")
    return text + (f"\n[avvisi: {err[:500]}]" if err else "")


TOOLS = [
    Tool(
        "create_file",
        "Crea un file di testo (txt, md, csv, html, py, json…) nelle cartelle dell'utente. "
        "mode: create (default), overwrite, append. open=true lo apre dopo.",
        params(
            {
                "name": {"type": "string", "description": "nome del file, es. lista spesa.txt"},
                "content": {"type": "string"},
                "folder": {"type": "string", "description": "desktop (default), documenti, download… o un percorso"},
                "mode": {"type": "string", "enum": ["create", "overwrite", "append"]},
                "open": {"type": "boolean"},
            },
            ["name", "content"],
        ),
        create_file,
    ),
    Tool(
        "create_folder",
        "Crea una cartella (default sul desktop).",
        params({"name": {"type": "string"}, "folder": {"type": "string"}}, ["name"]),
        create_folder,
    ),
    Tool(
        "read_file",
        "Legge un file di testo dell'utente.",
        params({"name": {"type": "string"}, "folder": {"type": "string"}}, ["name"]),
        read_file,
    ),
    Tool(
        "list_folder",
        "Elenca i file di una cartella (desktop, documenti, download… o un percorso).",
        params({"folder": {"type": "string"}, "name": {"type": "string", "description": "sottocartella"}}),
        list_folder,
    ),
    Tool(
        "write_in_app",
        "Apre (o usa) un'app e ci scrive un testo: Blocco note, Word, WhatsApp, chat, editor… "
        "new_document=true per un documento nuovo (Ctrl+N), save_as=nome per salvarlo.",
        params(
            {
                "app": {"type": "string"},
                "text": {"type": "string"},
                "new_document": {"type": "boolean"},
                "save_as": {"type": "string"},
            },
            ["app", "text"],
        ),
        write_in_app,
        timeout=120,
        snapshot_on_error=True,
    ),
    Tool(
        "read_screen",
        "Legge il testo visibile sullo schermo o nella finestra di un'app (per capire cosa c'è aperto).",
        params({"app": {"type": "string", "description": "facoltativo"}}),
        read_screen,
    ),
    Tool(
        "click_text",
        "Clicca su una scritta visibile sullo schermo (pulsante, link, voce di menu), facoltativamente in un'app.",
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
    ),
    Tool(
        "weather",
        "Meteo attuale e previsioni (default: dove si trova il PC). Usalo per qualsiasi domanda sul tempo.",
        params({"city": {"type": "string"}, "days": {"type": "integer", "description": "1-7, default 2"}}),
        weather,
        timeout=25,
    ),
    Tool(
        "run_powershell",
        "Esegue un comando PowerShell sul PC (ultima risorsa, quando nessun altro strumento basta: "
        "file, impostazioni, informazioni di sistema, programmi). Restituisce l'output.",
        params({"command": {"type": "string"}}, ["command"]),
        run_powershell,
        timeout=75,
    ),
]
