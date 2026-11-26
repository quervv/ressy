from __future__ import annotations

import datetime as dt
import io
import logging
import os
import subprocess
import time

from ..paths import pictures_dir
from ..speech.textnorm import normalize, similarity
from ..speech.wake import phonetic
from .apps import launch
from . import winapi
from .registry import Attachment, Tool, ToolContext, ToolError, params
from ..i18n import tr

log = logging.getLogger("ressy.system")

CREATE_NO_WINDOW = 0x08000000

MEDIA_KEYS = {
    "play_pause": "media_play_pause",
    "next": "media_next",
    "previous": "media_prev",
    "stop": "media_stop",
    "mute": "volume_mute",
}


def media_control(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    winapi.tap(winapi.VK[MEDIA_KEYS[action]])
    return {
        "play_pause": tr("Ho premuto play/pausa."),
        "next": tr("Traccia successiva."),
        "previous": tr("Traccia precedente."),
        "stop": tr("Riproduzione fermata."),
        "mute": tr("Audio disattivato/riattivato."),
    }[action]


def set_volume(ctx: ToolContext, args: dict) -> str:
    level = args.get("level")
    change = args.get("change")
    up, down = winapi.VK["volume_up"], winapi.VK["volume_down"]
    if level is not None:
        level = max(0, min(100, int(level)))
        presses = []
        for _ in range(50):
            presses += [winapi.key_input(down), winapi.key_input(down, up=True)]
        for _ in range(round(level / 2)):
            presses += [winapi.key_input(up), winapi.key_input(up, up=True)]
        winapi.send_inputs(presses)
        return tr("Volume impostato al {level}%.").format(level=level)
    if change in ("up", "down"):
        steps = max(1, min(50, int(args.get("steps") or 5)))
        vk = up if change == "up" else down
        presses = []
        for _ in range(steps):
            presses += [winapi.key_input(vk), winapi.key_input(vk, up=True)]
        winapi.send_inputs(presses)
        if change == "up":
            return tr("Volume alzato del {percent}%.").format(percent=steps * 2)
        return tr("Volume abbassato del {percent}%.").format(percent=steps * 2)
    if change == "mute":
        winapi.tap(winapi.VK["volume_mute"])
        return tr("Audio disattivato/riattivato.")
    raise ToolError(tr("Indica un livello (0-100) oppure change=up/down/mute."))


def take_screenshot(ctx: ToolContext, args: dict) -> str:
    from PIL import ImageGrab

    image = ImageGrab.grab(all_screens=True)
    folder = pictures_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot-{dt.datetime.now():%Y%m%d-%H%M%S}.png"
    image.save(path, "PNG")
    if ctx.channel.remote:
        preview = image.convert("RGB")
        if preview.width > 2560:
            ratio = 2560 / preview.width
            preview = preview.resize((2560, max(1, int(preview.height * ratio))))
        buffer = io.BytesIO()
        preview.save(buffer, "JPEG", quality=82, optimize=True)
        ctx.images.append(Attachment(buffer.getvalue(), path.with_suffix(".jpg").name, "image/jpeg"))
        return tr("Screenshot fatto ({width}×{height}): lo allego alla risposta.").format(width=image.width, height=image.height)
    return tr("Screenshot salvato in Immagini\\Ressy ({name}).").format(name=path.name)


def pc_power(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    delay = max(0, min(3600, int(args.get("delay_seconds") if args.get("delay_seconds") is not None else 60)))
    if action == "lock":
        if not winapi.lock_workstation():
            raise ToolError(tr("Windows non ha bloccato il PC."))
        return tr("PC bloccato.")
    if action == "sleep":
        ctx.deferred.append(winapi.suspend)
        return tr("Metto il PC in sospensione appena ho risposto.")
    if action in ("shutdown", "restart"):
        flag = "/s" if action == "shutdown" else "/r"
        subprocess.run(["shutdown", flag, "/t", str(delay)], check=False, creationflags=CREATE_NO_WINDOW)
        if action == "shutdown":
            return tr("Spengo il PC tra {delay} secondi. Per annullare chiedimi di annullare lo spegnimento.").format(delay=delay)
        return tr("Riavvio il PC tra {delay} secondi. Per annullare chiedimi di annullare il riavvio.").format(delay=delay)
    if action == "cancel":
        result = subprocess.run(["shutdown", "/a"], check=False, capture_output=True, creationflags=CREATE_NO_WINDOW)
        if result.returncode != 0:
            return tr("Non c'era nessuno spegnimento programmato.")
        return tr("Spegnimento annullato.")
    raise ToolError(tr("Azione non valida."))


def system_status(ctx: ToolContext, args: dict) -> str:
    import psutil

    cpu = psutil.cpu_percent(interval=0.4)
    memory = psutil.virtual_memory()
    parts = [f"CPU {cpu:.0f}%", tr("RAM {percent:.0f}% ({used:.1f} di {total:.1f} GB)").format(
        percent=memory.percent, used=memory.used / 2**30, total=memory.total / 2**30)]
    try:
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
        parts.append(tr("disco {value:.0f} GB liberi su {value2:.0f}").format(value=disk.free / 2**30, value2=disk.total / 2**30))
    except OSError:
        pass
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery is not None:
        charge = tr("batteria {percent:.0f}%, in carica") if battery.power_plugged else tr("batteria {percent:.0f}%, non in carica")
        parts.append(charge.format(percent=battery.percent))
    uptime = dt.timedelta(seconds=int(time.time() - psutil.boot_time()))
    hours, rem = divmod(uptime.seconds, 3600)
    parts.append(tr("acceso da {days}g {hours}h {value}m").format(days=uptime.days, hours=hours, value=rem // 60) if uptime.days else tr("acceso da {hours}h {value}m").format(hours=hours, value=rem // 60))
    return "; ".join(parts) + "."


FOLDER_NAMES = {
    "desktop": "desktop", "scrivania": "desktop",
    "documenti": "documents", "documents": "documents",
    "download": "downloads", "downloads": "downloads", "scaricati": "downloads",
    "immagini": "pictures", "foto": "pictures", "pictures": "pictures",
    "musica": "music", "music": "music",
    "video": "videos", "videos": "videos",
}


_SKIP_DIRS = {"appdata", "node_modules", ".git", "__pycache__", ".venv", "venv", "$recycle.bin", ".cache"}


def _folder_score(wanted: str, candidate: str) -> float:
    a, b = normalize(wanted).replace(" ", ""), normalize(candidate).replace(" ", "")
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    score = max(similarity(a, b), similarity(phonetic(a), phonetic(b)))
    if len(a) >= 4 and (b.startswith(a) or a in b):
        score = max(score, 0.86)
    return score


def find_folder(wanted: str, roots: list[str] | None = None, max_depth: int = 3,
                budget: float = 2.0) -> tuple[str | None, list[str]]:
    if roots is None:
        roots = [winapi.known_folder(k) for k in ("desktop", "documents", "downloads", "pictures", "music", "videos")]
        roots.append(os.path.expanduser("~"))
    deadline = time.monotonic() + budget
    seen: set[str] = set()
    queue = [(r, 0) for r in roots if r and os.path.isdir(r)]
    best: tuple[float, int, str] | None = None
    near: list[tuple[float, str]] = []
    while queue and time.monotonic() < deadline:
        folder, depth = queue.pop(0)
        key = os.path.normcase(os.path.abspath(folder))
        if key in seen:
            continue
        seen.add(key)
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            low = entry.name.lower()
            if low in _SKIP_DIRS or low.startswith("."):
                continue
            score = _folder_score(wanted, entry.name)
            if score >= 0.8 and (best is None or (score, -depth) > (best[0], -best[1])):
                best = (score, depth, entry.path)
            elif score >= 0.7:
                near.append((score, entry.name))
            if depth + 1 < max_depth:
                queue.append((entry.path, depth + 1))
    if best is not None:
        return best[2], []
    near.sort(reverse=True)
    return None, list(dict.fromkeys(name for _, name in near))[:4]


def open_folder(ctx: ToolContext, args: dict) -> str:
    raw_name = args["name"].strip().strip('"')
    name = raw_name.lower()
    if name in ("screenshot ressy", "ressy", "screenshot"):
        folder = pictures_dir()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))
        return tr("Ho aperto la cartella degli screenshot di Ressy.")
    key = FOLDER_NAMES.get(name)
    if key is not None:
        path = winapi.known_folder(key)
        if not path or not os.path.isdir(path):
            raise ToolError(tr("Non trovo quella cartella."))
        os.startfile(path)
        return tr("Ho aperto la cartella {raw_name}.").format(raw_name=raw_name)
    expanded = os.path.expandvars(os.path.expanduser(raw_name))
    if os.path.isabs(expanded) and os.path.isdir(expanded):
        os.startfile(expanded)
        return tr("Ho aperto la cartella {value}.").format(value=os.path.basename(expanded.rstrip(chr(92))) or expanded)
    path, near = find_folder(raw_name)
    if path is not None:
        os.startfile(path)
        return tr("Ho aperto la cartella {basename} ({dirname}).").format(basename=os.path.basename(path), dirname=os.path.dirname(path))
    apps = getattr(ctx.services, "apps", None)
    if apps is not None:
        entry, _ = apps.find(raw_name)
        if entry is not None:
            launch(entry)
            return tr("{raw_name} è un programma, non una cartella: l'ho aperto.").format(raw_name=raw_name)
    hint = tr(" Forse intendevi: {join}?").format(join=', '.join(near)) if near else ""
    raise ToolError(tr("Non trovo una cartella '{raw_name}' nel Desktop, Documenti, Download o nella cartella utente.{hint}").format(raw_name=raw_name, hint=hint))


def _require_desktop() -> None:
    if not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato: non posso usare la tastiera finché non viene sbloccato."))


def type_text(ctx: ToolContext, args: dict) -> str:
    text = args["text"]
    if len(text) > 5000:
        raise ToolError(tr("Testo troppo lungo (massimo 5000 caratteri)."))
    _require_desktop()
    winapi.wait_modifiers_released()
    title = winapi.window_title(winapi.foreground_window())
    winapi.type_text(text)
    return tr("Ho scritto il testo in «{value}».").format(value=title[:60]) if title else tr("Ho scritto il testo.")


_BLOCKED_COMBOS = ({0x11, 0x12, 0x2E},)


def press_keys(ctx: ToolContext, args: dict) -> str:
    try:
        codes = winapi.parse_keys(args["keys"])
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if set(codes) in [set(c) for c in _BLOCKED_COMBOS]:
        raise ToolError(tr("Questa combinazione non si può inviare."))
    _require_desktop()
    winapi.wait_modifiers_released()
    winapi.hotkey(*codes)
    return tr("Ho premuto {value}.").format(value=args['keys'])


def set_clipboard(ctx: ToolContext, args: dict) -> str:
    winapi.set_clipboard_text(args["text"])
    return tr("Testo copiato negli appunti.")


TOOLS = [
    Tool(
        "media_control",
        "Controlla la musica/video in riproduzione (Spotify, YouTube...).",
        params({"action": {"type": "string", "enum": list(MEDIA_KEYS)}}, ["action"]),
        media_control,
    ),
    Tool(
        "set_volume",
        "Volume del PC: level 0-100 per impostarlo, oppure change=up/down (steps da 2%) o mute.",
        params(
            {
                "level": {"type": "integer"},
                "change": {"type": "string", "enum": ["up", "down", "mute"]},
                "steps": {"type": "integer"},
            }
        ),
        set_volume,
    ),
    Tool("take_screenshot", "Fa uno screenshot dello schermo.", params(), take_screenshot),
    Tool(
        "pc_power",
        "Blocca, sospende, spegne o riavvia il PC, o annulla uno spegnimento programmato.",
        params(
            {
                "action": {"type": "string", "enum": ["lock", "sleep", "shutdown", "restart", "cancel"]},
                "delay_seconds": {"type": "integer", "description": "per shutdown/restart, default 60"},
            },
            ["action"],
        ),
        pc_power,
    ),
    Tool("system_status", "Stato del PC: CPU, RAM, disco, batteria, da quanto è acceso.", params(), system_status),
    Tool(
        "open_folder",
        "Apre una cartella in Esplora file: Desktop, Documenti, Download… o una tua cartella per nome.",
        params({"name": {"type": "string"}}, ["name"]),
        open_folder,
    ),
    Tool(
        "type_text",
        "Scrive del testo nella finestra attiva, come da tastiera.",
        params({"text": {"type": "string"}}, ["text"]),
        type_text,
        timeout=120,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "press_keys",
        "Preme una combinazione di tasti nella finestra attiva, es. 'ctrl+s', 'alt+tab', 'win+d', 'f5'.",
        params({"keys": {"type": "string"}}, ["keys"]),
        press_keys,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "set_clipboard",
        "Copia un testo negli appunti di Windows.",
        params({"text": {"type": "string"}}, ["text"]),
        set_clipboard,
    ),
]
