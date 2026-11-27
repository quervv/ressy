from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..i18n import tr
from . import discord as discord_tool
from . import platform_os, winapi
from .apps import launch
from .registry import NeedsInputError, Tool, ToolContext, ToolError, params

log = logging.getLogger("ressy.calls")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DISCORD_CALL_BUTTONS = ("Start Voice Call", "Avvia chiamata vocale", "Avvia chiamata", "Voice Call", "Call", "Chiama")
_TELEGRAM_CALL_BUTTONS = ("Call", "Chiama", "Voice Call", "Chiamata vocale", "Start Call", "Avvia chiamata")


def _uia_click_button(hwnd: int, candidates: tuple[str, ...]) -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    names_lit = ", ".join("'" + c.replace("'", "''") + "'" for c in candidates)
    script = (
        "Add-Type -AssemblyName UIAutomationClient; "
        "Add-Type -AssemblyName UIAutomationTypes; "
        f"$el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{int(hwnd)}); "
        "if (-not $el) { exit 2 }; "
        "$cond = New-Object System.Windows.Automation.PropertyCondition("
        "[System.Windows.Automation.AutomationElement]::ControlTypeProperty, "
        "[System.Windows.Automation.ControlType]::Button); "
        "$btns = $el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond); "
        f"$targets = @({names_lit}); "
        "foreach ($b in $btns) { "
        "  $n = [string]$b.Current.Name; "
        "  if (-not $n) { continue }; "
        "  foreach ($t in $targets) { "
        "    if ($n -ieq $t -or $n.ToLower().Contains($t.ToLower())) { "
        "      try { "
        "        $inv = $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern); "
        "        $inv.Invoke(); Write-Output $n; exit 0 "
        "      } catch { "
        "        $rect = $b.Current.BoundingRectangle; "
        "        if ($rect.Width -gt 0 -and $rect.Height -gt 0) { "
        "          Write-Output ('RECT:' + [int]($rect.Left + $rect.Width/2) + ',' + [int]($rect.Top + $rect.Height/2)); "
        "          exit 0 "
        "        } "
        "      } "
        "    } "
        "  } "
        "} "
        "exit 1"
    )
    try:
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        out = res.stdout.decode("utf-8", errors="replace").strip()
        if res.returncode == 0 and out.startswith("RECT:"):
            xy = out.split(":", 1)[1].split(",")
            winapi.click(int(xy[0]), int(xy[1]))
            return True
        return res.returncode == 0
    except Exception:
        log.debug("UIA button click failed", exc_info=True)
        return False


def _find_telegram_window() -> winapi.Window | None:
    if sys.platform != "win32":
        return None
    best: tuple[int, winapi.Window] | None = None
    for window in winapi.top_windows():
        proc = window.process_name.lower()
        if proc not in ("telegram.exe", "ayugram.exe", "kotatogram.exe"):
            continue
        w, h = winapi.window_size(window.hwnd)
        if w < 300 or h < 250:
            continue
        area = w * h
        if best is None or area > best[0]:
            best = (area, window)
    return best[1] if best else None


def _telegram_installed(ctx: ToolContext) -> Path | None:
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
        cand = appdata / "Telegram Desktop" / "Telegram.exe"
        if cand.is_file():
            return cand
    apps = getattr(ctx.services, "apps", None) if ctx.services else None
    if apps is not None:
        entry, _ = apps.find("Telegram")
        if entry is not None and entry.app_id and Path(entry.app_id).is_file():
            return Path(entry.app_id)
    return None


def _open_telegram_chat(ctx: ToolContext, target: str) -> winapi.Window:
    if sys.platform != "win32":
        raise ToolError(tr("Le chiamate tramite Telegram Desktop sono supportate su Windows."))
    clean = target.strip()
    if clean.startswith("@") or (re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", clean) and " " not in clean):
        username = clean.lstrip("@")
        os.startfile(f"tg://resolve?domain={username}")
        time.sleep(1.3)
    elif re.fullmatch(r"\+?\d{7,16}", clean.replace(" ", "")):
        digits = clean.replace(" ", "").lstrip("+")
        os.startfile(f"tg://resolve?phone={digits}")
        time.sleep(1.3)

    win = _find_telegram_window()
    if win is None:
        exe = _telegram_installed(ctx)
        if exe is not None:
            subprocess.Popen([str(exe)], creationflags=CREATE_NO_WINDOW)
        else:
            apps = getattr(ctx.services, "apps", None) if ctx.services else None
            if apps is not None:
                entry, _ = apps.find("Telegram")
                if entry is not None:
                    launch(entry)
                    win = None
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline and win is None:
            time.sleep(0.5)
            win = _find_telegram_window()
    if win is None:
        raise NeedsInputError(tr("Telegram Desktop non sembra installato o aperto su questo PC."))

    winapi.focus_window(win.hwnd)
    time.sleep(0.35)
    if clean and not clean.startswith("@") and not re.fullmatch(r"\+?\d{7,16}", clean.replace(" ", "")):
        winapi.tap(winapi.VK["esc"])
        time.sleep(0.1)
        winapi.hotkey(winapi.VK["ctrl"], winapi.VK["f"])
        time.sleep(0.25)
        winapi.type_text(clean)
        time.sleep(0.55)
        winapi.tap(winapi.VK["enter"])
        time.sleep(0.6)
    return win


def _call_via_discord(ctx: ToolContext, target: str) -> str:
    window = discord_tool._ensure_discord_ready(ctx)
    if target and not discord_tool.means_current_chat(target):
        resolved = discord_tool.known_name(target)
        discord_tool._open_chat(window, resolved, "user")
        discord_tool.remember_contact(resolved)
    else:
        winapi.focus_window(window.hwnd)
        time.sleep(0.2)
    clicked = _uia_click_button(window.hwnd, _DISCORD_CALL_BUTTONS)
    if not clicked:
        raise ToolError(
            tr("Ho aperto la chat Discord con {target}, ma non trovo il pulsante «Avvia chiamata vocale». "
               "Verifica che sia una chat privata (DM).").format(target=target or tr("corrente"))
        )
    return tr("Sto chiamando {target} su Discord!").format(target=target or tr("la chat aperta"))


def _call_via_telegram(ctx: ToolContext, target: str) -> str:
    win = _open_telegram_chat(ctx, target)
    clicked = _uia_click_button(win.hwnd, _TELEGRAM_CALL_BUTTONS)
    if not clicked:
        raise ToolError(
            tr("Ho aperto la chat Telegram con {target}, ma non trovo il pulsante «Chiama» nella barra in alto.").format(
                target=target or tr("corrente")
            )
        )
    return tr("Sto chiamando {target} su Telegram!").format(target=target or tr("la chat aperta"))


def _local_lan_ip() -> str:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 80))
        return str(s.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()


def discover_lan_devices(max_items: int = 12) -> list[dict[str, str]]:
    import concurrent.futures
    import socket

    local_ip = _local_lan_ip()
    prefix = ".".join(local_ip.split(".")[:3]) if local_ip.count(".") == 3 else ""

    if prefix and not local_ip.startswith("127."):
        def _probe(ip: str) -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.08)
            try:
                sock.connect((ip, 80))
            except OSError:
                pass
            finally:
                sock.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(_probe, [f"{prefix}.{i}" for i in range(1, 255)], timeout=1.5))

    devices: list[dict[str, str]] = []
    seen_ips: set[str] = set()
    try:
        cmd = ["arp", "-a"]
        kwargs: dict[str, Any] = {"capture_output": True, "timeout": 5}
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        res = subprocess.run(cmd, **kwargs)
        out = res.stdout.decode("utf-8", errors="replace")
        for line in out.splitlines():
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F:-]{11,17}|[0-9a-fA-F:]{11,17})", line)
            if not m:
                continue
            ip, mac = m.group(1), m.group(2)
            if ip == local_ip or ip in seen_ips or ip.startswith(("224.", "239.", "255.", "127.")):
                continue
            if ip.endswith(".255") or mac.lower() in ("ff-ff-ff-ff-ff-ff", "ff:ff:ff:ff:ff:ff"):
                continue
            seen_ips.add(ip)
            name = ""
            try:
                host, _, _ = socket.gethostbyaddr(ip)
                if host and host != ip:
                    name = host.split(".")[0]
            except OSError:
                pass
            devices.append({"ip": ip, "name": name or ip, "mac": mac})
            if len(devices) >= max_items:
                break
    except Exception:
        log.debug("LAN device discovery failed", exc_info=True)
    return devices


_WIFI_CALL_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ressy Wi-Fi Call</title><style>
body{margin:0;background:#0e1017;color:#f4f6fb;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#181b26;border:1px solid #2b3248;border-radius:22px;padding:26px;max-width:390px;width:90%;text-align:center;box-shadow:0 16px 40px #0008}
h2{margin:0 0 8px;color:#3cebff}p{color:#b7c0d8;line-height:1.45}.row{display:flex;gap:10px;margin-top:14px}
button{flex:1;padding:12px 14px;border:0;border-radius:12px;font-weight:700;cursor:pointer;font-size:15px}
.ans{background:#4df0b5;color:#0b1314}.send{background:#3cebff;color:#08131a}
input{width:100%;box-sizing:border-box;padding:11px 13px;border-radius:12px;border:1px solid #303952;background:#10131c;color:#fff;margin-top:14px;font-size:15px}
.badge{display:inline-block;padding:5px 12px;border-radius:999px;background:#1f3b36;color:#4df0b5;font-weight:600;margin-top:10px;font-size:13px}
</style></head><body><div class="card"><h2>Ressy Wi-Fi Call</h2><p id="msg">CONN</p>
<div class="badge" id="st">In attesa di risposta…</div>
<div class="row"><button class="ans" onclick="answerCall()">Rispondi e ascolta</button></div>
<input id="txt" placeholder="Scrivi qui per parlare sul PC…" onkeydown="if(event.key==='Enter')sendMsg()">
<div class="row"><button class="send" onclick="sendMsg()">Invia al PC</button></div>
<audio id="aud" preload="auto"></audio></div>
<script>
let ring=null;
function answerCall(){
  document.getElementById('st').textContent='Connesso su Wi-Fi locale';
  const a=document.getElementById('aud'); a.src='/audio'; a.play().catch(()=>{});
}
async function sendMsg(){
  const el=document.getElementById('txt'); const v=el.value.trim(); if(!v) return; el.value='';
  await fetch('/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:v})});
  document.getElementById('st').textContent='Inviato al PC: '+v;
}
</script></body></html>"""

_WIFI_SERVER_LOCK = __import__("threading").Lock()
_WIFI_SERVER_URL = ""
_WIFI_CALL_STATE: dict[str, Any] = {"reason": "Chiamata Wi-Fi attiva con Ressy", "audio": b"", "speaker": None, "loop": None}


def _ensure_wifi_call_endpoint(reason: str, speaker: Any = None, audio_bytes: bytes = b"", loop: Any = None) -> str:
    import http.server
    import json
    import threading

    global _WIFI_SERVER_URL
    with _WIFI_SERVER_LOCK:
        _WIFI_CALL_STATE["reason"] = reason or "Chiamata Wi-Fi attiva con Ressy"
        _WIFI_CALL_STATE["audio"] = audio_bytes
        if speaker is not None:
            _WIFI_CALL_STATE["speaker"] = speaker
        if loop is not None:
            _WIFI_CALL_STATE["loop"] = loop
        if _WIFI_SERVER_URL:
            return _WIFI_SERVER_URL

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.startswith("/audio"):
                    data = _WIFI_CALL_STATE.get("audio") or b""
                    self.send_response(200 if data else 204)
                    if data:
                        self.send_header("Content-Type", "audio/ogg")
                        self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if data:
                        self.wfile.write(data)
                    return
                html = _WIFI_CALL_HTML.replace("CONN", str(_WIFI_CALL_STATE["reason"])).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)

            def do_POST(self) -> None:
                if self.path.startswith("/reply"):
                    length = int(self.headers.get("Content-Length") or 0)
                    raw_body = self.rfile.read(min(length, 4096)).decode("utf-8", errors="replace")
                    try:
                        text = str(json.loads(raw_body).get("text") or "").strip()
                    except ValueError:
                        text = raw_body.strip()
                    sp = _WIFI_CALL_STATE.get("speaker")
                    lp = _WIFI_CALL_STATE.get("loop")
                    if text and sp is not None and lp is not None:
                        asyncio.run_coroutine_threadsafe(sp.speak(text), lp)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                return

        srv = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        _WIFI_SERVER_URL = f"http://{_local_lan_ip()}:{port}/"
        return _WIFI_SERVER_URL


def _match_lan_device(clean: str, devices: list[dict[str, str]]) -> dict[str, str] | None:
    from ..speech.textnorm import normalize, similarity

    ip_match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", clean)
    if ip_match:
        ip_found = ip_match.group(1)
        by_ip = next((d for d in devices if d["ip"] == ip_found), None)
        return by_ip or {"ip": ip_found, "name": ip_found, "mac": ""}

    if clean.isdigit() and 1 <= int(clean) <= len(devices):
        return devices[int(clean) - 1]

    spoken_clean = re.sub(r"\b(?:trattino|altro|dash|meno|spazio|punto|numero)\b", " ", clean, flags=re.IGNORECASE)
    q_norm = normalize(spoken_clean).replace(" ", "")
    best: tuple[float, dict[str, str]] | None = None
    for d in devices:
        d_norm = normalize(d["name"]).replace(" ", "")
        if q_norm and (q_norm in d_norm or d_norm in q_norm):
            return d
        score = similarity(q_norm, d_norm)
        if best is None or score > best[0]:
            best = (score, d)
    if best is not None and best[0] >= 0.55:
        return best[1]
    return None


def _call_via_wifi(ctx: ToolContext, target: str, reason: str, audio_bytes: bytes = b"", loop: Any = None) -> tuple[str, str]:
    devices = discover_lan_devices()
    clean = (target or "").strip()
    if not clean:
        if not devices:
            raise NeedsInputError(
                tr("Non vedo altri dispositivi attivi sulla rete Wi-Fi al momento. Dimmi l'IP o il nome del dispositivo da chiamare.")
            )
        listing = "\n".join(
            f"{i + 1}. {d['name']} ({d['ip']})" if d["name"] != d["ip"] else f"{i + 1}. {d['ip']}"
            for i, d in enumerate(devices)
        )
        raise NeedsInputError(
            tr("Quale dispositivo devo scegliere della tua rete?\n{devices}").format(devices=listing)
        )

    chosen = _match_lan_device(clean, devices)
    if chosen is None:
        if devices:
            listing = "\n".join(f"{i + 1}. {d['name']} ({d['ip']})" for i, d in enumerate(devices))
            raise NeedsInputError(
                tr("Non trovo «{target}» sulla rete. Quale dispositivo devo scegliere della tua rete?\n{devices}").format(
                    target=clean, devices=listing
                )
            )
        raise NeedsInputError(tr("Non trovo il dispositivo «{target}» sulla rete Wi-Fi.").format(target=clean))

    speaker = getattr(ctx.services, "speaker", None) if ctx.services else None
    call_url = _ensure_wifi_call_endpoint(reason, speaker=speaker, audio_bytes=audio_bytes, loop=loop)
    label = f"{chosen['name']} ({chosen['ip']})" if chosen["name"] != chosen["ip"] else chosen["ip"]
    return tr("Chiamata Wi-Fi avviata verso {device}! Apri sul dispositivo: {url}").format(device=label, url=call_url), call_url


def _choose_platform(ctx: ToolContext, wanted: str) -> str:
    w = (wanted or "auto").strip().lower()
    if w in ("discord", "telegram", "wifi"):
        return w
    settings = getattr(ctx.services, "settings", None) if ctx.services else None
    if settings is not None:
        if getattr(settings, "call_telegram_target", "") and not getattr(settings, "call_discord_target", ""):
            return "telegram"
        if getattr(settings, "call_discord_target", "") and not getattr(settings, "call_telegram_target", ""):
            return "discord"
    if _find_telegram_window() is not None and discord_tool._main_window() is None:
        return "telegram"
    if discord_tool._main_window() is not None:
        return "discord"
    return "telegram" if _telegram_installed(ctx) is not None else "discord"


def _resolve_target(ctx: ToolContext, platform: str, raw_target: str) -> str:
    t = (raw_target or "").strip()
    if t:
        return t
    settings = getattr(ctx.services, "settings", None) if ctx.services else None
    if settings is not None:
        saved = settings.call_telegram_target if platform == "telegram" else settings.call_discord_target
        if saved:
            return saved
    remote = getattr(ctx.services, "remote", None) if ctx.services else None
    if remote is not None:
        for link in getattr(remote, "links", []) or []:
            if str(link.get("platform") or "").lower() == platform:
                disp = str(link.get("display") or "").strip()
                if disp:
                    return disp
    return ""


async def _send_urgent_remote_alert(ctx: ToolContext, platform: str, text: str) -> bool:
    import base64

    remote = getattr(ctx.services, "remote", None) if ctx.services else None
    speaker = getattr(ctx.services, "speaker", None) if ctx.services else None
    if remote is None or not getattr(remote, "links", None):
        return False
    target = next((l for l in remote.links if str(l.get("platform") or "").lower() == platform), None)
    if target is None:
        target = remote.links[0]
    voice_payload: dict[str, str] | None = None
    if speaker is not None and hasattr(speaker, "voice_note"):
        try:
            note = await speaker.voice_note(text)
            if note is not None and len(note) == 2 and note[0]:
                voice_payload = {"mime": str(note[1]), "data": base64.b64encode(note[0]).decode("ascii")}
        except Exception:
            voice_payload = None
    return await remote.notify(
        f"📞 {text}",
        voice=voice_payload,
        target={"platform": target["platform"], "user_id": target["user_id"]},
    )


def send_telegram_message(ctx: ToolContext, args: dict) -> str:
    recipient = str(args.get("recipient") or "").strip()
    message = str(args.get("message") or "").strip()
    if not recipient:
        raise NeedsInputError(tr("A chi devo scrivere su Telegram?"))
    if not message:
        raise NeedsInputError(tr("Il messaggio è vuoto."))
    win = _open_telegram_chat(ctx, recipient)
    if winapi.foreground_window() != win.hwnd:
        raise ToolError(tr("Telegram ha perso il focus: messaggio NON inviato."))
    left, top, right, bottom = winapi.window_rect(win.hwnd)
    winapi.click(left + (right - left) // 2, bottom - 34)
    time.sleep(0.15)
    winapi.type_text(message, newline="shift_enter")
    time.sleep(0.25)
    if winapi.foreground_window() != win.hwnd:
        raise ToolError(tr("Telegram ha perso il focus mentre scrivevo: controlla la chat."))
    winapi.tap(winapi.VK["enter"])
    time.sleep(0.35)
    return tr("Messaggio inviato su Telegram a {target}.").format(target=recipient)


async def call_phone(ctx: ToolContext, args: dict) -> str:
    platform = _choose_platform(ctx, str(args.get("platform") or "auto"))
    raw_recipient = str(args.get("recipient") or "").strip()
    target = _resolve_target(ctx, platform, raw_recipient)
    reason = str(args.get("reason") or "").strip()
    remote = getattr(ctx.services, "remote", None) if ctx.services else None
    speaker = getattr(ctx.services, "speaker", None) if ctx.services else None
    has_remote_links = bool(remote is not None and getattr(remote, "links", None))

    if platform == "wifi":
        spoken_text = reason or tr("Chiamata Wi-Fi da Ressy sul tuo PC!")
        voice_data = b""
        if speaker is not None and hasattr(speaker, "voice_note"):
            try:
                note = await speaker.voice_note(spoken_text)
                if note:
                    voice_data = note[0]
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        msg, call_url = await asyncio.to_thread(_call_via_wifi, ctx, raw_recipient, spoken_text, voice_data, loop)
        if has_remote_links:
            sent = await _send_urgent_remote_alert(ctx, "auto", f"{spoken_text}\n{call_url}")
            if sent:
                return msg + " " + tr("Ti ho inviato anche la notifica con il link sul telefono.")
        return msg

    if not target and has_remote_links:
        alert_text = reason or tr("Chiamata da Ressy sul tuo PC!")
        sent = await _send_urgent_remote_alert(ctx, platform, alert_text)
        if sent:
            return tr("Ti ho inviato una chiamata vocale/notifica urgente su {plat}!").format(plat=platform.title())

    if not target and platform == "telegram":
        raise NeedsInputError(
            tr("Dimmi il contatto o @username Telegram da chiamare (puoi anche salvarlo in Impostazioni › Da remoto).")
        )
    if not target and platform == "discord":
        win = discord_tool._main_window()
        if win is None:
            raise NeedsInputError(
                tr("Dimmi il nome Discord da chiamare (puoi anche salvarlo in Impostazioni › Da remoto).")
            )

    desktop_err = ""
    desktop_msg = ""
    try:
        desktop_msg = await asyncio.to_thread(
            _call_via_telegram if platform == "telegram" else _call_via_discord, ctx, target
        )
    except Exception as exc:
        desktop_err = str(exc)

    remote_sent = False
    if has_remote_links and (reason or desktop_err or not raw_recipient):
        alert_text = reason or tr("Chiamata da Ressy sul tuo PC!")
        try:
            remote_sent = await _send_urgent_remote_alert(ctx, platform, alert_text)
        except Exception:
            remote_sent = False

    if desktop_msg:
        if remote_sent:
            return desktop_msg + " " + tr("Ti ho inviato anche un avviso vocale sul telefono.")
        return desktop_msg
    if remote_sent:
        return tr("Non sono riuscita a far partire la chiamata desktop ({err}), ma ti ho inviato subito un avviso vocale su {plat}.").format(
            err=desktop_err, plat=platform.title()
        )
    raise ToolError(desktop_err or tr("Non sono riuscita ad avviare la chiamata."))


TOOLS = [
    Tool(
        "call_phone",
        "Chiama su Discord, Telegram o Wi-Fi locale (elenca i dispositivi in rete e chiede quale scegliere).",
        params(
            {
                "platform": {"type": "string", "enum": ["auto", "discord", "telegram", "wifi"]},
                "recipient": {"type": "string", "description": "contatto, @username, IP o dispositivo Wi-Fi"},
                "reason": {"type": "string", "description": "motivo o promemoria della chiamata"},
            },
        ),
        call_phone,
        timeout=90,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "send_telegram_message",
        "Invia un messaggio su Telegram Desktop a un contatto o @username.",
        params(
            {
                "recipient": {"type": "string", "description": "nome contatto o @username"},
                "message": {"type": "string", "description": "testo del messaggio"},
            },
            ["recipient", "message"],
        ),
        send_telegram_message,
        timeout=60,
        snapshot_on_error=True,
        uses_screen=True,
    ),
]
