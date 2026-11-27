from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import platform
import re
import logging
import os
import secrets
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import httpx

from ..config import LOCAL_LLM_MODELS
from ..i18n import language, tr
from .groq import ChatResult, GroqError

log = logging.getLogger("ressy.llm.local")

LLAMA_TAG = "b12728"
_RUNTIME_SPECS: dict[tuple[str, str], tuple[str, str, int, str]] = {
    ("win32", "amd64"): (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-win-cpu-x64.zip",
        "a8ace09d44bb10e2617268c55c3f2db0e0adeedd9c1ba722969920665a3ae698",
        25,
        "llama-server.exe",
    ),
    ("win32", "arm64"): (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-win-cpu-arm64.zip",
        "c4babfa1a8ba38b7a86f3719c7254cf15b918eca81179b1a0c76a23779d3985a",
        13,
        "llama-server.exe",
    ),
    ("darwin", "arm64"): (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-macos-arm64.tar.gz",
        "001140842db7fa5253e57f891c14db5377937faf07d955a2646b471df0e7d9bd",
        17,
        "llama-server",
    ),
    ("darwin", "x86_64"): (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-macos-x64.tar.gz",
        "817b0faa91432ff32ccd6895a7b11a19f0d6ee57d3800c75e93c7d78265c1a9d",
        13,
        "llama-server",
    ),
    ("linux", "x86_64"): (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-ubuntu-x64.tar.gz",
        "7c8d787ff15384423d6742a42fad8e7e453d61b94a9c4cd85296e800d538b178",
        23,
        "llama-server",
    ),
    ("linux", "arm64"): (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-ubuntu-arm64.tar.gz",
        "fd00c6490374e11509e22feebfeb3e576662736a18c1ce56b190e388c2e7b003",
        19,
        "llama-server",
    ),
}


def _runtime_spec() -> tuple[str, str, int, str]:
    plat = "darwin" if sys.platform == "darwin" else ("win32" if sys.platform == "win32" else "linux")
    mach = platform.machine().lower()
    if mach in ("aarch64", "arm64"):
        arch = "arm64"
    elif plat == "win32":
        arch = "amd64"
    else:
        arch = "x86_64"
    return _RUNTIME_SPECS.get((plat, arch)) or _RUNTIME_SPECS[(plat, "amd64" if plat == "win32" else "x86_64")]


LLAMA_URL, LLAMA_SHA256, LLAMA_MB, _SERVER_BIN = _runtime_spec()
_RUNTIME_FILES = (
    "llama-server.exe", "llama-server",
    "llama-server-impl.dll", "llama-common.dll", "llama.dll", "mtmd.dll",
    "libomp.dll", "ggml.dll", "ggml-base.dll", "ggml-rpc.dll",
)
_READY_MARK = ".ressy-ok"

IDLE_STOP_S = 150
START_TIMEOUT_S = 120

LOCAL_TOOLS = (
    "open_app", "close_app", "focus_app", "open_url", "web_search", "play_youtube", "media_control", "set_volume",
    "weather", "take_screenshot", "system_status", "reminder", "call_phone", "create_folder", "open_folder", "list_windows",
    "pc_power", "set_clipboard", "type_text", "press_keys", "go_to_sleep", "api_usage", "web_answer", "wait",
)
LOCAL_TOOLS_FULL = LOCAL_TOOLS + (
    "call_phone", "send_telegram_message", "send_discord_message", "read_discord_chat", "write_in_app",
    "create_file", "read_file", "list_folder", "file_action", "find_files",
    "record_video", "edit_video", "download_file", "run_python",
    "read_screen", "click_text", "window_action", "mouse_action", "clipboard",
    "notes", "timer", "system_control", "read_webpage", "compose_email", "run_powershell",
)
_MAX_HISTORY = 2
_LOCAL_CONTINUE_LOOKING = frozenset({
    "list_windows", "read_screen", "list_folder", "read_file", "find_files", "read_webpage", "read_discord_chat", "clipboard",
})
_SCREENSHOT_ASK = re.compile(
    r"\b(?:screenshot|screen\s*shot|schermata|fotograf\w*|cattura\w*|mostra\w*\s+(?:lo\s+)?schermo|"
    r"vedi\s+(?:cosa|lo)\s+schermo|guarda\s+(?:lo\s+)?schermo|show\s+(?:me\s+)?(?:the\s+)?screen)\b",
    re.IGNORECASE,
)


def _wants_screenshot(text: str) -> bool:
    return bool(_SCREENSHOT_ASK.search(text or ""))
_LOCAL_PREPARING = frozenset({"open_app", "focus_app", "open_url", "open_folder", "window_action"})
_LOCAL_OPEN_ONLY = re.compile(
    r"^\W*(?:apri\w*|avvia\w*|lancia\w*|esegui\w*|vai\b|porta\w*|passa\b|torna\b|minimizz\w*|massimizz\w*|"
    r"open|launch|start|run|go|switch|bring|focus|minimize|maximize)\b",
    re.I,
)
_LOCAL_MORE_VERBS = re.compile(
    r"\b(?:scriv\w*|mand\w*|invi\w*|clicca\w*|leggi\w*|cerca\w*|crea\w*|copia\w*|incolla\w*|salva\w*|"
    r"esegui\w*|scarica\w*|edita\w*|monta\w*|convert\w*|sinistra|destra|schermo intero|primo piano|"
    r"write|send|click|read|search|create|copy|paste|save|run|execute|download|edit|left|right|fullscreen)\b",
    re.I,
)
_LOCAL_SECONDARY = re.compile(
    r"\b(?:e\s+(?:poi|dopo|subito|esegui\w*|lancia\w*|apri\w*|salva\w*|manda\w*|invia\w*|scriv\w*|verifica\w*)|"
    r"ed\s+(?:esegui\w*|apri\w*|edita\w*)|and\s+(?:then|run|execute|open|save|send|write|check))\b",
    re.IGNORECASE,
)
_MULTI_ARG_TOOLS = frozenset({
    "run_python", "run_powershell", "create_file", "read_file", "file_action",
    "download_file", "write_in_app", "type_text", "press_keys", "mouse_action",
    "click_text", "open_url", "web_search", "web_answer", "open_app", "open_folder",
    "find_files", "edit_video", "send_discord_message",
})

Progress = Callable[[int, int], None]


def models_dir() -> Path:
    from ..speech.local_stt import models_dir as base

    path = base() / "llm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_path(name: str) -> Path:
    return models_dir() / LOCAL_LLM_MODELS[name][2]


def runtime_dir() -> Path:
    from ..paths import app_dir

    path = app_dir() / "llama" / LLAMA_TAG
    path.mkdir(parents=True, exist_ok=True)
    return path


def server_exe() -> Path:
    return runtime_dir() / _SERVER_BIN


def runtime_ready() -> bool:
    return (runtime_dir() / _READY_MARK).is_file() and server_exe().is_file()


def model_ready(name: str) -> bool:
    if name not in LOCAL_LLM_MODELS:
        return False
    path = model_path(name)
    return path.is_file() and path.stat().st_size > LOCAL_LLM_MODELS[name][1] * 0.9e6


def is_downloaded(name: str) -> bool:
    return model_ready(name) and runtime_ready()


def installed() -> list[str]:
    return [name for name in LOCAL_LLM_MODELS if is_downloaded(name)]


def download_size_mb(name: str) -> int:
    size = 0 if model_ready(name) else LOCAL_LLM_MODELS[name][1]
    return size + (0 if runtime_ready() else LLAMA_MB)


def _wanted(member: str) -> bool:
    base = member.replace("\\", "/").rsplit("/", 1)[-1]
    return (
        base in _RUNTIME_FILES
        or (base.startswith("ggml-cpu") and (base.endswith(".dll") or ".so" in base or base.endswith(".dylib")))
        or ".so" in base
        or base.endswith(".dylib")
        or base.startswith("LICENSE")
    )


def install_runtime(archive: Path, target: Path | None = None) -> Path:
    digest = hashlib.sha256()
    with archive.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    expected_sha = LLAMA_SHA256 if LLAMA_SHA256 != _RUNTIME_SPECS[("win32", "amd64")][1] else _runtime_spec()[1]
    exe_name = _runtime_spec()[3]
    if digest.hexdigest() != expected_sha:
        raise OSError(tr("il motore AI scaricato non corrisponde a quello ufficiale"))
    target = target or runtime_dir()
    if archive.name.endswith(".tar.gz") or archive.suffix == ".tgz":
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile() or not _wanted(member.name):
                    continue
                name = member.name.replace("\\", "/").rsplit("/", 1)[-1]
                src = tf.extractfile(member)
                if src is None:
                    continue
                dst_path = target / name
                with src, dst_path.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                if os.name == "posix" and (name == exe_name or ".so" in name or name.endswith(".dylib")):
                    os.chmod(dst_path, 0o755)
    else:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir() or not _wanted(info.filename):
                    continue
                name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
                dst_path = target / name
                with zf.open(info) as src, dst_path.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                if os.name == "posix" and name == exe_name:
                    os.chmod(dst_path, 0o755)
    if not (target / exe_name).is_file():
        raise OSError(tr("llama-server non trovato nell'archivio"))
    (target / _READY_MARK).write_text(LLAMA_TAG, encoding="utf-8")
    return target


def download(name: str, progress: Progress | None = None, cancel: threading.Event | None = None) -> Path:
    from ..speech.local_stt import download_file

    url, _sha, rt_mb, _exe = _runtime_spec()
    total = download_size_mb(name) * 1_000_000
    offset = 0

    def step(done: int, _total: int) -> None:
        if progress is not None:
            progress(offset + done, max(total, offset + done))

    if not runtime_ready():
        ext = ".tar.gz" if url.endswith(".tar.gz") else ".zip"
        archive = runtime_dir() / f"llama{ext}"
        try:
            download_file(url, archive, rt_mb, step, cancel)
            install_runtime(archive)
        finally:
            archive.unlink(missing_ok=True)
        offset += rt_mb * 1_000_000
    if not model_ready(name):
        _label, mb, _file, url = LOCAL_LLM_MODELS[name]
        download_file(url, model_path(name), mb, step, cancel)
    return model_path(name)


def delete_others(keep: str) -> None:
    for name in LOCAL_LLM_MODELS:
        if name != keep:
            model_path(name).unlink(missing_ok=True)


def _tool_line(schema: dict[str, Any], limit: int = 90) -> str:
    fn = schema.get("function") or {}
    props = (fn.get("parameters") or {}).get("properties") or {}
    required = set((fn.get("parameters") or {}).get("required") or [])
    args = []
    for name, spec in props.items():
        hint = "|".join(map(str, spec["enum"])) if "enum" in spec else spec.get("type", "string")
        args.append(f"{name}{'' if name in required else '?'}: {hint}")
    description = str(fn.get("description") or "").split(". ")[0].split(" (")[0][:limit]
    return f"- {fn.get('name')}({', '.join(args)}): {description}"


_EXAMPLES = (
    ("apri spotify", {"azione": "open_app", "argomenti": {"name": "Spotify"}, "risposta": ""}),
    ("scrivi su discord a marco ciao", {
        "azione": "send_discord_message",
        "argomenti": {"recipient": "Marco", "message": "ciao", "kind": "user"},
        "risposta": "",
    }),
    ("scrivi su discord nel canale generale arrivo", {
        "azione": "send_discord_message",
        "argomenti": {"recipient": "generale", "message": "arrivo", "kind": "channel"},
        "risposta": "",
    }),
    ("edita un video", {"azione": "edit_video", "argomenti": {"editor": "auto"}, "risposta": ""}),
    ("metti lofi su youtube", {"azione": "play_youtube", "argomenti": {"query": "lofi"}, "risposta": ""}),
    ("crea il file lista.txt con pane e latte", {
        "azione": "create_file",
        "argomenti": {"name": "lista.txt", "content": "pane e latte"},
        "risposta": "",
    }),
    ("calcola i primi 10 quadrati in python", {
        "azione": "run_python",
        "argomenti": {"code": "print([i*i for i in range(1, 11)])"},
        "risposta": "",
    }),
    ("che tempo fa a Torino?", {"azione": "weather", "argomenti": {"city": "Torino"}, "risposta": ""}),
    ("come stai?", {"azione": "rispondi", "argomenti": {}, "risposta": "Benissimo, grazie! Cosa faccio per te?"}),
)
_EXAMPLES_EN = (
    ("open spotify", {"azione": "open_app", "argomenti": {"name": "Spotify"}, "risposta": ""}),
    ("send marco on discord hi", {
        "azione": "send_discord_message",
        "argomenti": {"recipient": "Marco", "message": "hi", "kind": "user"},
        "risposta": "",
    }),
    ("edit a video", {"azione": "edit_video", "argomenti": {"editor": "auto"}, "risposta": ""}),
    ("play lofi on youtube", {"azione": "play_youtube", "argomenti": {"query": "lofi"}, "risposta": ""}),
    ("what's the weather in London?", {"azione": "weather", "argomenti": {"city": "London"}, "risposta": ""}),
    ("how are you?", {"azione": "rispondi", "argomenti": {}, "risposta": "Very well, thanks! What can I do for you?"}),
)


def build_prompt(tools: list[dict[str, Any]], user_name: str = "", lang: str | None = None) -> str:
    limit = 55 if len(tools) > 25 else 90
    lines = "\n".join(_tool_line(t, limit) for t in tools)
    names = {(t.get("function") or {}).get("name") for t in tools}
    if (lang or language()) == "en":
        whose = f"{user_name}'s" if user_name else "this"
        examples = "\n".join(
            f"User: {said}\nYou: {json.dumps(answer, ensure_ascii=False)}"
            for said, answer in _EXAMPLES_EN if answer["azione"] in names or answer["azione"] == "rispondi"
        )
        return (
            f"You are Ressy, the voice assistant on {whose} PC. Answer ONLY the current user request.\n"
            "Use the tools below to accomplish ANYTHING requested (apps, find_files, web_answer, download_file, "
            "run_python, run_powershell, UI, edit_video), or choose \"rispondi\" only for chatting/questions. "
            "Never say «I can't» and never invent file paths (for edit_video without user files, omit files). "
            "Never call take_screenshot unless explicitly asked for a screenshot.\n\n"
            f"Tools:\n{lines}\n\nExamples:\n{examples}"
        )
    who = f" di {user_name}" if user_name else ""
    examples = "\n".join(
        f"Utente: {said}\nTu: {json.dumps(answer, ensure_ascii=False)}"
        for said, answer in _EXAMPLES if answer["azione"] in names or answer["azione"] == "rispondi"
    )
    return (
        f"Sei Ressy, l'assistente personale sul PC{who}. Rispondi SOLO all'ultima richiesta attuale dell'utente.\n"
        "Usa gli strumenti qui sotto per fare QUALSIASI cosa richiesta (app, find_files, web_answer, download_file, "
        "run_python, run_powershell, UI, edit_video), oppure scegli \"rispondi\" solo per parlare. "
        "Non dire mai «non posso», non inventare nomi di file (per edit_video senza file reali non mettere files) e "
        "non usare take_screenshot se non richiesto esplicitamente.\n\n"
        f"Strumenti:\n{lines}\n\nEsempi:\n{examples}"
    )


def answer_schema(names: list[str], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    params = {(t.get("function") or {}).get("name"): (t.get("function") or {}).get("parameters") for t in tools or []}
    branches: list[dict[str, Any]] = [{
        "type": "object",
        "properties": {"azione": {"const": "rispondi"}, "argomenti": {"type": "object", "maxProperties": 0},
                       "risposta": {"type": "string", "minLength": 1, "maxLength": 2000}},
        "required": ["azione", "argomenti", "risposta"],
    }]
    for name in names:
        schema = params.get(name) or {"type": "object", "properties": {}}
        arguments = {"type": "object", "properties": schema.get("properties") or {},
                     "required": schema.get("required") or [], "additionalProperties": False}
        branches.append({
            "type": "object",
            "properties": {"azione": {"const": name}, "argomenti": arguments, "risposta": {"type": "string",
                                                                                           "maxLength": 300}},
            "required": ["azione", "argomenti", "risposta"],
        })
    return {"anyOf": branches}


def to_local_messages(messages: list[dict[str, Any]], system: str) -> list[dict[str, str]]:
    non_system = [m for m in messages if m.get("role") != "system"]
    last_user_idx = max((i for i, m in enumerate(non_system) if m.get("role") == "user"), default=0)

    context_note = ""
    if last_user_idx >= 2:
        prev_u = ""
        prev_a = ""
        for m in reversed(non_system[:last_user_idx]):
            if not prev_a and m.get("role") == "assistant" and not m.get("tool_calls"):
                prev_a = str(m.get("content") or "").strip()[:180]
            elif prev_a and m.get("role") == "user":
                prev_u = str(m.get("content") or "").strip()[:120]
                break
        if prev_u and prev_a:
            context_note = f"[Contesto precedente (solo se la nuova richiesta vi si riferisce): «{prev_u}» → «{prev_a}»]\n"

    out: list[dict[str, str]] = []
    for offset, message in enumerate(non_system[last_user_idx:]):
        role = message.get("role")
        if role == "assistant":
            calls = message.get("tool_calls") or []
            if calls:
                fn = calls[0].get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                text = json.dumps({"azione": fn.get("name"), "argomenti": args, "risposta": ""}, ensure_ascii=False)
            else:
                text = json.dumps({"azione": "rispondi", "argomenti": {}, "risposta": str(message.get("content") or "")},
                                  ensure_ascii=False)
            out.append({"role": "assistant", "content": text})
        elif role == "tool":
            out.append({"role": "user", "content": f"{tr('Risultato di ')}{message.get('name')}: {message.get('content')}"})
        else:
            content = str(message.get("content") or "")
            if offset == 0 and context_note:
                content = context_note + content
            out.append({"role": "user", "content": content})
    return [{"role": "system", "content": system}, *out]


_CLAIMS_DONE = re.compile(r"^\s*(fatto|ho (?:aperto|avviato|scritto|mandato|inviato|messo|chiuso|cercato|impostato)"
                          r"|done|i(?:'ve| have)? (?:opened|started|written|wrote|sent|put|closed|searched|set))\b",
                          re.I)


_PLACEHOLDER_VIDEOS = frozenset({"downloaded_video.mp4", "video.mp4", "input.mp4", "example.mp4", "sample.mp4", "clip.mp4"})


def parse_reply(raw: str, allowed: set[str], step_id: str) -> dict[str, Any]:
    text = (raw or "").strip()
    data: Any = None
    try:
        data = json.loads(text)
    except ValueError:
        if text.startswith("{"):
            m_act = re.search(r'"azione"\s*:\s*"([^"]+)"', text)
            if m_act and m_act.group(1) in allowed:
                act = m_act.group(1)
                args_salvaged: dict[str, Any] = {}
                m_ed = re.search(r'"editor"\s*:\s*"([^"]+)"', text)
                if m_ed and act == "edit_video":
                    args_salvaged["editor"] = m_ed.group(1)
                data = {"azione": act, "argomenti": args_salvaged, "risposta": ""}
            else:
                m_rep = re.search(r'"risposta"\s*:\s*"((?:[^"\\]|\\.)*)', text)
                if m_rep and m_rep.group(1).strip():
                    return {"role": "assistant", "content": m_rep.group(1).replace('\\"', '"').strip()}
                return {"role": "assistant", "content": tr("Non sono riuscita a completare la risposta, riprova.")}
        else:
            return {"role": "assistant", "content": text}
    if not isinstance(data, dict):
        return {"role": "assistant", "content": str(data)}
    action = str(data.get("azione") or "rispondi")
    args = data.get("argomenti") if isinstance(data.get("argomenti"), dict) else {}
    if action == "edit_video" and isinstance(args.get("files"), list):
        kept = [f for f in args["files"] if str(f).strip().lower() not in _PLACEHOLDER_VIDEOS or Path(str(f)).exists()]
        if kept:
            args["files"] = kept
        else:
            args.pop("files", None)
    reply = str(data.get("risposta") or "").strip()
    if action == "rispondi" or action not in allowed:
        return {"role": "assistant", "content": reply}
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": step_id, "type": "function",
            "function": {"name": action, "arguments": json.dumps(args, ensure_ascii=False)},
        }],
    }


def result_reply(messages: list[dict[str, Any]]) -> str | None:
    if not messages or messages[-1].get("role") != "tool":
        return None
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = str(m.get("content") or "")
            break
    step_match = re.search(r"(?:Ora fai solo l'azione|Now do only action) \d+:\s*(.+)$", last_user, re.MULTILINE)
    order_text = step_match.group(1) if step_match else last_user

    parts = []
    tool_names: list[str] = []
    all_ok = True
    needs_input_msg = ""
    for message in reversed(messages):
        if message.get("role") != "tool":
            break
        name = str(message.get("name") or "")
        tool_names.append(name)
        try:
            result = json.loads(message.get("content") or "{}")
        except ValueError:
            result = {}
        ok = bool(result.get("ok"))
        if not ok:
            all_ok = False
            if result.get("needs_input") and not needs_input_msg:
                needs_input_msg = str(result.get("errore") or "").strip()
        text = str(result.get("esito") or "") if ok else \
            tr("Non ci sono riuscita: ") + str(result.get("errore") or tr("errore sconosciuto"))
        parts.append(text.strip())

    if needs_input_msg:
        return needs_input_msg

    tool_count_in_turn = 0
    for message in reversed(messages):
        if message.get("role") == "user":
            break
        if message.get("role") == "tool":
            tool_count_in_turn += 1

    if not all_ok and tool_count_in_turn < 3:
        return None

    if all_ok and tool_names:
        looking = _LOCAL_CONTINUE_LOOKING if _wants_screenshot(order_text) else (_LOCAL_CONTINUE_LOOKING | {"take_screenshot"})
        if all(n in looking for n in tool_names):
            return None
        if all(n in _LOCAL_PREPARING for n in tool_names) and (
            not _LOCAL_OPEN_ONLY.match(order_text) or _LOCAL_MORE_VERBS.search(order_text)
        ):
            return None
        if (
            tool_count_in_turn == 1
            and _LOCAL_SECONDARY.search(order_text)
            and not (set(tool_names) & {"send_discord_message", "edit_video", "run_python", "run_powershell"})
        ):
            return None
    return " ".join(reversed([p for p in parts if p])) or tr("Fatto.")


def _norm_call_args(call: dict[str, Any]) -> str:
    raw = call.get("arguments") or "{}"
    try:
        return json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False)
    except ValueError:
        return str(raw)


def _repeat_guard(message: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    calls = message.get("tool_calls")
    if not calls or not messages or messages[-1].get("role") != "tool":
        return message
    cur_call = (calls[0].get("function") or {})
    cur_name = cur_call.get("name")
    cur_args = _norm_call_args(cur_call)
    try:
        last_result = json.loads(messages[-1].get("content") or "{}")
    except ValueError:
        last_result = {}

    non_system = [m for m in messages if m.get("role") != "system"]
    last_user_idx = max((i for i, m in enumerate(non_system) if m.get("role") == "user"), default=0)
    turn_msgs = non_system[last_user_idx:]

    prior_calls: list[tuple[str, str, dict[str, Any]]] = []
    for idx, msg in enumerate(turn_msgs):
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                res_obj: dict[str, Any] = {}
                for nxt in turn_msgs[idx + 1:]:
                    if nxt.get("role") == "tool" and nxt.get("tool_call_id") == tc.get("id"):
                        try:
                            res_obj = json.loads(nxt.get("content") or "{}")
                        except ValueError:
                            res_obj = {}
                        break
                prior_calls.append((str(fn.get("name") or ""), _norm_call_args(fn), res_obj))

    for p_name, p_args, p_res in reversed(prior_calls):
        if p_name != cur_name:
            continue
        p_ok = bool(p_res.get("ok"))
        if p_args == cur_args or (p_ok and cur_name not in _MULTI_ARG_TOOLS):
            return {"role": "assistant", "content": str(p_res.get("esito") or p_res.get("errore") or last_result.get("esito") or "Fatto.")}
    return message


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _KillOnExit:

    def __init__(self) -> None:
        self.handle = None
        if os.name != "nt":
            return
        try:
            kernel32 = ctypes.windll.kernel32

            class _Basic(ctypes.Structure):
                _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", ctypes.c_uint32),
                            ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", ctypes.c_uint32),
                            ("f", ctypes.c_size_t), ("g", ctypes.c_uint32), ("h", ctypes.c_uint32)]

            class _Extended(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", ctypes.c_uint64 * 6),
                            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            kernel32.CreateJobObjectW.restype = ctypes.c_void_p
            handle = kernel32.CreateJobObjectW(None, None)
            info = _Extended()
            info.BasicLimitInformation.LimitFlags = 0x2000
            if handle and kernel32.SetInformationJobObject(ctypes.c_void_p(handle), 9, ctypes.byref(info),
                                                           ctypes.sizeof(info)):
                self.handle = handle
        except Exception:
            log.debug("job object not available", exc_info=True)

    def add(self, process: subprocess.Popen) -> None:
        if self.handle is None:
            return
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.AssignProcessToJobObject(ctypes.c_void_p(self.handle), ctypes.c_void_p(int(process._handle)))
        except Exception:
            log.debug("could not tie llama-server to Ressy", exc_info=True)


class LlamaServer:

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.model = ""
        self.port = 0
        self.key = ""
        self._job: _KillOnExit | None = None
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def command(self, model: Path) -> list[str]:
        threads = max(2, min(6, (os.cpu_count() or 4) - 1))
        return [
            str(server_exe()), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
            "-c", "2048", "-b", "256", "-ub", "128", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0",
            "--no-warmup", "-t", str(threads), "-np", "1", "--api-key", self.key,
        ]

    def ensure(self, name: str) -> None:
        with self._lock:
            if self.running() and self.model == name:
                return
            self._stop_locked()
            if not is_downloaded(name):
                raise GroqError(tr("Il modello AI sul PC non è ancora scaricato (Impostazioni › Intelligenza)."),
                                code="model_missing", provider="PC")
            from ..paths import log_dir

            self.port = _free_port()
            self.key = secrets.token_urlsafe(24)
            log_dir().mkdir(parents=True, exist_ok=True)
            out = (log_dir() / "llama-server.log").open("w", encoding="utf-8", errors="replace")
            started = time.monotonic()
            popen_kwargs: dict[str, Any] = {
                "cwd": str(runtime_dir()),
                "stdin": subprocess.DEVNULL,
                "stdout": out,
                "stderr": subprocess.STDOUT,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
                )
            else:
                popen_kwargs["start_new_session"] = True
                env = dict(os.environ)
                rt = str(runtime_dir())
                if sys.platform == "darwin":
                    env["DYLD_LIBRARY_PATH"] = rt + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
                else:
                    env["LD_LIBRARY_PATH"] = rt + os.pathsep + env.get("LD_LIBRARY_PATH", "")
                popen_kwargs["env"] = env
            self.process = subprocess.Popen(
                self.command(model_path(name)),
                **popen_kwargs,
            )
            out.close()
            if self._job is None:
                self._job = _KillOnExit()
            self._job.add(self.process)
            self.model = name
            deadline = time.monotonic() + START_TIMEOUT_S
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    code = self.process.returncode
                    self.process = None
                    raise GroqError(tr("Il motore AI sul PC si è chiuso all'avvio (codice {code}).").format(code=code),
                                    code="local_failed", provider="PC")
                try:
                    if httpx.get(f"{self.base_url}/health", timeout=2).status_code == 200:
                        log.info("llama-server ready with %s in %.1fs", name, time.monotonic() - started)
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.3)
            self._stop_locked()
            raise GroqError(tr("Il motore AI sul PC non è partito in tempo."), code="local_failed", provider="PC")

    def _stop_locked(self) -> None:
        process, self.process = self.process, None
        self.model = ""
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        log.info("llama-server stopped")

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()


class LocalLLMClient:
    NAME = "PC"
    PROVIDER = "local"
    usage: Any = None

    def __init__(self, model_name: Callable[[], str], user_name: Callable[[], str] = lambda: "",
                 server: LlamaServer | None = None) -> None:
        self._model_name = model_name
        self._user_name = user_name
        self.server = server or LlamaServer()
        self._calls = 0
        self._last_use = 0.0
        self._idle: threading.Timer | None = None
        self._busy = threading.Lock()

    def preload(self) -> None:
        self.server.ensure(self._model_name())
        self._touch()

    def _touch(self) -> None:
        self._last_use = time.monotonic()
        if self._idle is not None:
            self._idle.cancel()
        self._idle = threading.Timer(IDLE_STOP_S, self._stop_if_idle)
        self._idle.daemon = True
        self._idle.start()

    def _stop_if_idle(self) -> None:
        if time.monotonic() - self._last_use >= IDLE_STOP_S - 1 and not self._busy.locked():
            log.info("AI on the PC idle: stopping llama-server to free memory")
            self.server.stop()

    def _complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None,
                  tool_choice: str | None, max_tokens: int) -> ChatResult:
        name = self._model_name()
        spoken = result_reply(messages)
        if spoken is not None:
            return ChatResult(message={"role": "assistant", "content": spoken}, model=name, finish_reason="stop")
        allowed_set = set(LOCAL_TOOLS if name == "qwen2.5-0.5b" else LOCAL_TOOLS_FULL)
        last_user_text = next((str(m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"), "")
        if not _wants_screenshot(last_user_text):
            allowed_set.discard("take_screenshot")
        usable = [t for t in (tools or []) if (t.get("function") or {}).get("name") in allowed_set]
        names = [] if tool_choice == "none" else [t["function"]["name"] for t in usable]
        chat = to_local_messages(messages, build_prompt(usable, self._user_name()))
        with self._busy:
            self.server.ensure(name)
            started = time.monotonic()
            response = httpx.post(
                f"{self.server.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.server.key}"},
                json={
                    "messages": chat,
                    "temperature": 0.2,
                    "max_tokens": min(max_tokens, 1400),
                    "response_format": {"type": "json_schema",
                                        "json_schema": {"name": "azione", "schema": answer_schema(names, usable)}},
                    "cache_prompt": True,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=httpx.Timeout(120.0, connect=5.0),
            )
        self._touch()
        if response.status_code >= 400:
            raise GroqError(tr("Il motore AI sul PC ha risposto {status}.").format(status=response.status_code),
                            status=response.status_code,
                            code="local_failed", provider=self.NAME)
        out = response.json()
        self._calls += 1
        raw = str(((out.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        used = out.get("usage") or {}
        log.info("local AI answered in %.1fs (%s tokens)", time.monotonic() - started, used.get("total_tokens"))
        if self.usage is not None:
            try:
                self.usage.record(self.PROVIDER, name, None, used.get("total_tokens"))
            except Exception:
                log.debug("usage bookkeeping failed", exc_info=True)
        message = _repeat_guard(parse_reply(raw, set(names), f"local_{self._calls}"), messages)
        return ChatResult(message=message, model=name, finish_reason="stop")

    async def chat(self, messages: list[dict[str, Any]], *, models: Any = None, tools: list[dict[str, Any]] | None = None,
                   tool_choice: str | None = None, max_tokens: int = 1500, **_: Any) -> ChatResult:
        try:
            return await asyncio.to_thread(self._complete, messages, tools, tool_choice, max_tokens)
        except GroqError:
            raise
        except Exception as exc:
            log.warning("local AI failed", exc_info=True)
            raise GroqError(tr("Il modello AI sul PC non è riuscito a rispondere."), code="local_failed",
                            provider=self.NAME) from exc

    async def web_answer(self, question: str, *, language: str = "it") -> str:
        raise GroqError(tr("Il modello sul PC non può cercare sul web."), code="no_web", status=400,
                        provider=self.NAME)

    async def list_models(self, key: str | None = None) -> list[str]:
        return installed()

    async def aclose(self) -> None:
        if self._idle is not None:
            self._idle.cancel()
        await asyncio.to_thread(self.server.stop)
