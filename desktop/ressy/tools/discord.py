from __future__ import annotations

import json
import logging
import time

from ..speech.textnorm import normalize, similarity
from . import screen, winapi
from .apps import launch
from ..paths import app_dir
from .registry import Tool, ToolContext, ToolError, params

MAX_CONTACTS = 30


def _contacts_path():
    return app_dir() / "discord_contacts.json"


def known_contacts() -> list[str]:
    try:
        data = json.loads(_contacts_path().read_text(encoding="utf-8"))
        return [str(x) for x in data if isinstance(x, str)][:MAX_CONTACTS]
    except (OSError, ValueError):
        return []


def remember_contact(name: str) -> None:
    names = [n for n in known_contacts() if n.lower() != name.lower()]
    try:
        _contacts_path().write_text(json.dumps([name, *names][:MAX_CONTACTS], ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.debug("could not save the contact list", exc_info=True)

log = logging.getLogger("ressy.discord")

PROCESSES = ("discord.exe", "discordptb.exe", "discordcanary.exe")
APP_NAMES = ("Discord", "Discord PTB", "Discord Canary")
MAX_LENGTH = 2000
_SUFFIXES = (" - discord", " | discord", "discord | ")


def _main_window() -> winapi.Window | None:
    best: tuple[int, winapi.Window] | None = None
    for window in winapi.top_windows():
        if window.process_name.lower() not in PROCESSES:
            continue
        if "updater" in window.title.lower():
            continue
        width, height = winapi.window_size(window.hwnd)
        if width < 400 or height < 300:
            continue
        area = width * height
        if best is None or area > best[0]:
            best = (area, window)
    return best[1] if best else None


def _launch_discord(ctx: ToolContext) -> None:
    index = ctx.services.apps
    for name in APP_NAMES:
        entry, _ = index.find(name)
        if entry is not None and "discord" in entry.norm:
            launch(entry)
            return
    raise ToolError("Discord non sembra installato su questo PC.")


def _wait_main_window(timeout: float) -> winapi.Window | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window = _main_window()
        if window is not None:
            return window
        time.sleep(0.5)
    return None


def _chat_name(title: str) -> str:
    t = title.strip()
    lowered = t.lower()
    for suffix in _SUFFIXES:
        if lowered.endswith(suffix):
            t = t[: -len(suffix)]
            lowered = t.lower()
        elif lowered.startswith(suffix):
            t = t[len(suffix):]
            lowered = t.lower()
    return t.strip()


def _names_match(heard: str, wanted: str) -> bool:
    a, b = normalize(heard), normalize(wanted)
    if not a or not b:
        return False
    if a == b or all(tok in a.split() for tok in b.split()):
        return True
    compact_a, compact_b = a.replace(" ", ""), b.replace(" ", "")
    return compact_b in compact_a or similarity(compact_a, compact_b) >= 0.8


def chat_confirmed(title_before: str, title_after: str, recipient: str, kind: str) -> bool:
    chat = _chat_name(title_after)
    marker = "#" if kind == "channel" else "@"
    if chat.startswith(marker):
        head = chat[1:].split(" | ")[0]
        return _names_match(head, recipient)
    return title_after != title_before and _names_match(chat, recipient)


def _overlay_region(hwnd: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = winapi.window_rect(hwnd)
    width, height = right - left, bottom - top
    return left + width // 6, top + height // 8, right - width // 6, bottom - height // 8


def _header_region(hwnd: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = winapi.window_rect(hwnd)
    width = right - left
    return left + width // 5, top, right, top + 110


def _read(region: tuple[int, int, int, int]) -> list[screen.Line]:
    try:
        return screen.read_text(region)
    except Exception:
        log.info("OCR unavailable", exc_info=True)
        return []


def _clean_name(text: str) -> str:
    return text.strip().lstrip("@#").strip()


def pick_result(lines: list[screen.Line], recipient: str, query_text: str) -> tuple[float, tuple[int, int], str] | None:
    search_y = None
    for line in lines:
        if screen.find_text([line], query_text, threshold=0.85) is not None:
            search_y = line.box[3]
            break
    if search_y is None:
        return None
    candidates = [line for line in lines if line.box[1] > search_y + 4]
    found = screen.find_text(candidates, recipient, threshold=0.72)
    if found is None:
        return None
    score, line, point = found
    return score, point, line.text


def visible_names(lines: list[screen.Line], query_text: str, limit: int = 6) -> list[str]:
    out: list[str] = []
    for line in lines:
        text = _clean_name(line.text)
        if len(text) < 2 or normalize(text) == normalize(query_text):
            continue
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def header_confirms(lines: list[screen.Line], recipient: str) -> bool:
    return screen.find_text(lines, recipient, threshold=0.8) is not None


def _clear_switcher() -> None:
    winapi.hotkey(winapi.VK["ctrl"], winapi.VK["a"])
    time.sleep(0.05)
    winapi.tap(winapi.VK["backspace"])
    time.sleep(0.05)
    winapi.tap(winapi.VK["esc"])
    time.sleep(0.2)


def _queries(recipient: str, kind: str) -> list[str]:
    marker = "#" if kind == "channel" else "@"
    out = [marker + recipient, recipient]
    words = recipient.split()
    if len(words) > 1:
        out.append(max(words, key=len))
    seen: set[str] = set()
    return [q for q in out if not (q.lower() in seen or seen.add(q.lower()))]


class _Stuck(ToolError):
    pass


def _open_chat(window: winapi.Window, recipient: str, kind: str) -> str:
    hwnd = window.hwnd
    use_ocr = screen.ocr_available()
    offered: list[str] = []
    for query in _queries(recipient, kind):
        title_before = winapi.window_title(hwnd)
        winapi.tap(winapi.VK["esc"])
        time.sleep(0.15)
        winapi.hotkey(winapi.VK["ctrl"], winapi.VK["k"])
        time.sleep(0.7)
        winapi.type_text(query)
        time.sleep(1.2)
        if winapi.foreground_window() != hwnd:
            raise ToolError("Discord ha perso il focus mentre cercavo la chat: messaggio NON inviato.")

        if use_ocr:
            lines = _read(_overlay_region(hwnd))
            choice = pick_result(lines, recipient, query)
            if choice is None:
                offered = visible_names(lines, query) or offered
                log.info("discord switcher: no row matches (query %d chars)", len(query))
                _clear_switcher()
                continue
            score, (x, y), row = choice
            log.info("discord switcher: clicking a row (score %.2f)", score)
            winapi.click(x, y)
        else:
            winapi.tap(winapi.VK["enter"])
        time.sleep(1.3)

        title_after = winapi.window_title(hwnd)
        if chat_confirmed(title_before, title_after, recipient, kind):
            return "title"
        if use_ocr and header_confirms(_read(_header_region(hwnd)), recipient):
            return "header"
        log.info("discord: chat opened but not confirmed")
        winapi.tap(winapi.VK["esc"])
        time.sleep(0.3)
    hint = f" Su Discord vedo: {', '.join(offered)}." if offered else ""
    raise _Stuck(
        f"Non ho trovato la chat con '{recipient}' su Discord (o non sono riuscita a verificarla): "
        f"il messaggio NON è stato inviato.{hint}"
    )


def send_discord_message(ctx: ToolContext, args: dict) -> str:
    recipient = _clean_name(args["recipient"])
    message = args["message"].strip()
    kind = "channel" if args.get("kind") == "channel" else "user"
    if not recipient:
        raise ToolError("A chi devo scrivere?")
    if not message:
        raise ToolError("Il messaggio è vuoto.")
    if len(message) > MAX_LENGTH:
        raise ToolError(f"Il messaggio è troppo lungo per Discord ({len(message)} caratteri, massimo {MAX_LENGTH}).")
    if not winapi.input_desktop_available():
        raise ToolError("Il PC è bloccato: non posso scrivere su Discord finché non viene sbloccato.")

    window = _main_window()
    if window is None:
        _launch_discord(ctx)
        window = _wait_main_window(40)
        if window is None:
            raise ToolError("Discord non si è aperto in tempo. Riprova tra poco.")
        time.sleep(4.0)
        window = _main_window() or window

    winapi.wait_modifiers_released()
    if not winapi.focus_window(window.hwnd):
        raise ToolError("Non riesco a portare Discord in primo piano.")
    time.sleep(0.35)

    _open_chat(window, recipient, kind)

    if winapi.foreground_window() != window.hwnd:
        raise ToolError("Discord ha perso il focus: messaggio NON inviato.")
    winapi.type_text(message + " ", newline="shift_enter")
    time.sleep(0.35)
    if winapi.foreground_window() != window.hwnd:
        raise ToolError("Discord ha perso il focus mentre scrivevo: controlla la chat, il messaggio potrebbe non essere partito.")
    winapi.tap(winapi.VK["enter"])
    time.sleep(0.4)
    target = _chat_name(winapi.window_title(window.hwnd))
    if not target or target.lower() == "discord":
        target = recipient
    remember_contact(recipient)
    return f"Messaggio inviato su Discord a {target}."


TOOLS = [
    Tool(
        "send_discord_message",
        "Scrive e invia un messaggio su Discord (app desktop) a un utente o a un canale. Apre Discord se serve.",
        params(
            {
                "recipient": {"type": "string", "description": "nome utente/amico (come appare su Discord), o nome del canale senza #"},
                "message": {"type": "string", "description": "testo esatto da inviare"},
                "kind": {"type": "string", "enum": ["user", "channel"], "description": "default user"},
            },
            ["recipient", "message"],
        ),
        send_discord_message,
        timeout=90,
        snapshot_on_error=True,
    ),
]

