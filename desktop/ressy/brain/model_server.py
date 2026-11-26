from __future__ import annotations

import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx

from ..config import DEFAULT_MODEL_SERVER_PORT, LOCAL_LLM_MODELS, normalize_custom_url
from ..paths import user_folder
from . import local_llm

log = logging.getLogger("ressy.model_server")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class ModelServerConfig:
    model_path: str
    host: str = "127.0.0.1"
    port: int = DEFAULT_MODEL_SERVER_PORT
    api_key: str = ""
    ctx_size: int = 8192
    gpu_layers: int = 99


def generate_api_key() -> str:
    return f"ressy-{secrets.token_urlsafe(24)}"


def lan_addresses() -> list[str]:
    ips: list[str] = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = str(info[4][0])
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 80))
            ip = str(s.getsockname()[0])
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.insert(0, ip)
    except OSError:
        pass
    return ips


def server_urls(port: int, *, expose_lan: bool = False) -> list[str]:
    urls = [f"http://127.0.0.1:{int(port)}/v1"]
    if expose_lan:
        for ip in lan_addresses():
            urls.append(f"http://{ip}:{int(port)}/v1")
    return urls


def scan_gguf_models(extra_dirs: Iterable[Path] = ()) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def _add(label: str, path: Path) -> None:
        key = os.path.normcase(str(path.resolve()))
        if key in seen or not path.is_file():
            return
        seen.add(key)
        out.append((label, path.resolve()))

    for key, (label, _mb, _fname, _url) in LOCAL_LLM_MODELS.items():
        if local_llm.model_ready(key):
            _add(f"Ressy · {label} ({key})", local_llm.model_path(key))

    mdir = local_llm.models_dir()
    if mdir.is_dir():
        for p in sorted(mdir.glob("*.gguf")):
            _add(p.stem, p)

    search_roots = list(extra_dirs) + [
        user_folder("downloads"),
        user_folder("documents"),
        user_folder("desktop"),
        Path.home() / "models",
    ]
    for root in search_roots:
        if not root.is_dir():
            continue
        try:
            for p in sorted(root.glob("*.gguf")):
                _add(f"{p.stem} ({root.name})", p)
        except OSError:
            continue
    return out


def build_launch_command(exe: Path, cfg: ModelServerConfig) -> list[str]:
    model = Path(cfg.model_path).expanduser().resolve()
    host = (cfg.host or "127.0.0.1").strip()
    port = max(1024, min(65535, int(cfg.port)))
    ctx = max(2048, int(cfg.ctx_size))
    threads = max(2, min(16, (os.cpu_count() or 4) - 1 or 2))
    cmd = [
        str(exe),
        "--model", str(model),
        "--host", host,
        "--port", str(port),
        "--ctx-size", str(ctx),
        "--threads", str(threads),
        "--n-gpu-layers", str(int(cfg.gpu_layers)),
        "--jinja",
        "--alias", model.stem,
    ]
    if (cfg.api_key or "").strip():
        cmd += ["--api-key", cfg.api_key.strip()]
    return cmd


def check_health(base_url: str, api_key: str = "", timeout: float = 3.0) -> tuple[bool, list[str]]:
    url = normalize_custom_url(base_url)
    if not url:
        return False, []
    headers = {"Authorization": f"Bearer {api_key.strip()}"} if api_key.strip() else {}
    try:
        r = httpx.get(f"{url}/models", headers=headers, timeout=timeout)
        if r.status_code >= 400:
            return False, []
        data = r.json().get("data") or []
        models = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
        return True, models
    except Exception:
        return False, []


class ModelServerRunner:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self.config: ModelServerConfig | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def start(self, cfg: ModelServerConfig, *, wait_s: float = 45.0) -> list[str]:
        model = Path(cfg.model_path).expanduser()
        if not model.is_file():
            raise FileNotFoundError(f"Modello .gguf non trovato: {model}")
        if not local_llm.runtime_ready():
            raise RuntimeError("Motore llama.cpp non ancora scaricato: scarica prima un modello o installa llama-server.")
        exe = local_llm.server_exe()
        self.stop()

        cmd = build_launch_command(exe, cfg)
        log.info("starting custom model server on %s:%s (%s)", cfg.host, cfg.port, model.name)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        with self._lock:
            self.process = proc
            self.config = cfg

        local_url = f"http://127.0.0.1:{int(cfg.port)}/v1"
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                self.stop()
                raise RuntimeError("Il server del modello si è chiuso inaspettatamente (controlla modello/RAM o porta).")
            ok, models = check_health(local_url, cfg.api_key, timeout=2.0)
            if ok:
                return models or [model.stem]
            time.sleep(0.35)
        self.stop()
        raise TimeoutError("Il server del modello non ha risposto in tempo.")

    def stop(self) -> None:
        with self._lock:
            proc, self.process = self.process, None
            self.config = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


_SHARED: ModelServerRunner | None = None


def shared_runner() -> ModelServerRunner:
    global _SHARED
    if _SHARED is None:
        _SHARED = ModelServerRunner()
    return _SHARED


def cli_instructions(port: int = DEFAULT_MODEL_SERVER_PORT) -> str:
    return (
        f"Esempi per collegare o ospitare un server AI esterno:\n"
        f"• Ollama: OLLAMA_HOST=0.0.0.0:11434 ollama serve → URL http://IP-PC:11434/v1\n"
        f"• LM Studio: Local Server → Start → URL http://127.0.0.1:1234/v1\n"
        f"• Ressy CLI (su un altro PC/VPS): Ressy --model-server --model-file modello.gguf --model-port {int(port)}"
    )


def run_cli_model_server(model_file: str, *, host: str = "0.0.0.0", port: int = DEFAULT_MODEL_SERVER_PORT,
                         api_key: str = "") -> int:
    if not model_file.strip():
        found = scan_gguf_models()
        if not found:
            print("Nessun modello .gguf trovato. Passa --model-file <percorso.gguf>.", file=sys.stderr)
            return 1
        model_file = str(found[0][1])
    cfg = ModelServerConfig(model_path=model_file, host=host, port=port, api_key=api_key)
    runner = ModelServerRunner()
    models = runner.start(cfg, wait_s=90.0)
    urls = server_urls(port, expose_lan=(host in ("0.0.0.0", "::")))
    print(f"Ressy Model Server attivo! Modelli: {', '.join(models)}")
    for u in urls:
        print(f"  URL: {u}")
    if api_key.strip():
        print("  API Key: (impostata)")
    try:
        while runner.running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()
    return 0
