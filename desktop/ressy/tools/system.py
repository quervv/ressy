from __future__ import annotations

import datetime as dt
import io
import logging
import os
import socket
import subprocess
import sys
import time

from ..paths import pictures_dir, user_folder
from ..speech.textnorm import normalize, similarity
from ..speech.wake import phonetic
from .apps import _matching_windows, _real_window, launch
from . import platform_os, winapi
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
    if sys.platform != "win32":
        platform_os.media_action(action)
    else:
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
    if sys.platform != "win32":
        if level is None and change not in ("up", "down", "mute"):
            raise ToolError(tr("Indica un livello (0-100) oppure change=up/down/mute."))
        steps = max(1, min(50, int(args.get("steps") or 5)))
        return platform_os.unix_set_volume(level=level, change=change, steps=steps)
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

    app_name = (args.get("app") or "").strip()
    if app_name:
        windows = _matching_windows(app_name)
        real = [w for w in windows if _real_window(w)]
        target = real[0] if real else (windows[0] if windows else None)
        if target is None:
            raise ToolError(tr("Non vedo finestre aperte di '{name}'.").format(name=app_name))
        if sys.platform != "win32":
            platform_os.unix_focus_window(target.hwnd, target.class_name)
            time.sleep(0.25)
            image = ImageGrab.grab(all_screens=True)
        else:
            if winapi.input_desktop_available():
                winapi.focus_window(target.hwnd)
                time.sleep(0.25)
            rect = winapi.window_rect(target.hwnd)
            if rect[2] <= rect[0] or rect[3] <= rect[1]:
                raise ToolError(tr("La finestra di {name} è ridotta a icona.").format(name=app_name))
            image = ImageGrab.grab(bbox=rect, all_screens=True)
    else:
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
    if sys.platform != "win32":
        return platform_os.unix_pc_power(action, delay)
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
        disk = psutil.disk_usage(platform_os.unix_system_drive())
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
        if sys.platform == "win32":
            roots = [winapi.known_folder(k) for k in ("desktop", "documents", "downloads", "pictures", "music", "videos")]
        else:
            roots = platform_os.user_home_folders()
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
        platform_os.open_path(folder)
        return tr("Ho aperto la cartella degli screenshot di Ressy.")
    key = FOLDER_NAMES.get(name)
    if key is not None:
        path = winapi.known_folder(key) if sys.platform == "win32" else str(user_folder(key))
        if not path or not os.path.isdir(path):
            raise ToolError(tr("Non trovo quella cartella."))
        platform_os.open_path(path)
        return tr("Ho aperto la cartella {raw_name}.").format(raw_name=raw_name)
    expanded = os.path.expandvars(os.path.expanduser(raw_name))
    if os.path.isabs(expanded) and os.path.isdir(expanded):
        platform_os.open_path(expanded)
        return tr("Ho aperto la cartella {value}.").format(value=os.path.basename(expanded.rstrip(chr(92) + "/")) or expanded)
    path, near = find_folder(raw_name)
    if path is not None:
        platform_os.open_path(path)
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
    if sys.platform == "win32" and not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato: non posso usare la tastiera finché non viene sbloccato."))


def type_text(ctx: ToolContext, args: dict) -> str:
    text = args["text"]
    if len(text) > 5000:
        raise ToolError(tr("Testo troppo lungo (massimo 5000 caratteri)."))
    _require_desktop()
    platform_os.wait_modifiers_released()
    if sys.platform == "win32":
        title = winapi.window_title(winapi.foreground_window())
        winapi.type_text(text)
    else:
        wins = platform_os.unix_top_windows()
        title = next((str(w["title"]) for w in wins if w.get("front")), "")
        platform_os.type_text(text)
    return tr("Ho scritto il testo in «{value}».").format(value=title[:60]) if title else tr("Ho scritto il testo.")


_BLOCKED_COMBOS = ({0x11, 0x12, 0x2E},)


def press_keys(ctx: ToolContext, args: dict) -> str:
    if sys.platform != "win32":
        try:
            keys = platform_os.validate_keys(args["keys"])
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        platform_os.wait_modifiers_released()
        platform_os.send_hotkey(*keys)
        return tr("Ho premuto {value}.").format(value=args["keys"])
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
    platform_os.set_clipboard(args["text"])
    return tr("Testo copiato negli appunti.")


def clipboard(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    if action == "get":
        text = platform_os.get_clipboard()
        if not text:
            return tr("Gli appunti sono vuoti (o non contengono testo).")
        if len(text) > 4000:
            return tr("Negli appunti c'è:\n{text}").format(text=text[:4000] + "…")
        return tr("Negli appunti c'è:\n{text}").format(text=text)
    if action == "set":
        text = args.get("text") or ""
        if not text:
            raise ToolError(tr("Quale testo devo copiare negli appunti?"))
        platform_os.set_clipboard(text)
        return tr("Testo copiato negli appunti.")
    if action == "paste":
        _require_desktop()
        platform_os.wait_modifiers_released()
        platform_os.send_hotkey(platform_os.mod_key(), "v")
        return tr("Ho incollato dagli appunti.")
    if action == "clear":
        platform_os.clear_clipboard()
        return tr("Ho svuotato gli appunti.")
    raise ToolError(tr("Azione non valida per gli appunti."))


def mouse_action(ctx: ToolContext, args: dict) -> str:
    action = args["action"]
    _require_desktop()
    app_name = (args.get("app") or "").strip()
    x, y = args.get("x"), args.get("y")
    if app_name:
        windows = _matching_windows(app_name)
        real = [w for w in windows if _real_window(w)]
        target = real[0] if real else (windows[0] if windows else None)
        if target is None:
            raise ToolError(tr("Non vedo finestre aperte di '{name}'.").format(name=app_name))
        if sys.platform != "win32":
            platform_os.unix_focus_window(target.hwnd, target.class_name)
        else:
            winapi.focus_window(target.hwnd)
        time.sleep(0.2)
        if (x is None or y is None) and sys.platform == "win32":
            l, t, r, b = winapi.window_rect(target.hwnd)
            if r > l and b > t:
                x, y = (l + r) // 2, (t + b) // 2
    if x is not None and y is not None:
        try:
            platform_os.move_mouse(int(x), int(y))
        except OSError as exc:
            raise ToolError(tr("Non riesco a spostare il mouse.")) from exc
        time.sleep(0.05)

    amount = max(1, min(30, int(args.get("amount") or 5)))
    if action == "scroll_down":
        platform_os.scroll_mouse(dy=-amount)
        return tr("Ho scorso verso il basso.")
    if action == "scroll_up":
        platform_os.scroll_mouse(dy=amount)
        return tr("Ho scorso verso l'alto.")
    if action == "scroll_left":
        platform_os.scroll_mouse(dx=-amount)
        return tr("Ho scorso a sinistra.")
    if action == "scroll_right":
        platform_os.scroll_mouse(dx=amount)
        return tr("Ho scorso a destra.")
    if action == "click":
        if x is None or y is None:
            raise ToolError(tr("Indica le coordinate (x, y) o usa click_text per cliccare una scritta."))
        platform_os.click_mouse(int(x), int(y))
        return tr("Ho cliccato alle coordinate {x}, {y}.").format(x=int(x), y=int(y))
    if action == "double_click":
        if x is None or y is None:
            raise ToolError(tr("Indica le coordinate (x, y) per il doppio clic."))
        platform_os.click_mouse(int(x), int(y), double=True)
        return tr("Ho fatto doppio clic alle coordinate {x}, {y}.").format(x=int(x), y=int(y))
    if action == "right_click":
        if x is None or y is None:
            raise ToolError(tr("Indica le coordinate (x, y) per il clic destro."))
        platform_os.click_mouse(int(x), int(y), right=True)
        return tr("Ho fatto clic destro alle coordinate {x}, {y}.").format(x=int(x), y=int(y))
    raise ToolError(tr("Azione del mouse non valida."))


_SETTINGS_PAGES = {
    "main": "ms-settings:",
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "sound": "ms-settings:sound",
    "display": "ms-settings:display",
    "battery": "ms-settings:batterysaver",
    "updates": "ms-settings:windowsupdate",
    "apps": "ms-settings:appsfeatures",
    "privacy": "ms-settings:privacy",
}


def _wmi_brightness(level: int | None = None, delta: int = 0) -> int:
    if level is not None:
        target = max(0, min(100, int(level)))
        cmd = f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {target})"
    else:
        cmd = (
            "$cur = (Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness; "
            f"$next = [Math]::Max(0, [Math]::Min(100, [int]$cur + ({int(delta)}))); "
            "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, $next); "
            "Write-Output $next"
        )
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW,
    )
    if res.returncode != 0:
        raise ToolError(tr("Questo schermo non permette di regolare la luminosità da Windows."))
    if level is not None:
        return max(0, min(100, int(level)))
    out = res.stdout.decode("utf-8", errors="replace").strip().splitlines()
    return int(out[-1]) if out and out[-1].strip().isdigit() else 50


def _set_theme(dark: bool) -> None:
    import winreg

    val = 0 if dark else 1
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, val)
        winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, val)


def system_control(ctx: ToolContext, args: dict) -> str:
    import psutil

    action = args["action"]
    if action == "brightness_set":
        if args.get("level") is None:
            raise ToolError(tr("Indica la percentuale di luminosità (0-100)."))
        val = _wmi_brightness(level=int(args["level"]))
        return tr("Luminosità impostata al {level}%.").format(level=val)
    if action == "brightness_up":
        val = _wmi_brightness(delta=15)
        return tr("Luminosità alzata al {level}%.").format(level=val)
    if action == "brightness_down":
        val = _wmi_brightness(delta=-15)
        return tr("Luminosità abbassata al {level}%.").format(level=val)
    if action in ("dark_mode", "light_mode"):
        dark = action == "dark_mode"
        if sys.platform != "win32":
            platform_os.unix_set_theme(dark)
        else:
            _set_theme(dark)
        return tr("Ho attivato la modalità scura.") if dark else tr("Ho attivato la modalità chiara.")
    if action == "empty_recycle_bin":
        ok = winapi.empty_recycle_bin() if sys.platform == "win32" else platform_os.unix_empty_trash()
        if not ok:
            raise ToolError(tr("Windows non ha svuotato il Cestino."))
        return tr("Ho svuotato il Cestino.")
    if action == "top_processes":
        by_name: dict[str, list[float]] = {}
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                name = (proc.info.get("name") or "?").removesuffix(".exe")
                mem = proc.info.get("memory_info")
                mb = (mem.rss / 2**20) if mem else 0.0
                by_name[name] = [by_name.get(name, [0.0, 0])[0] + mb, by_name.get(name, [0.0, 0])[1] + 1]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        top = sorted(by_name.items(), key=lambda kv: kv[1][0], reverse=True)[:6]
        lines = [f"{name}: {mb:.0f} MB" + (f" ({int(cnt)})" if cnt > 1 else "") for name, (mb, cnt) in top]
        return tr("Programmi che usano più RAM:\n") + "\n".join(lines)
    if action == "disk_space":
        parts = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts.lower() or not part.fstype:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                parts.append(
                    tr("{drive} {free:.0f} GB liberi su {total:.0f} GB").format(
                        drive=part.device.rstrip("\\"), free=usage.free / 2**30, total=usage.total / 2**30
                    )
                )
            except OSError:
                continue
        return "; ".join(parts) + "." if parts else tr("Non leggo i dischi.")
    if action == "network_info":
        local_ip = ""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("1.1.1.1", 80))
                local_ip = s.getsockname()[0]
        except OSError:
            pass
        ssid = ""
        if sys.platform != "win32":
            ssid = platform_os.unix_wifi_ssid()
        else:
            try:
                res = subprocess.run(
                    ["netsh", "wlan", "show", "interfaces"], capture_output=True, timeout=5, creationflags=CREATE_NO_WINDOW
                )
                for line in res.stdout.decode("utf-8", errors="replace").splitlines():
                    if line.strip().startswith("SSID") and "BSSID" not in line:
                        ssid = line.split(":", 1)[1].strip()
                        break
            except Exception:
                pass
        if not local_ip:
            return tr("Il PC non sembra connesso a Internet o alla rete locale.")
        wifi = tr(" Wi-Fi: {ssid}.").format(ssid=ssid) if ssid else ""
        return tr("Connesso. IP locale: {ip}.{wifi}").format(ip=local_ip, wifi=wifi)
    if action == "open_settings":
        page = (args.get("page") or "main").strip().lower()
        if sys.platform == "darwin":
            platform_os.open_path("x-apple.systempreferences:")
            return tr("Ho aperto le impostazioni di sistema ({page}).").format(page=page)
        if sys.platform != "win32":
            platform_os.launch_unix_target("gnome-control-center")
            return tr("Ho aperto le impostazioni di sistema ({page}).").format(page=page)
        uri = _SETTINGS_PAGES.get(page, "ms-settings:")
        os.startfile(uri)
        return tr("Ho aperto le impostazioni di Windows ({page}).").format(page=page)
    raise ToolError(tr("Azione di sistema non valida."))


TOOLS = [
    Tool(
        "media_control",
        "Controlla media in riproduzione.",
        params({"action": {"type": "string", "enum": list(MEDIA_KEYS)}}, ["action"]),
        media_control,
    ),
    Tool(
        "set_volume",
        "Volume PC (level 0-100, change=up/down/mute).",
        params(
            {
                "level": {"type": "integer"},
                "change": {"type": "string", "enum": ["up", "down", "mute"]},
                "steps": {"type": "integer"},
            }
        ),
        set_volume,
    ),
    Tool(
        "take_screenshot",
        "Salva/allega foto schermo SOLO se chiesta esplicitamente (mai per leggere app o Discord).",
        params({"app": {"type": "string"}}),
        take_screenshot,
    ),
    Tool(
        "pc_power",
        "Blocca, sospende, spegne o riavvia il PC.",
        params(
            {
                "action": {"type": "string", "enum": ["lock", "sleep", "shutdown", "restart", "cancel"]},
                "delay_seconds": {"type": "integer"},
            },
            ["action"],
        ),
        pc_power,
    ),
    Tool("system_status", "Stato PC (CPU, RAM, disco, batteria).", params(), system_status),
    Tool(
        "system_control",
        "Controlli PC: luminosità, dark/light mode, cestino, processi, disco, rete, impostazioni.",
        params(
            {
                "action": {
                    "type": "string",
                    "enum": [
                        "brightness_set", "brightness_up", "brightness_down", "dark_mode", "light_mode",
                        "empty_recycle_bin", "top_processes", "disk_space", "network_info", "open_settings",
                    ],
                },
                "level": {"type": "integer"},
                "page": {"type": "string"},
            },
            ["action"],
        ),
        system_control,
    ),
    Tool(
        "open_folder",
        "Apre cartella in Esplora file.",
        params({"name": {"type": "string"}}, ["name"]),
        open_folder,
    ),
    Tool(
        "type_text",
        "Scrive testo nella finestra attiva.",
        params({"text": {"type": "string"}}, ["text"]),
        type_text,
        timeout=120,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "press_keys",
        "Preme scorciatoia tasti (es. ctrl+s, alt+tab).",
        params({"keys": {"type": "string"}}, ["keys"]),
        press_keys,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "mouse_action",
        "Scroll o click mouse nella schermata.",
        params(
            {
                "action": {
                    "type": "string",
                    "enum": ["scroll_down", "scroll_up", "scroll_left", "scroll_right", "click", "double_click", "right_click"],
                },
                "amount": {"type": "integer"},
                "app": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            ["action"],
        ),
        mouse_action,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "set_clipboard",
        "Copia testo negli appunti.",
        params({"text": {"type": "string"}}, ["text"]),
        set_clipboard,
    ),
    Tool(
        "clipboard",
        "Legge, imposta, incolla o svuota gli appunti.",
        params(
            {
                "action": {"type": "string", "enum": ["get", "set", "paste", "clear"]},
                "text": {"type": "string"},
            },
            ["action"],
        ),
        clipboard,
        uses_screen=True,
    ),
]
