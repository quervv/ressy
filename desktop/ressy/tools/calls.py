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


def _choose_platform(ctx: ToolContext, wanted: str) -> str:
    w = (wanted or "auto").strip().lower()
    if w in ("discord", "telegram"):
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
    remote = getattr(ctx.services, "remote", None) if ctx.services else None
    speaker = getattr(ctx.services, "speaker", None) if ctx.services else None
    if remote is None or not getattr(remote, "links", None):
        return False
    target = next((l for l in remote.links if str(l.get("platform") or "").lower() == platform), None)
    if target is None:
        target = remote.links[0]
    voice = None
    if speaker is not None and hasattr(speaker, "voice_note"):
        try:
            voice = await speaker.voice_note(text)
        except Exception:
            voice = None
    return await remote.notify(
        f"📞 {text}",
        voice=voice,
        target={"platform": target["platform"], "user_id": target["user_id"]},
    )


def call_phone(ctx: ToolContext, args: dict) -> str:
    platform = _choose_platform(ctx, str(args.get("platform") or "auto"))
    target = _resolve_target(ctx, platform, str(args.get("recipient") or ""))
    reason = str(args.get("reason") or "").strip()

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
        desktop_msg = _call_via_telegram(ctx, target) if platform == "telegram" else _call_via_discord(ctx, target)
    except Exception as exc:
        desktop_err = str(exc)

    remote_sent = False
    if reason or desktop_err:
        alert_text = reason or tr("Chiamata da Ressy sul tuo PC!")
        try:
            loop = getattr(ctx.services, "loop", None) if ctx.services else None
            if loop is not None and loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_send_urgent_remote_alert(ctx, platform, alert_text), loop)
                remote_sent = bool(fut.result(timeout=12))
            else:
                remote_sent = asyncio.run(_send_urgent_remote_alert(ctx, platform, alert_text))
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
        "Chiama un contatto o l'utente su Discord o Telegram (app desktop + avviso vocale sul telefono) per appuntamenti o altro.",
        params(
            {
                "platform": {"type": "string", "enum": ["auto", "discord", "telegram"]},
                "recipient": {"type": "string", "description": "nome contatto o @username (vuoto = contatto salvato)"},
                "reason": {"type": "string", "description": "motivo o promemoria della chiamata"},
            },
        ),
        call_phone,
        timeout=90,
        snapshot_on_error=True,
        uses_screen=True,
    ),
]
