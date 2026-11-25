from __future__ import annotations

import asyncio
import json
import logging
import platform
import random
from typing import Any, Awaitable, Callable

import aiohttp

from .. import __version__
from ..config import Settings

log = logging.getLogger("ressy.remote")

PROTOCOL_VERSION = 1
MAX_WS_MESSAGE = 32 * 1024 * 1024
HELLO_TIMEOUT_S = 15
CLOSE_REPLACED = 4001

DISABLED = "disabled"
CONNECTING = "connecting"
ONLINE = "online"
OFFLINE = "offline"
AUTH_FAILED = "auth_failed"
OUTDATED = "outdated"
REPLACED = "replaced"
BOT_ERROR = "bot_error"

CommandHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
EventSink = Callable[[str, dict[str, Any]], None]


class RemoteError(RuntimeError):
    pass


class RemoteClient:
    def __init__(self, settings: Settings, on_command: CommandHandler, on_event: EventSink) -> None:
        self.settings = settings
        self._on_command = on_command
        self._emit = on_event
        self.state = DISABLED
        self.detail = ""
        self.links: list[dict[str, Any]] = []
        self.bots: dict[str, Any] = {}
        self.pair_code_ttl = 600
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._stopping = False
        self._pair_waiter: asyncio.Future | None = None
        self._jobs: set[asyncio.Task] = set()
        self.url_provider: Callable[[], str] = lambda: self.settings.server_url.strip()
        self._blocked = ""

    def block(self, detail: str) -> None:
        self._blocked = detail
        self.reconnect()

    def unblock(self) -> None:
        self._blocked = ""

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name="ressy-remote")

    def reconnect(self) -> None:
        self._wake.set()
        ws = self._ws
        if ws is not None and not ws.closed:
            asyncio.ensure_future(ws.close(code=1000, message=b"reconnect"))

    async def stop(self, reason: str = "quit") -> None:
        self._stopping = True
        self._wake.set()
        ws = self._ws
        if ws is not None and not ws.closed:
            try:
                await asyncio.wait_for(self._send({"type": "bye", "reason": reason}), timeout=2)
            except Exception:
                pass
            try:
                await asyncio.wait_for(ws.close(code=1000, message=b"bye"), timeout=3)
            except Exception:
                pass
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        for job in list(self._jobs):
            job.cancel()
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        self._set_state(DISABLED)

    def _set_state(self, state: str, detail: str = "") -> None:
        if state == self.state and detail == self.detail:
            return
        self.state, self.detail = state, detail
        self._emit("state", {"state": state, "detail": detail})

    async def _wait_wake(self, timeout: float | None) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stopping:
            if self._blocked:
                self._set_state(BOT_ERROR, self._blocked)
                await self._wait_wake(None)
                continue
            if not self.settings.remote_ready or not self.url_provider():
                self._set_state(DISABLED)
                await self._wait_wake(None)
                continue
            self._set_state(CONNECTING)
            outcome = await self._connect_once()
            if self._stopping:
                break
            if outcome == "welcomed":
                backoff = 1.0
            if outcome in (AUTH_FAILED, OUTDATED, REPLACED):
                await self._wait_wake(None)
                continue
            if self._wake.is_set():
                self._wake.clear()
                continue
            delay = 60.0 if outcome == "rate_limited" else backoff * random.uniform(0.8, 1.2)
            backoff = min(backoff * 2, 30.0)
            self._set_state(OFFLINE, f"nuovo tentativo tra {int(delay)} s")
            await self._wait_wake(delay)

    async def _connect_once(self) -> str:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15),
                headers={"User-Agent": f"Ressy/{__version__}"},
            )
        welcomed = False
        try:
            async with self._session.ws_connect(
                self.url_provider(),
                heartbeat=25,
                max_msg_size=MAX_WS_MESSAGE,
                timeout=aiohttp.ClientWSTimeout(ws_close=5.0),
            ) as ws:
                self._ws = ws
                await self._send(
                    {
                        "type": "hello",
                        "protocol": PROTOCOL_VERSION,
                        "agent_id": self.settings.agent_id,
                        "secret": self.settings.agent_secret,
                        "name": self.settings.device_name,
                        "version": __version__,
                        "os": f"{platform.system()} {platform.release()}",
                    }
                )
                first = await asyncio.wait_for(ws.receive(), timeout=HELLO_TIMEOUT_S)
                verdict = self._handle_first(first)
                if verdict != "welcomed":
                    return verdict
                welcomed = True
                async for message in ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._dispatch(message.data)
                    elif message.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE,
                                          aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                        break
                if ws.close_code == CLOSE_REPLACED:
                    self._set_state(REPLACED, "Ressy si è collegata al server da un altro PC con la stessa identità.")
                    return REPLACED
                log.info("server connection closed (code %s)", ws.close_code)
                return "welcomed"
        except asyncio.TimeoutError:
            log.warning("server did not answer in time")
            return "welcomed" if welcomed else "error"
        except aiohttp.WSServerHandshakeError as exc:
            log.warning("server refused the WebSocket (%s)", exc.status)
            return "error"
        except (aiohttp.ClientError, OSError) as exc:
            log.info("cannot reach the server: %s", exc)
            return "welcomed" if welcomed else "error"
        finally:
            self._ws = None
            if self._pair_waiter is not None and not self._pair_waiter.done():
                self._pair_waiter.set_exception(RemoteError("Connessione al server persa."))

    def _handle_first(self, message: aiohttp.WSMessage) -> str:
        if message.type != aiohttp.WSMsgType.TEXT:
            return "error"
        try:
            data = json.loads(message.data)
        except ValueError:
            return "error"
        if data.get("type") == "welcome":
            self.links = list(data.get("links") or [])
            self.bots = dict(data.get("bots") or {})
            self.pair_code_ttl = int(data.get("pair_code_ttl") or 600)
            self._set_state(ONLINE)
            self._emit("links", {"links": self.links})
            log.info("connected to the server (%d linked chat(s))", len(self.links))
            return "welcomed"
        if data.get("type") == "error":
            code = str(data.get("code") or "")
            text = str(data.get("message") or "")
            log.warning("server refused this PC: %s %s", code, text)
            if code == "auth_failed":
                self._set_state(AUTH_FAILED, text or "Identità del PC non valida.")
                return AUTH_FAILED
            if code == "unsupported_protocol":
                self._set_state(OUTDATED, text or "Aggiorna Ressy.")
                return OUTDATED
            if code == "rate_limited":
                return "rate_limited"
        return "error"

    async def _dispatch(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except ValueError:
            return
        kind = data.get("type")
        if kind == "command":
            job = asyncio.create_task(self._run_command(data))
            self._jobs.add(job)
            job.add_done_callback(self._jobs.discard)
        elif kind == "pair_code":
            if self._pair_waiter is not None and not self._pair_waiter.done():
                self._pair_waiter.set_result(data)
            self._emit("pair_code", data)
        elif kind == "linked":
            self._emit("linked", data.get("link") or {})
        elif kind == "links":
            self.links = list(data.get("links") or [])
            self._emit("links", {"links": self.links})
        elif kind == "error":
            log.warning("server error: %s", data.get("message"))

    async def _run_command(self, data: dict[str, Any]) -> None:
        request_id = data.get("id")
        try:
            reply = await self._on_command(data)
        except Exception:
            log.exception("command handler crashed")
            reply = {"ok": False, "text": "Errore interno di Ressy sul PC."}
        try:
            await self._send({"type": "reply", "id": request_id, **reply})
        except Exception:
            log.warning("could not deliver a reply (connection lost?)")

    async def _send(self, payload: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            raise RemoteError("Non connessa al server.")
        async with self._send_lock:
            await ws.send_str(json.dumps(payload, ensure_ascii=False))

    @property
    def online(self) -> bool:
        return self.state == ONLINE

    async def request_pair_code(self) -> dict[str, Any]:
        if not self.online:
            raise RemoteError("Ressy non è connessa al server: controlla la connessione.")
        loop = asyncio.get_running_loop()
        self._pair_waiter = loop.create_future()
        await self._send({"type": "pair_request"})
        return await asyncio.wait_for(self._pair_waiter, timeout=10)

    async def unlink(self, platform_name: str, user_id: str) -> None:
        await self._send({"type": "unlink", "platform": platform_name, "user_id": user_id})

    async def rename(self, name: str) -> None:
        if self.online:
            await self._send({"type": "rename", "name": name})

    async def notify(
        self,
        text: str,
        *,
        voice: dict[str, str] | None = None,
        images: list[dict[str, str]] | None = None,
        target: dict[str, str] | None = None,
    ) -> bool:
        if not self.online:
            return False
        payload: dict[str, Any] = {"type": "notify", "text": text}
        if voice:
            payload["voice"] = voice
        if images:
            payload["images"] = images
        if target:
            payload["target"] = target
        try:
            await self._send(payload)
            return True
        except Exception:
            return False
