from __future__ import annotations

import datetime as dt
import io
import logging
import os
import subprocess
import time

from ..paths import pictures_dir
from . import winapi
from .registry import Attachment, Tool, ToolContext, ToolError, params

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
        "play_pause": "Ho premuto play/pausa.",
        "next": "Traccia successiva.",
        "previous": "Traccia precedente.",
        "stop": "Riproduzione fermata.",
        "mute": "Audio disattivato/riattivato.",
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
        return f"Volume impostato al {level}%."
    if change in ("up", "down"):
        steps = max(1, min(50, int(args.get("steps") or 5)))
        vk = up if change == "up" else down
        presses = []
        for _ in range(steps):
            presses += [winapi.key_input(vk), winapi.key_input(vk, up=True)]
        winapi.send_inputs(presses)
        return f"Volume {'alzato' if change == 'up' else 'abbassato'} del {steps * 2}%."
    if change == "mute":
        winapi.tap(winapi.VK["volume_mute"])
        return "Audio disattivato/riattivato."
    raise ToolError("Indica un livello (0-100) oppure change=up/down/mute.")


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
        return f"Screenshot fatto ({image.width}×{image.height}): lo allego alla risposta."
    return f"Screenshot salvato in Immagini\\Ressy ({path.name})."


def pc_power(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    delay = max(0, min(3600, int(args.get("delay_seconds") if args.get("delay_seconds") is not None else 60)))
    if action == "lock":
        if not winapi.lock_workstation():
            raise ToolError("Windows non ha bloccato il PC.")
        return "PC bloccato."
    if action == "sleep":
        ctx.deferred.append(winapi.suspend)
        return "Metto il PC in sospensione appena ho risposto."
    if action in ("shutdown", "restart"):
        flag = "/s" if action == "shutdown" else "/r"
        subprocess.run(["shutdown", flag, "/t", str(delay)], check=False, creationflags=CREATE_NO_WINDOW)
        verb = "Spengo" if action == "shutdown" else "Riavvio"
        return f"{verb} il PC tra {delay} secondi. Per annullare chiedimi di annullare lo spegnimento."
    if action == "cancel":
        result = subprocess.run(["shutdown", "/a"], check=False, capture_output=True, creationflags=CREATE_NO_WINDOW)
        if result.returncode != 0:
            return "Non c'era nessuno spegnimento programmato."
        return "Spegnimento annullato."
    raise ToolError("Azione non valida.")


def system_status(ctx: ToolContext, args: dict) -> str:
    import psutil

    cpu = psutil.cpu_percent(interval=0.4)
    memory = psutil.virtual_memory()
    parts = [f"CPU {cpu:.0f}%", f"RAM {memory.percent:.0f}% ({memory.used / 2**30:.1f} di {memory.total / 2**30:.1f} GB)"]
    try:
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
        parts.append(f"disco {disk.free / 2**30:.0f} GB liberi su {disk.total / 2**30:.0f}")
    except OSError:
        pass
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery is not None:
        state = "in carica" if battery.power_plugged else "a batteria"
        parts.append(f"batteria {battery.percent:.0f}% {state}")
    uptime = dt.timedelta(seconds=int(time.time() - psutil.boot_time()))
    hours, rem = divmod(uptime.seconds, 3600)
    parts.append(f"acceso da {uptime.days}g {hours}h {rem // 60}m" if uptime.days else f"acceso da {hours}h {rem // 60}m")
    return "; ".join(parts) + "."


FOLDER_NAMES = {
    "desktop": "desktop", "scrivania": "desktop",
    "documenti": "documents", "documents": "documents",
    "download": "downloads", "downloads": "downloads", "scaricati": "downloads",
    "immagini": "pictures", "foto": "pictures", "pictures": "pictures",
    "musica": "music", "music": "music",
    "video": "videos", "videos": "videos",
}


def open_folder(ctx: ToolContext, args: dict) -> str:
    name = args["name"].strip().lower()
    if name in ("screenshot ressy", "ressy", "screenshot"):
        folder = pictures_dir()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))
        return "Ho aperto la cartella degli screenshot di Ressy."
    key = FOLDER_NAMES.get(name)
    if key is None:
        raise ToolError("Posso aprire: Desktop, Documenti, Download, Immagini, Musica, Video, screenshot.")
    path = winapi.known_folder(key)
    if not path or not os.path.isdir(path):
        raise ToolError("Non trovo quella cartella.")
    os.startfile(path)
    return f"Ho aperto la cartella {args['name']}."


def _require_desktop() -> None:
    if not winapi.input_desktop_available():
        raise ToolError("Il PC è bloccato: non posso usare la tastiera finché non viene sbloccato.")


def type_text(ctx: ToolContext, args: dict) -> str:
    text = args["text"]
    if len(text) > 5000:
        raise ToolError("Testo troppo lungo (massimo 5000 caratteri).")
    _require_desktop()
    winapi.wait_modifiers_released()
    title = winapi.window_title(winapi.foreground_window())
    winapi.type_text(text)
    return f"Ho scritto il testo in «{title[:60]}»." if title else "Ho scritto il testo."


_BLOCKED_COMBOS = ({0x11, 0x12, 0x2E},)


def press_keys(ctx: ToolContext, args: dict) -> str:
    try:
        codes = winapi.parse_keys(args["keys"])
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if set(codes) in [set(c) for c in _BLOCKED_COMBOS]:
        raise ToolError("Questa combinazione non si può inviare.")
    _require_desktop()
    winapi.wait_modifiers_released()
    winapi.hotkey(*codes)
    return f"Ho premuto {args['keys']}."


def set_clipboard(ctx: ToolContext, args: dict) -> str:
    winapi.set_clipboard_text(args["text"])
    return "Testo copiato negli appunti."


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
        "Apre una cartella: Desktop, Documenti, Download, Immagini, Musica, Video, screenshot.",
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
    ),
    Tool(
        "press_keys",
        "Preme una combinazione di tasti nella finestra attiva, es. 'ctrl+s', 'alt+tab', 'win+d', 'f5'.",
        params({"keys": {"type": "string"}}, ["keys"]),
        press_keys,
        snapshot_on_error=True,
    ),
    Tool(
        "set_clipboard",
        "Copia un testo negli appunti di Windows.",
        params({"text": {"type": "string"}}, ["text"]),
        set_clipboard,
    ),
]
