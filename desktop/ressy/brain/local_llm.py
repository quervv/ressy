from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import logging
import os
import secrets
import socket
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import httpx

from ..config import LOCAL_LLM_MODELS
from .groq import ChatResult, GroqError

log = logging.getLogger("ressy.llm.local")

LLAMA_TAG = "b12728"
LLAMA_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-win-cpu-x64.zip"
LLAMA_SHA256 = "a8ace09d44bb10e2617268c55c3f2db0e0adeedd9c1ba722969920665a3ae698"
LLAMA_MB = 25
_RUNTIME_FILES = ("llama-server.exe", "llama-server-impl.dll", "llama-common.dll", "llama.dll", "mtmd.dll",
                  "libomp.dll", "ggml.dll", "ggml-base.dll", "ggml-rpc.dll")
_READY_MARK = ".ressy-ok"

IDLE_STOP_S = 10 * 60
START_TIMEOUT_S = 120

LOCAL_TOOLS = (
    "open_app", "close_app", "focus_app", "open_url", "web_search", "play_youtube", "media_control", "set_volume",
    "weather", "take_screenshot", "system_status", "reminder", "create_folder", "open_folder", "list_windows",
    "pc_power", "set_clipboard", "type_text", "press_keys", "go_to_sleep", "api_usage", "web_answer",
)
_MAX_HISTORY = 6

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
    return runtime_dir() / "llama-server.exe"


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
    return base in _RUNTIME_FILES or (base.startswith("ggml-cpu") and base.endswith(".dll")) or base.startswith("LICENSE")


def install_runtime(archive: Path, target: Path | None = None) -> Path:
    digest = hashlib.sha256()
    with archive.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != LLAMA_SHA256:
        raise OSError("il motore AI scaricato non corrisponde a quello ufficiale")
    target = target or runtime_dir()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir() or not _wanted(info.filename):
                continue
            name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
            with zf.open(info) as src, (target / name).open("wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
    if not (target / "llama-server.exe").is_file():
        raise OSError("llama-server.exe non trovato nell'archivio")
    (target / _READY_MARK).write_text(LLAMA_TAG, encoding="utf-8")
    return target


def download(name: str, progress: Progress | None = None, cancel: threading.Event | None = None) -> Path:
    from ..speech.local_stt import download_file

    total = download_size_mb(name) * 1_000_000
    offset = 0

    def step(done: int, _total: int) -> None:
        if progress is not None:
            progress(offset + done, max(total, offset + done))

    if not runtime_ready():
        archive = runtime_dir() / "llama.zip"
        try:
            download_file(LLAMA_URL, archive, LLAMA_MB, step, cancel)
            install_runtime(archive)
        finally:
            archive.unlink(missing_ok=True)
        offset += LLAMA_MB * 1_000_000
    if not model_ready(name):
        _label, mb, _file, url = LOCAL_LLM_MODELS[name]
        download_file(url, model_path(name), mb, step, cancel)
    return model_path(name)


def delete_others(keep: str) -> None:
    for name in LOCAL_LLM_MODELS:
        if name != keep:
            model_path(name).unlink(missing_ok=True)


def _tool_line(schema: dict[str, Any]) -> str:
    fn = schema.get("function") or {}
    props = (fn.get("parameters") or {}).get("properties") or {}
    required = set((fn.get("parameters") or {}).get("required") or [])
    args = []
    for name, spec in props.items():
        hint = "|".join(map(str, spec["enum"])) if "enum" in spec else spec.get("type", "string")
        args.append(f"{name}{'' if name in required else '?'}: {hint}")
    description = str(fn.get("description") or "").split(". ")[0].split(" (")[0][:90]
    return f"- {fn.get('name')}({', '.join(args)}): {description}"


def build_prompt(tools: list[dict[str, Any]], user_name: str = "") -> str:
    who = f" di {user_name}" if user_name else ""
    lines = "\n".join(_tool_line(t) for t in tools)
    return (
        f"Sei Ressy, l'assistente vocale sul PC{who}. Parli italiano, frasi brevi (al massimo due).\n"
        "Per ogni messaggio scegli UNA azione: uno degli strumenti qui sotto, oppure \"rispondi\" per parlare.\n"
        "Dopo che uno strumento ha funzionato, usa \"rispondi\" per dire in breve cosa hai fatto.\n"
        "Non inventare risultati: se serve un'informazione aggiornata usa web_answer o weather.\n"
        "Rispondi solo con JSON: {\"azione\": ..., \"argomenti\": {...}, \"risposta\": \"...\"}.\n\n"
        f"Strumenti:\n{lines}"
    )


def answer_schema(names: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "azione": {"type": "string", "enum": [*names, "rispondi"]},
            "argomenti": {"type": "object"},
            "risposta": {"type": "string"},
        },
        "required": ["azione", "argomenti", "risposta"],
    }


def to_local_messages(messages: list[dict[str, Any]], system: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
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
            out.append({"role": "user", "content": f"Risultato di {message.get('name')}: {message.get('content')}"})
        else:
            out.append({"role": "user", "content": str(message.get("content") or "")})
    last_user = max((i for i, m in enumerate(out) if m["role"] == "user" and not m["content"].startswith("Risultato di ")),
                    default=0)
    start = max(0, last_user - _MAX_HISTORY)
    return [{"role": "system", "content": system}, *out[start:]]


def parse_reply(raw: str, allowed: set[str], step_id: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except ValueError:
        return {"role": "assistant", "content": raw.strip()}
    if not isinstance(data, dict):
        return {"role": "assistant", "content": str(data)}
    action = str(data.get("azione") or "rispondi")
    args = data.get("argomenti") if isinstance(data.get("argomenti"), dict) else {}
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


def _repeat_guard(message: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    calls = message.get("tool_calls")
    if not calls or not messages or messages[-1].get("role") != "tool":
        return message
    previous = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})
    prev_call = ((previous.get("tool_calls") or [{}])[0].get("function") or {})
    if prev_call.get("name") != calls[0]["function"]["name"]:
        return message
    try:
        result = json.loads(messages[-1].get("content") or "{}")
    except ValueError:
        result = {}
    return {"role": "assistant", "content": str(result.get("esito") or result.get("errore") or "Fatto.")}


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
        threads = max(2, min(8, (os.cpu_count() or 4) - 1))
        return [
            str(server_exe()), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
            "-c", "4096", "-t", str(threads), "-np", "1", "--api-key", self.key,
        ]

    def ensure(self, name: str) -> None:
        with self._lock:
            if self.running() and self.model == name:
                return
            self._stop_locked()
            if not is_downloaded(name):
                raise GroqError("Il modello AI sul PC non è ancora scaricato (Impostazioni › Intelligenza).",
                                code="model_missing", provider="PC")
            from ..paths import log_dir

            self.port = _free_port()
            self.key = secrets.token_urlsafe(24)
            log_dir().mkdir(parents=True, exist_ok=True)
            out = (log_dir() / "llama-server.log").open("w", encoding="utf-8", errors="replace")
            started = time.monotonic()
            self.process = subprocess.Popen(
                self.command(model_path(name)),
                cwd=str(runtime_dir()),
                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0),
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
                    raise GroqError(f"Il motore AI sul PC si è chiuso all'avvio (codice {code}).",
                                    code="local_failed", provider="PC")
                try:
                    if httpx.get(f"{self.base_url}/health", timeout=2).status_code == 200:
                        log.info("llama-server ready with %s in %.1fs", name, time.monotonic() - started)
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.3)
            self._stop_locked()
            raise GroqError("Il motore AI sul PC non è partito in tempo.", code="local_failed", provider="PC")

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
        usable = [t for t in (tools or []) if (t.get("function") or {}).get("name") in LOCAL_TOOLS]
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
                    "max_tokens": min(max_tokens, 300),
                    "response_format": {"type": "json_schema",
                                        "json_schema": {"name": "azione", "schema": answer_schema(names)}},
                    "cache_prompt": True,
                },
                timeout=httpx.Timeout(120.0, connect=5.0),
            )
        self._touch()
        if response.status_code >= 400:
            raise GroqError(f"Il motore AI sul PC ha risposto {response.status_code}.", status=response.status_code,
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
            raise GroqError("Il modello AI sul PC non è riuscito a rispondere.", code="local_failed",
                            provider=self.NAME) from exc

    async def web_answer(self, question: str, *, language: str = "it") -> str:
        raise GroqError("Il modello sul PC non può cercare sul web.", code="no_web", status=400, provider=self.NAME)

    async def list_models(self, key: str | None = None) -> list[str]:
        return installed()

    async def aclose(self) -> None:
        if self._idle is not None:
            self._idle.cancel()
        await asyncio.to_thread(self.server.stop)
