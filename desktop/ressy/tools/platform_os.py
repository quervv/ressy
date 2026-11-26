from __future__ import annotations

import datetime as dt
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from configparser import ConfigParser
from pathlib import Path
from typing import Any

from ..i18n import tr
from ..paths import user_folder

log = logging.getLogger("ressy.os")

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def mod_key() -> str:
    return "cmd" if IS_MACOS else "ctrl"


def open_path(target: str | Path) -> None:
    value = str(target)
    if IS_WINDOWS:
        os.startfile(value)
        return
    if IS_MACOS:
        subprocess.Popen(["open", value], start_new_session=True, close_fds=True)
        return
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if opener is None:
        raise OSError(tr("Impossibile aprire: xdg-open non è installato."))
    cmd = [opener, "open", value] if Path(opener).name == "gio" else [opener, value]
    subprocess.Popen(cmd, start_new_session=True, close_fds=True)


def _run_osascript(script: str, timeout: float = 10.0) -> str:
    res = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        timeout=timeout,
    )
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or "osascript failed")
    return res.stdout.decode("utf-8", errors="replace").strip()


def _apple_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def input_ready() -> bool:
    if IS_WINDOWS:
        from . import winapi

        return winapi.input_desktop_available()
    return True


def wait_modifiers_released(timeout: float = 1.0) -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.wait_modifiers_released(timeout)
        return
    time.sleep(0.05)


def _pynput_key(name: str):
    from pynput.keyboard import Key, KeyCode

    k = name.strip().lower()
    mapping = {
        "ctrl": Key.ctrl,
        "control": Key.ctrl,
        "alt": Key.alt,
        "shift": Key.shift,
        "win": Key.cmd,
        "cmd": Key.cmd,
        "command": Key.cmd,
        "super": Key.cmd,
        "enter": Key.enter,
        "return": Key.enter,
        "tab": Key.tab,
        "esc": Key.esc,
        "escape": Key.esc,
        "space": Key.space,
        "backspace": Key.backspace,
        "delete": Key.delete,
        "del": Key.delete,
        "up": Key.up,
        "down": Key.down,
        "left": Key.left,
        "right": Key.right,
        "home": Key.home,
        "end": Key.end,
        "pageup": Key.page_up,
        "pagedown": Key.page_down,
        **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 21) if hasattr(Key, f"f{i}")},
    }
    if k in mapping:
        return mapping[k]
    if len(k) == 1:
        return KeyCode.from_char(k)
    raise ValueError(tr("Tasto sconosciuto: '{token}'.").format(token=name))


def validate_keys(spec: str) -> list[Any]:
    if IS_WINDOWS:
        from . import winapi

        return winapi.parse_keys(spec)
    tokens = [t.strip() for t in re.split(r"[+\s]+", spec.lower()) if t.strip()]
    if not tokens:
        raise ValueError(tr("Specifica i tasti da premere."))
    return [_pynput_key(tok) for tok in tokens]


def send_hotkey(*keys: Any) -> None:
    if IS_WINDOWS:
        from . import winapi

        if keys and isinstance(keys[0], str):
            resolved = [winapi.VK[mod_key() if k == "mod" else k.lower()] for k in keys]
            winapi.hotkey(*resolved)
        else:
            winapi.hotkey(*keys)
        return
    from pynput.keyboard import Controller

    resolved = [_pynput_key(mod_key() if k == "mod" else k) if isinstance(k, str) else k for k in keys]
    ctrl = Controller()
    for k in resolved[:-1]:
        ctrl.press(k)
    if resolved:
        ctrl.press(resolved[-1])
        ctrl.release(resolved[-1])
    for k in reversed(resolved[:-1]):
        ctrl.release(k)


def tap_key(key: str) -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.tap(winapi.VK[key.lower()])
        return
    from pynput.keyboard import Controller

    Controller().tap(_pynput_key(key))


def type_text(text: str, newline: str = "enter") -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.type_text(text, newline=newline)
        return
    if IS_MACOS and text:
        try:
            old_clip = get_clipboard()
        except Exception:
            old_clip = ""
        set_clipboard(text)
        send_hotkey("cmd", "v")
        time.sleep(0.08)
        if old_clip:
            try:
                set_clipboard(old_clip)
            except Exception:
                pass
        return
    from pynput.keyboard import Controller, Key

    ctrl = Controller()
    for ch in text:
        if ch == "\n":
            if newline == "shift_enter":
                with ctrl.pressed(Key.shift):
                    ctrl.tap(Key.enter)
            else:
                ctrl.tap(Key.enter)
        else:
            ctrl.type(ch)


def move_mouse(x: int, y: int) -> None:
    if IS_WINDOWS:
        from . import winapi

        if not winapi.user32.SetCursorPos(int(x), int(y)):
            raise OSError("SetCursorPos failed")
        return
    from pynput.mouse import Controller

    Controller().position = (int(x), int(y))


def click_mouse(x: int, y: int, *, right: bool = False, double: bool = False) -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.click(int(x), int(y), right=right, double=double)
        return
    from pynput.mouse import Button, Controller

    mouse = Controller()
    mouse.position = (int(x), int(y))
    time.sleep(0.03)
    btn = Button.right if right else Button.left
    mouse.click(btn, 2 if double else 1)


def scroll_mouse(*, dx: int = 0, dy: int = 0) -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.scroll(dx=dx, dy=dy)
        return
    from pynput.mouse import Controller

    Controller().scroll(int(dx), int(dy))


def get_clipboard() -> str:
    if IS_WINDOWS:
        from . import winapi

        return winapi.get_clipboard_text()
    if IS_MACOS:
        res = subprocess.run(["pbpaste"], capture_output=True, timeout=5)
        return res.stdout.decode("utf-8", errors="replace")
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-o", "-selection", "clipboard"], ["xsel", "-ob"]):
        if shutil.which(cmd[0]):
            res = subprocess.run(cmd, capture_output=True, timeout=5)
            if res.returncode == 0:
                return res.stdout.decode("utf-8", errors="replace")
    return ""


def set_clipboard(text: str) -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.set_clipboard_text(text)
        return
    if IS_MACOS:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
        return
    for cmd in (["wl-copy"], ["xclip", "-i", "-selection", "clipboard"], ["xsel", "-ib"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
            return
    raise OSError(tr("Nessun gestore appunti trovato (xclip, xsel o wl-copy)."))


def clear_clipboard() -> None:
    if IS_WINDOWS:
        from . import winapi

        winapi.clear_clipboard()
        return
    set_clipboard("")


def unix_top_windows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if IS_MACOS:
        script = (
            'tell application "System Events"\n'
            'set frontApp to name of first application process whose frontmost is true\n'
            'set outText to ""\n'
            'repeat with p in (every application process whose visible is true)\n'
            'set pname to name of p\n'
            'set pidVal to unix id of p\n'
            'set wtitle to pname\n'
            'try\n'
            'if (count of windows of p) > 0 then set wtitle to name of first window of p\n'
            'end try\n'
            'set isFront to "0"\n'
            'if pname is frontApp then set isFront to "1"\n'
            'set outText to outText & pidVal & "\t" & pname & "\t" & isFront & "\t" & wtitle & "\n"\n'
            'end repeat\n'
            'return outText\n'
            'end tell'
        )
        try:
            raw = _run_osascript(script, timeout=8.0)
        except Exception:
            return []
        for idx, line in enumerate(raw.splitlines()):
            parts = line.split("\t", 3)
            if len(parts) == 4:
                pid = int(parts[0]) if parts[0].isdigit() else 0
                out.append({
                    "handle": pid or (idx + 1),
                    "pid": pid,
                    "process": parts[1],
                    "front": parts[2] == "1",
                    "title": parts[3] or parts[1],
                })
        return out
    if IS_LINUX and shutil.which("wmctrl"):
        try:
            res = subprocess.run(["wmctrl", "-lp"], capture_output=True, timeout=5)
            active_id = ""
            if shutil.which("xdotool"):
                ar = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, timeout=3)
                if ar.returncode == 0 and ar.stdout.strip().isdigit():
                    active_id = hex(int(ar.stdout.strip()))[2:].lower()
            for line in res.stdout.decode("utf-8", errors="replace").splitlines():
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    wid_hex, _desk, pid_s, _host, title = parts
                    wid = int(wid_hex, 16)
                    pid = int(pid_s) if pid_s.isdigit() else 0
                    out.append({
                        "handle": wid,
                        "pid": pid,
                        "process": title.split(" - ")[-1],
                        "front": bool(active_id and wid_hex.lower().endswith(active_id)),
                        "title": title,
                    })
        except Exception:
            return []
    return out


def unix_focus_window(handle: int, process_name: str = "") -> bool:
    if IS_MACOS:
        if process_name:
            try:
                _run_osascript(f'tell application {_apple_quote(process_name)} to activate')
                return True
            except Exception:
                pass
        if handle:
            try:
                _run_osascript(f'tell application "System Events" to set frontmost of first process whose unix id is {handle} to true')
                return True
            except Exception:
                return False
    if IS_LINUX:
        if shutil.which("wmctrl") and handle:
            res = subprocess.run(["wmctrl", "-i", "-a", hex(handle)], capture_output=True, timeout=5)
            return res.returncode == 0
        if shutil.which("xdotool") and handle:
            res = subprocess.run(["xdotool", "windowactivate", str(handle)], capture_output=True, timeout=5)
            return res.returncode == 0
    return False


def unix_close_window(handle: int, process_name: str = "") -> None:
    if IS_MACOS:
        target = process_name
        if target:
            try:
                _run_osascript(f'tell application {_apple_quote(target)} to quit')
                return
            except Exception:
                pass
    if IS_LINUX and handle:
        if shutil.which("wmctrl"):
            subprocess.run(["wmctrl", "-i", "-c", hex(handle)], capture_output=True, timeout=5)
            return
        if shutil.which("xdotool"):
            subprocess.run(["xdotool", "windowclose", str(handle)], capture_output=True, timeout=5)
            return


def media_action(action: str) -> bool:
    if IS_MACOS:
        if action in ("play_pause", "next", "previous", "stop"):
            for app in ("Spotify", "Music"):
                running = subprocess.run(["pgrep", "-x", app], capture_output=True).returncode == 0
                if running:
                    cmd = {
                        "play_pause": "playpause",
                        "next": "next track",
                        "previous": "previous track",
                        "stop": "stop",
                    }[action]
                    _run_osascript(f'tell application "{app}" to {cmd}')
                    return True
        if action == "mute":
            cur = _run_osascript("output muted of (get volume settings)")
            target = "false" if cur.lower() == "true" else "true"
            _run_osascript(f"set volume output muted {target}")
            return True
    if IS_LINUX:
        if action == "mute":
            if shutil.which("wpctl"):
                subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], check=False, timeout=5)
                return True
            if shutil.which("pactl"):
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], check=False, timeout=5)
                return True
        if shutil.which("playerctl"):
            p_cmd = {
                "play_pause": "play-pause",
                "next": "next",
                "previous": "previous",
                "stop": "stop",
            }.get(action)
            if p_cmd:
                subprocess.run(["playerctl", p_cmd], check=False, timeout=5)
                return True
    from pynput.keyboard import Controller, Key

    mapping = {
        "play_pause": getattr(Key, "media_play_pause", None),
        "next": getattr(Key, "media_next", None),
        "previous": getattr(Key, "media_previous", None),
        "stop": getattr(Key, "media_stop", None),
        "mute": getattr(Key, "media_volume_mute", None),
    }
    key = mapping.get(action)
    if key is None:
        return False
    Controller().tap(key)
    return True


def unix_set_volume(*, level: int | None = None, change: str | None = None, steps: int = 5) -> str:
    delta = steps * 2
    if IS_MACOS:
        if level is not None:
            lvl = max(0, min(100, int(level)))
            _run_osascript(f"set volume output volume {lvl}")
            return tr("Volume impostato al {level}%.").format(level=lvl)
        if change in ("up", "down"):
            cur_s = _run_osascript("output volume of (get volume settings)")
            cur = int(cur_s) if cur_s.isdigit() else 50
            nxt = max(0, min(100, cur + (delta if change == "up" else -delta)))
            _run_osascript(f"set volume output volume {nxt}")
            return (tr("Volume alzato del {percent}%.") if change == "up" else tr("Volume abbassato del {percent}%.")).format(percent=delta)
        if change == "mute":
            media_action("mute")
            return tr("Audio disattivato/riattivato.")
    if IS_LINUX:
        if shutil.which("pactl"):
            if level is not None:
                lvl = max(0, min(100, int(level)))
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{lvl}%"], check=False, timeout=5)
                return tr("Volume impostato al {level}%.").format(level=lvl)
            if change in ("up", "down"):
                sign = "+" if change == "up" else "-"
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{delta}%"], check=False, timeout=5)
                return (tr("Volume alzato del {percent}%.") if change == "up" else tr("Volume abbassato del {percent}%.")).format(percent=delta)
            if change == "mute":
                media_action("mute")
                return tr("Audio disattivato/riattivato.")
        if shutil.which("wpctl"):
            if level is not None:
                lvl = max(0, min(100, int(level)))
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{lvl / 100:.2f}"], check=False, timeout=5)
                return tr("Volume impostato al {level}%.").format(level=lvl)
            if change in ("up", "down"):
                op = f"{delta}%+" if change == "up" else f"{delta}%-"
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", op], check=False, timeout=5)
                return (tr("Volume alzato del {percent}%.") if change == "up" else tr("Volume abbassato del {percent}%.")).format(percent=delta)
            if change == "mute":
                media_action("mute")
                return tr("Audio disattivato/riattivato.")
    raise OSError("Audio mixer CLI unavailable")


def unix_pc_power(action: str, delay_seconds: int) -> str:
    if IS_MACOS:
        if action == "lock":
            subprocess.run(["pmset", "displaysleepnow"], check=False, timeout=5)
            return tr("PC bloccato.")
        if action == "sleep":
            subprocess.Popen(["pmset", "sleepnow"], start_new_session=True)
            return tr("Metto il PC in sospensione appena ho risposto.")
        if action in ("shutdown", "restart"):
            mins = max(1, (delay_seconds + 59) // 60)
            verb = "shut down" if action == "shutdown" else "restart"
            _run_osascript(f'tell application "System Events" to {verb}')
            return (tr("Spengo il PC tra {delay} secondi.") if action == "shutdown" else tr("Riavvio il PC tra {delay} secondi.")).format(delay=mins * 60)
        if action == "cancel":
            return tr("Non c'era nessuno spegnimento programmato.")
    if IS_LINUX:
        if action == "lock":
            if shutil.which("loginctl"):
                subprocess.run(["loginctl", "lock-session"], check=False, timeout=5)
            elif shutil.which("xdg-screensaver"):
                subprocess.run(["xdg-screensaver", "lock"], check=False, timeout=5)
            return tr("PC bloccato.")
        if action == "sleep":
            subprocess.Popen(["systemctl", "suspend"], start_new_session=True)
            return tr("Metto il PC in sospensione appena ho risposto.")
        if action in ("shutdown", "restart"):
            mins = max(1, (delay_seconds + 59) // 60)
            flag = "-h" if action == "shutdown" else "-r"
            subprocess.run(["shutdown", flag, f"+{mins}"], check=False, timeout=5)
            return (tr("Spengo il PC tra {delay} secondi. Per annullare chiedimi di annullare lo spegnimento.")
                    if action == "shutdown"
                    else tr("Riavvio il PC tra {delay} secondi. Per annullare chiedimi di annullare il riavvio.")).format(delay=mins * 60)
        if action == "cancel":
            res = subprocess.run(["shutdown", "-c"], capture_output=True, check=False, timeout=5)
            return tr("Spegnimento annullato.") if res.returncode == 0 else tr("Non c'era nessuno spegnimento programmato.")
    raise OSError("Unsupported platform")


def unix_empty_trash() -> bool:
    targets: list[Path] = []
    if IS_MACOS:
        targets.append(Path.home() / ".Trash")
    elif IS_LINUX:
        data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
        targets.extend([data_home / "Trash/files", data_home / "Trash/info"])
    ok = False
    for folder in targets:
        if folder.is_dir():
            for child in list(folder.iterdir()):
                try:
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                    ok = True
                except OSError:
                    pass
    return ok


def unix_recycle(path: Path) -> bool:
    if IS_MACOS:
        try:
            _run_osascript(f'tell application "Finder" to delete POSIX file {_apple_quote(str(path))}')
            return True
        except Exception:
            return False
    if IS_LINUX:
        if shutil.which("gio"):
            res = subprocess.run(["gio", "trash", str(path)], capture_output=True, timeout=10)
            if res.returncode == 0:
                return True
        trash_files = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "Trash/files"
        try:
            trash_files.mkdir(parents=True, exist_ok=True)
            dst = trash_files / path.name
            if dst.exists():
                dst = trash_files / f"{path.stem}-{int(time.time())}{path.suffix}"
            shutil.move(str(path), str(dst))
            return True
        except OSError:
            return False
    return False


def unix_set_theme(dark: bool) -> bool:
    if IS_MACOS:
        val = "true" if dark else "false"
        _run_osascript(f'tell application "System Events" to tell appearance preferences to set dark mode to {val}')
        return True
    if IS_LINUX and shutil.which("gsettings"):
        scheme = "prefer-dark" if dark else "prefer-light"
        res = subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", scheme], capture_output=True, timeout=5)
        return res.returncode == 0
    return False


def unix_wifi_ssid() -> str:
    try:
        if IS_MACOS:
            res = subprocess.run(["networksetup", "-getairportnetwork", "en0"], capture_output=True, timeout=5)
            out = res.stdout.decode("utf-8", errors="replace").strip()
            if ":" in out and "not associated" not in out.lower():
                return out.split(":", 1)[1].strip()
        elif IS_LINUX and shutil.which("nmcli"):
            res = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], capture_output=True, timeout=5)
            for line in res.stdout.decode("utf-8", errors="replace").splitlines():
                if line.startswith("yes:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def find_unix_apps() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    if IS_MACOS:
        roots = [Path("/Applications"), Path.home() / "Applications", Path("/System/Applications"), Path("/System/Applications/Utilities")]
        for root in roots:
            if not root.is_dir():
                continue
            for app in sorted(root.glob("*.app")) + sorted(root.glob("*/*.app")):
                name = app.stem
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    found.append((name, str(app)))
        resolve_app = Path("/Applications/DaVinci Resolve/DaVinci Resolve.app")
        if resolve_app.is_dir() and "davinci resolve" not in seen:
            found.append(("DaVinci Resolve", str(resolve_app)))
        return found

    if IS_LINUX:
        xdg_dirs = [
            Path.home() / ".local/share/applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
            Path.home() / ".local/share/flatpak/exports/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
        ]
        for folder in xdg_dirs:
            if not folder.is_dir():
                continue
            for desktop in folder.glob("*.desktop"):
                cp = ConfigParser(interpolation=None)
                try:
                    cp.read(desktop, encoding="utf-8")
                    sec = cp["Desktop Entry"]
                except Exception:
                    continue
                if sec.getboolean("NoDisplay", False) or sec.getboolean("Hidden", False):
                    continue
                name = (sec.get("Name") or "").strip()
                exec_cmd = (sec.get("Exec") or "").strip()
                if not name or not exec_cmd:
                    continue
                cleaned = re.sub(r"\s+%[fFuUdDnNickvm]", "", exec_cmd).strip()
                if name.lower() not in seen:
                    seen.add(name.lower())
                    found.append((name, cleaned))
        resolve_bin = Path("/opt/resolve/bin/resolve")
        if resolve_bin.is_file() and "davinci resolve" not in seen:
            found.append(("DaVinci Resolve", str(resolve_bin)))
    return found


def launch_unix_target(target: str) -> None:
    if IS_MACOS:
        if target.endswith(".app") or "://" in target or Path(target).exists():
            open_path(target)
            return
        subprocess.Popen(["open", "-a", target], start_new_session=True, close_fds=True)
        return
    if "://" in target or target.endswith(".desktop"):
        open_path(target)
        return
    argv = shlex.split(target)
    subprocess.Popen(argv, start_new_session=True, close_fds=True)


_UNIX_DANGEROUS = re.compile(
    r"(rm\s+-[a-z]*rf[a-z]*\s+/($|\s)|rm\s+-[a-z]*fr[a-z]*\s+/($|\s)|mkfs\.|dd\s+.*of=/dev/|"
    r":\(\)\s*\{\s*:\|\s*:\&\s*\};:|>\s*/dev/sd|curl[^|;]*\|\s*(sh|bash)|wget[^|;]*\|\s*(sh|bash)|"
    r"\bshutdown\b|\breboot\b|\bhalt\b|poweroff)",
    re.IGNORECASE,
)


def run_unix_shell(command: str, cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    if _UNIX_DANGEROUS.search(command):
        raise ValueError(tr("Questo comando può danneggiare il PC o i dati: non lo eseguo. Fallo tu se sei sicuro."))
    shell = "/bin/zsh" if IS_MACOS and Path("/bin/zsh").exists() else "/bin/bash"
    if not Path(shell).exists():
        shell = "/bin/sh"
    res = subprocess.run([shell, "-lc", command], capture_output=True, timeout=timeout, cwd=str(cwd))
    return res.returncode, res.stdout.decode("utf-8", errors="replace").strip(), res.stderr.decode("utf-8", errors="replace").strip()


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_with_tesseract(image) -> list[tuple[str, list[tuple[str, int, int, int, int]]]]:
    exe = shutil.which("tesseract")
    if not exe:
        raise RuntimeError("tesseract not found")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        image.save(tmp_path, "PNG")
        res = subprocess.run([exe, str(tmp_path), "stdout", "--psm", "6", "tsv"], capture_output=True, timeout=20)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.decode("utf-8", errors="replace"))
        rows = res.stdout.decode("utf-8", errors="replace").splitlines()
    finally:
        tmp_path.unlink(missing_ok=True)
    grouped: dict[tuple[str, str, str, str], list[tuple[str, int, int, int, int]]] = {}
    for line in rows[1:]:
        cols = line.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        key = (cols[1], cols[2], cols[3], cols[4])
        grouped.setdefault(key, []).append((text, int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9])))
    out = []
    for words in grouped.values():
        out.append((" ".join(w[0] for w in words), words))
    return out


def unix_system_drive() -> str:
    return "/" if not IS_WINDOWS else os.environ.get("SystemDrive", "C:") + "\\"


def user_home_folders() -> list[str]:
    return [str(user_folder(k)) for k in ("desktop", "documents", "downloads", "pictures", "music", "videos")]


def timestamp_slug() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")
