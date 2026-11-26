from __future__ import annotations

import json
import logging
import sys
import time

import re

from ..speech.textnorm import normalize, similarity
from ..speech.wake import phonetic
from . import platform_os, screen, winapi
from .apps import launch
from ..paths import app_dir
from .registry import Tool, ToolContext, ToolError, params
from ..i18n import tr

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

def sounds_like(a: str, b: str) -> float:
    na, nb = normalize(a).replace(" ", ""), normalize(b).replace(" ", "")
    if not na or not nb:
        return 0.0
    pa, pb = phonetic(na), phonetic(nb)
    return max(similarity(na, nb), similarity(pa, pb))


def known_name(recipient: str, contacts: list[str] | None = None) -> str:
    contacts = known_contacts() if contacts is None else contacts
    best, score = recipient, 0.0
    for name in contacts:
        value = sounds_like(recipient, name)
        if value > score:
            best, score = name, value
    return best if score >= 0.72 else recipient


_HERE = re.compile(
    r"^(?:qui|qua|questa chat|la chat (?:aperta|attuale|corrente)|chat (?:aperta|attuale|corrente)|"
    r"(?:il |la |questo |questa )?(?:gruppo|canale|server|chat)(?: (?:in cui|dove|che) (?:sono|sto|ho aperto|e aperto|è aperto)"
    r"(?: adesso| ora)?| attuale| aperto| aperta| corrente| di adesso)?|dove sono(?: adesso| ora)?|"
    r"(?:il )?(?:gruppo|canale) (?:dove|in cui) (?:sono|sto)(?: adesso| ora)?)$"
)


def means_current_chat(recipient: str) -> bool:
    return bool(_HERE.match(normalize(recipient)))


log = logging.getLogger("ressy.discord")

PROCESSES = ("discord.exe", "discordptb.exe", "discordcanary.exe")
APP_NAMES = ("Discord", "Discord PTB", "Discord Canary")
MAX_LENGTH = 2000
_SUFFIXES = (
    " - discord canary", " | discord canary", "discord canary | ",
    " - discord ptb", " | discord ptb", "discord ptb | ",
    " - discord", " | discord", "discord | ",
)


def _main_window() -> winapi.Window | None:
    if sys.platform != "win32":
        for item in platform_os.unix_top_windows():
            proc = str(item.get("process") or "").lower()
            title = str(item.get("title") or "").lower()
            if ("discord" in proc or "discord" in title) and "updater" not in title:
                return winapi.Window(hwnd=int(item["handle"]), title=str(item["title"]), pid=int(item["pid"]), class_name=str(item["process"]))
        return None
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
    raise ToolError(tr("Discord non sembra installato su questo PC."))


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
    width, height = right - left, bottom - top
    return left + width // 5, top, right, top + min(180, max(120, height // 8))


def _try_read(region: tuple[int, int, int, int]) -> tuple[list[screen.Line], bool]:
    try:
        return screen.read_text(region), True
    except Exception:
        log.info("OCR unavailable", exc_info=True)
        return [], False


def _read(region: tuple[int, int, int, int]) -> list[screen.Line]:
    lines, _ = _try_read(region)
    return lines


def _clean_name(text: str) -> str:
    return text.strip().lstrip("@#").strip()


def _result_rows(lines: list[screen.Line], query_text: str) -> list[screen.Line] | None:
    search_y = None
    target_norm = normalize(query_text)
    if target_norm:
        for line in lines:
            if similarity(normalize(line.text), target_norm) >= 0.82:
                search_y = line.box[3]
                break
    if search_y is None:
        for line in lines:
            if screen.find_text([line], query_text, threshold=0.80) is not None:
                search_y = line.box[3]
                break
    if search_y is None:
        return None
    min_len = 1 if len(_clean_name(query_text)) <= 1 else 2
    rows = [line for line in lines if line.box[1] > search_y + 4 and len(_clean_name(line.text)) >= min_len]
    return rows[:8]


def pick_result(lines: list[screen.Line], recipient: str, query_text: str) -> tuple[float, tuple[int, int], str] | None:
    rows = _result_rows(lines, query_text)
    if not rows:
        return None
    found = screen.find_text(rows, recipient, threshold=0.72)
    if found is not None:
        score, line, point = found
        return score, point, line.text
    names = [row for row in rows if _looks_like_a_name(row.text)]
    if len(names) == 1:
        row = names[0]
        head = _clean_name(row.text).split("  ")[0]
        if sounds_like(head.split()[0] if head.split() else head, recipient) >= 0.55 \
                or sounds_like(head, recipient) >= 0.55:
            x0, y0, x1, y1 = row.box
            return 0.55, ((x0 + x1) // 2, (y0 + y1) // 2), row.text
    return None


_SWITCHER_HEADERS = (
    "cerca", "search", "suggerimento", "protip", "consiglio", "messaggi diretti", "direct messages",
    "canali di testo", "text channels", "canali vocali", "voice channels", "ultimi canali", "recent channels",
    "dove vuoi andare", "where would you like to go", "amici", "friends", "server", "servers",
)


def _looks_like_a_name(text: str) -> bool:
    t = _clean_name(text)
    low = t.lower()
    return 1 <= len(t) <= 60 and not any(low.startswith(h) for h in _SWITCHER_HEADERS)


def visible_names(lines: list[screen.Line], query_text: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for line in _result_rows(lines, query_text) or []:
        text = _clean_name(line.text)
        if not _looks_like_a_name(text) or normalize(text) == normalize(query_text):
            continue
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def header_confirms(lines: list[screen.Line], recipient: str) -> bool:
    return screen.find_text(lines, recipient, threshold=0.8) is not None


def _clear_switcher() -> None:
    if sys.platform != "win32":
        platform_os.send_hotkey(platform_os.mod_key(), "a")
        time.sleep(0.05)
        platform_os.tap_key("backspace")
        time.sleep(0.05)
        platform_os.tap_key("esc")
        time.sleep(0.2)
        return
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


def _wait_confirmed(hwnd: int, title_before: str, recipient: str, kind: str, use_ocr: bool, row: str,
                    timeout: float = 3.5) -> str:
    names = [recipient]
    clicked = _clean_name(row).split("  ")[0].strip()
    if clicked and normalize(clicked) != normalize(recipient):
        names.append(clicked)
    deadline = time.monotonic() + timeout
    checked_header = False
    while True:
        time.sleep(0.4)
        title_after = winapi.window_title(hwnd)
        if any(chat_confirmed(title_before, title_after, name, kind) for name in names):
            return "title"
        if use_ocr and (time.monotonic() > deadline - 1.5 or not checked_header):
            header = _read(_header_region(hwnd))
            checked_header = True
            if any(header_confirms(header, name) for name in names):
                return "header"
        if time.monotonic() > deadline:
            return ""


def _open_chat(window: winapi.Window, recipient: str, kind: str) -> str:
    if sys.platform != "win32":
        platform_os.unix_focus_window(window.hwnd, window.class_name)
        time.sleep(0.2)
        for query in _queries(recipient, kind):
            platform_os.tap_key("esc")
            time.sleep(0.15)
            platform_os.send_hotkey(platform_os.mod_key(), "k")
            time.sleep(0.6)
            platform_os.type_text(query)
            time.sleep(1.1)
            platform_os.tap_key("enter")
            time.sleep(0.8)
            now_win = _main_window()
            if now_win and chat_confirmed(window.title, now_win.title, recipient, kind):
                return "title"
        raise _Stuck(
            tr("Non ho trovato la chat con '{recipient}' su Discord (o non sono riuscita a verificarla): il messaggio NON è stato inviato.{hint}").format(
                recipient=recipient, hint=tr(" Chiedi all'utente di ripetere o scrivere il nome come appare su Discord.")
            )
        )
    hwnd = window.hwnd
    use_ocr = screen.ocr_available()
    offered: list[str] = []
    for query in _queries(recipient, kind):
        title_before = winapi.window_title(hwnd)
        lines: list[screen.Line] = []
        rows: list[screen.Line] | None = None
        for attempt in range(3):
            winapi.tap(winapi.VK["esc"])
            time.sleep(0.15)
            winapi.hotkey(winapi.VK["ctrl"], winapi.VK["k"])
            time.sleep(0.7)
            winapi.type_text(query)
            time.sleep(1.2)
            if winapi.foreground_window() != hwnd:
                raise ToolError(tr("Discord ha perso il focus mentre cercavo la chat: messaggio NON inviato."))
            if not use_ocr:
                break
            lines, ocr_ok = _try_read(_overlay_region(hwnd))
            if not ocr_ok:
                use_ocr = False
                break
            rows = _result_rows(lines, query)
            if rows is not None:
                break
            if attempt < 2:
                log.info("discord switcher did not open yet, waiting briefly and retrying")
                _clear_switcher()
                time.sleep(1.8)
                winapi.focus_window(hwnd)

        row_text = ""
        if use_ocr:
            choice = pick_result(lines, recipient, query)
            if choice is None:
                offered = visible_names(lines, query) or offered
                log.info("discord switcher: no row matches (query %d chars)", len(query))
                _clear_switcher()
                continue
            score, (x, y), row_text = choice
            log.info("discord switcher: clicking a row (score %.2f)", score)
            winapi.click(x, y)
        else:
            winapi.tap(winapi.VK["enter"])
        confirmed = _wait_confirmed(hwnd, title_before, recipient, kind, use_ocr, row_text)
        if confirmed:
            return confirmed
        log.info("discord: chat opened but not confirmed")
        winapi.tap(winapi.VK["esc"])
        time.sleep(0.3)
    hint = (tr(" Nella ricerca di Discord ci sono: {join}. Chiedi all'utente se intendeva uno di questi e, se sì, riprova con quel nome esatto.").format(join=', '.join(offered))) if offered else \
        tr(" Chiedi all'utente di ripetere o scrivere il nome come appare su Discord.")
    raise _Stuck(
        tr("Non ho trovato la chat con '{recipient}' su Discord (o non sono riuscita a verificarla): il messaggio NON è stato inviato.{hint}").format(recipient=recipient, hint=hint)
    )


def _ensure_discord_ready(ctx: ToolContext) -> winapi.Window:
    if sys.platform != "win32":
        window = _main_window()
        if window is None:
            _launch_discord(ctx)
            window = _wait_main_window(40)
            if window is None:
                raise ToolError(tr("Discord non si è aperto in tempo. Riprova tra poco."))
            time.sleep(3.0)
            window = _main_window() or window
        platform_os.unix_focus_window(window.hwnd, window.class_name)
        time.sleep(0.35)
        return window
    if not winapi.input_desktop_available():
        raise ToolError(tr("Il PC è bloccato: non posso usare Discord finché non viene sbloccato."))
    window = _main_window()
    if window is None:
        _launch_discord(ctx)
        window = _wait_main_window(40)
        if window is None:
            raise ToolError(tr("Discord non si è aperto in tempo. Riprova tra poco."))
        time.sleep(4.0)
        window = _main_window() or window
    winapi.wait_modifiers_released()
    if not winapi.focus_window(window.hwnd):
        raise ToolError(tr("Non riesco a portare Discord in primo piano."))
    time.sleep(0.35)
    return window


def send_discord_message(ctx: ToolContext, args: dict) -> str:
    recipient = _clean_name(args.get("recipient") or "")
    message = args["message"].strip()
    kind = args.get("kind") if args.get("kind") in ("user", "channel", "current") else "user"
    if kind != "current" and (not recipient or means_current_chat(recipient)):
        kind = "current" if recipient else kind
    if kind != "current" and not recipient:
        raise ToolError(tr("A chi devo scrivere?"))
    if kind == "user":
        recipient = known_name(recipient)
    if not message:
        raise ToolError(tr("Il messaggio è vuoto."))
    if len(message) > MAX_LENGTH:
        raise ToolError(tr("Il messaggio è troppo lungo per Discord ({len} caratteri, massimo {MAX_LENGTH}).").format(len=len(message), MAX_LENGTH=MAX_LENGTH))

    window = _ensure_discord_ready(ctx)

    if sys.platform != "win32":
        if kind == "current":
            platform_os.tap_key("esc")
            time.sleep(0.15)
        else:
            _open_chat(window, recipient, kind)
        platform_os.type_text(message + " ", newline="shift_enter")
        time.sleep(0.35)
        platform_os.tap_key("enter")
        time.sleep(0.4)
        cur = _main_window()
        target = _chat_name(cur.title if cur else "")
        if not target or target.lower() in ("discord", "discord canary", "discord ptb"):
            target = recipient or tr("la chat aperta")
        if kind == "user":
            remember_contact(_clean_name(target.split(" | ")[0]) if target.startswith("@") else recipient)
        return tr("Messaggio inviato su Discord a {target}.").format(target=target)

    if kind == "current":
        winapi.tap(winapi.VK["esc"])
        time.sleep(0.15)
    else:
        _open_chat(window, recipient, kind)

    if winapi.foreground_window() != window.hwnd:
        raise ToolError(tr("Discord ha perso il focus: messaggio NON inviato."))
    winapi.type_text(message + " ", newline="shift_enter")
    time.sleep(0.35)
    if winapi.foreground_window() != window.hwnd:
        raise ToolError(tr("Discord ha perso il focus mentre scrivevo: controlla la chat, il messaggio potrebbe non essere partito."))
    winapi.tap(winapi.VK["enter"])
    time.sleep(0.4)
    target = _chat_name(winapi.window_title(window.hwnd))
    if not target or target.lower() in ("discord", "discord canary", "discord ptb"):
        target = recipient or tr("la chat aperta")
    if kind == "user":
        remember_contact(_clean_name(target.split(" | ")[0]) if target.startswith("@") else recipient)
    return tr("Messaggio inviato su Discord a {target}.").format(target=target)


def read_discord_chat(ctx: ToolContext, args: dict) -> str:
    if not screen.ocr_available():
        raise ToolError(tr("Il riconoscimento del testo sullo schermo non è disponibile per leggere Discord."))
    recipient = _clean_name(args.get("recipient") or "")
    kind = args.get("kind") if args.get("kind") in ("user", "channel", "current") else ("user" if recipient else "current")
    if kind != "current" and (not recipient or means_current_chat(recipient)):
        kind = "current"
    if kind == "user" and recipient:
        recipient = known_name(recipient)

    window = _ensure_discord_ready(ctx)
    if sys.platform != "win32":
        if kind == "current":
            platform_os.tap_key("esc")
            time.sleep(0.15)
        else:
            _open_chat(window, recipient, kind)
        lines, ok = _try_read(None)
        if not ok:
            raise ToolError(tr("Non riesco a leggere il testo nella finestra di Discord."))
        target = _chat_name((_main_window() or window).title) or recipient or tr("Discord")
        text = "\n".join(line.text for line in lines if line.text.strip())
        if not text.strip():
            return tr("Non vedo messaggi leggibili nella chat di {target}.").format(target=target)
        return tr("Messaggi visibili in {target}:\n{text}").format(target=target, text=text[:4000])
    if kind == "current":
        winapi.tap(winapi.VK["esc"])
        time.sleep(0.15)
    else:
        _open_chat(window, recipient, kind)

    left, top, right, bottom = winapi.window_rect(window.hwnd)
    width, height = right - left, bottom - top
    chat_region = (left + width // 5, top + 50, right - 20, max(top + 120, bottom - 70))
    lines, ok = _try_read(chat_region)
    if not ok:
        raise ToolError(tr("Non riesco a leggere il testo nella finestra di Discord."))
    target = _chat_name(winapi.window_title(window.hwnd)) or recipient or tr("Discord")
    text = "\n".join(line.text for line in lines if line.text.strip())
    if not text.strip():
        return tr("Non vedo messaggi leggibili nella chat di {target}.").format(target=target)
    return tr("Messaggi visibili in {target}:\n{text}").format(target=target, text=text[:4000])


TOOLS = [
    Tool(
        "send_discord_message",
        "Invia un messaggio su Discord a un amico, a un canale o nella chat aperta (kind=current). "
        "Apre Discord e trova la chat da solo: non chiamare open_app prima.",
        params(
            {
                "recipient": {"type": "string", "description": "nome dell'amico o del canale (senza @ o #) come lo ha "
                                                              "detto l'utente; vuoto se kind=current"},
                "message": {"type": "string", "description": "testo esatto da inviare, in prima persona come lo "
                                                            "scriverebbe l'utente (es. «arrivo tra 10 minuti»)"},
                "kind": {"type": "string", "enum": ["user", "channel", "current"],
                         "description": "user = persona (default), channel = canale di un server, current = chat aperta"},
            },
            ["message"],
        ),
        send_discord_message,
        timeout=90,
        snapshot_on_error=True,
        uses_screen=True,
    ),
    Tool(
        "read_discord_chat",
        "Legge i messaggi visibili in una chat o canale Discord (o nella chat aperta).",
        params(
            {
                "recipient": {"type": "string", "description": "nome amico o canale (opzionale: vuoto = chat aperta)"},
                "kind": {"type": "string", "enum": ["user", "channel", "current"]},
            },
        ),
        read_discord_chat,
        timeout=60,
        snapshot_on_error=True,
        uses_screen=True,
    ),
]

