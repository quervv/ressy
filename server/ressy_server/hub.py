from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import __version__, texts
from .frontends.base import Attachment, Frontend, OutgoingReply
from .protocol import (
    AGENT_ID_RE,
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    MAX_REPLY_TEXT,
    MAX_VOICE_BYTES,
    PROTOCOL_VERSION,
    SECRET_RE,
    b64decode,
    clean_name,
)
from .ratelimit import SlidingWindow
from .settings import Settings
from .storage import AgentRecord, LinkRecord, Store

log = logging.getLogger("ressy.hub")


class AgentOffline(Exception):
    pass


class AgentDisconnected(Exception):
    pass


class CommandTimeout(Exception):
    pass


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(eq=False)
class AgentConnection:
    agent_id: str
    name: str
    version: str
    ws: Any
    remote: str = ""
    connected_at: float = field(default_factory=time.time)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self.send_lock:
            await self.ws.send_str(data)

    async def close(self, code: int, message: str) -> None:
        try:
            await self.ws.close(code=code, message=message.encode("utf-8"))
        except Exception:
            pass


class Hub:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self._agents: dict[str, AgentConnection] = {}
        self._pending: dict[str, tuple[str, asyncio.Future[dict]]] = {}
        self._offline_tasks: dict[str, asyncio.Task[None]] = {}
        self._frontends: dict[str, Frontend] = {}
        self._announced: set[str] = set()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._registrations = SlidingWindow(settings.max_registrations_per_hour, 3600)
        self._closing = False

    def add_frontend(self, frontend: Frontend) -> None:
        self._frontends[frontend.platform] = frontend

    def frontend(self, platform: str) -> Frontend | None:
        return self._frontends.get(platform)

    def bots_info(self) -> dict[str, dict]:
        info: dict[str, dict] = {}
        for platform, fe in self._frontends.items():
            try:
                info[platform] = fe.bot_info()
            except Exception:
                log.exception("bot_info failed for %s", platform)
        return info

    def _spawn(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def start(self) -> None:
        self._spawn(self._startup_sweep())
        self._spawn(self._housekeeping())

    async def drain_notices(self, timeout: float = 4.0) -> None:
        due = [t for t in self._offline_tasks.values() if not t.done()]
        if due:
            await asyncio.wait(due, timeout=timeout)

    async def shutdown(self) -> None:
        self._closing = True
        for task in list(self._offline_tasks.values()):
            task.cancel()
        for task in list(self._tasks):
            task.cancel()
        for _, fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(AgentDisconnected())
        conns = list(self._agents.values())
        self._agents.clear()
        await asyncio.gather(*(c.close(1001, "server restart") for c in conns), return_exceptions=True)

    @property
    def online_count(self) -> int:
        return len(self._agents)

    def is_online(self, agent_id: str) -> bool:
        return agent_id in self._agents

    async def authenticate(self, hello: dict, remote_ip: str) -> tuple[AgentRecord | None, str | None]:
        if hello.get("protocol") != PROTOCOL_VERSION:
            return None, "unsupported_protocol"
        agent_id = hello.get("agent_id")
        secret = hello.get("secret")
        if not isinstance(agent_id, str) or not AGENT_ID_RE.match(agent_id):
            return None, "bad_hello"
        if not isinstance(secret, str) or not SECRET_RE.match(secret):
            return None, "bad_hello"
        name = clean_name(hello.get("name"))
        version = clean_name(hello.get("version"), fallback="?")[:32]
        record = await self.store.get_agent(agent_id)
        if record is None:
            if not self._registrations.hit(remote_ip or "?"):
                return None, "rate_limited"
            record = await self.store.create_agent(agent_id, hash_secret(secret), name, version)
            log.info("registered new agent %s (%s) from %s", agent_id[:8], name, remote_ip)
            return record, None
        if not hmac.compare_digest(record.secret_hash, hash_secret(secret)):
            log.warning("auth failed for agent %s from %s", agent_id[:8], remote_ip)
            return None, "auth_failed"
        return record, None

    async def agent_connected(self, conn: AgentConnection) -> None:
        previous = self._agents.get(conn.agent_id)
        self._agents[conn.agent_id] = conn
        if previous is not None and previous is not conn:
            log.info("agent %s reconnected, closing the older socket", conn.agent_id[:8])
            self._spawn(previous.close(4001, "replaced by a newer connection"))
        pending_offline = self._offline_tasks.pop(conn.agent_id, None)
        if pending_offline is not None:
            pending_offline.cancel()

        record = await self.store.get_agent(conn.agent_id)
        await self.store.touch_agent(conn.agent_id, name=conn.name, version=conn.version)
        links = await self.store.links_for_agent(conn.agent_id)
        await conn.send(
            {
                "type": "welcome",
                "server_version": __version__,
                "links": [link.public() for link in links],
                "bots": self.bots_info(),
                "pair_code_ttl": self.settings.pair_code_ttl_s,
            }
        )
        log.info("agent %s online (%s, v%s)", conn.agent_id[:8], conn.name, conn.version)
        first = conn.agent_id not in self._announced
        self._announced.add(conn.agent_id)
        if record is not None and record.offline_notified:
            await self.store.set_offline_notified(conn.agent_id, False)
            await self._broadcast_presence(links, texts.online_notice(conn.name))
        elif first and self.settings.announce_first_connect and record is not None:
            await self._broadcast_presence(links, texts.online_notice(conn.name))

    async def agent_disconnected(self, conn: AgentConnection, *, graceful: bool) -> None:
        if self._agents.get(conn.agent_id) is not conn:
            return
        del self._agents[conn.agent_id]
        try:
            await self.store.touch_agent(conn.agent_id)
        except Exception:
            log.exception("could not update last_seen for %s", conn.agent_id[:8])
        for request_id, (agent_id, fut) in list(self._pending.items()):
            if agent_id == conn.agent_id and not fut.done():
                fut.set_exception(AgentDisconnected())
        log.info("agent %s offline (%s)", conn.agent_id[:8], "quit" if graceful else "dropped")
        if self._closing:
            return
        delay = 0.0 if graceful else self.settings.offline_grace_s
        self._schedule_offline_notice(conn.agent_id, delay, graceful)

    def _schedule_offline_notice(self, agent_id: str, delay: float, graceful: bool) -> None:
        old = self._offline_tasks.pop(agent_id, None)
        if old is not None:
            old.cancel()
        task = asyncio.create_task(self._offline_after(agent_id, delay, graceful))
        self._offline_tasks[agent_id] = task

        def _cleanup(t: asyncio.Task[None]) -> None:
            if self._offline_tasks.get(agent_id) is t:
                del self._offline_tasks[agent_id]

        task.add_done_callback(_cleanup)

    async def _offline_after(self, agent_id: str, delay: float, graceful: bool) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            if agent_id in self._agents:
                return
            record = await self.store.get_agent(agent_id)
            if record is None or record.offline_notified:
                return
            links = await self.store.links_for_agent(agent_id)
            if not links:
                return
            await self.store.set_offline_notified(agent_id, True)
            notice = texts.quit_notice(record.name) if graceful else texts.offline_notice(record.name)
            await self._broadcast_presence(links, notice)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("offline notice failed for %s", agent_id[:8])

    async def _broadcast_presence(self, links: list[LinkRecord], text: str) -> None:
        for link in links:
            if link.presence_alerts:
                await self._deliver(link, OutgoingReply(text=text))

    async def deliver(self, link: LinkRecord, reply: OutgoingReply) -> None:
        await self._deliver(link, reply)

    async def _deliver(self, link: LinkRecord, reply: OutgoingReply) -> None:
        frontend = self._frontends.get(link.platform)
        if frontend is None:
            return
        try:
            await frontend.notify(link, reply)
        except Exception:
            log.exception("could not notify %s:%s", link.platform, link.user_id)

    async def _startup_sweep(self) -> None:
        try:
            await asyncio.sleep(self.settings.startup_sweep_delay_s)
            for record in await self.store.agents_with_links_not_notified():
                if record.agent_id in self._agents or record.agent_id in self._offline_tasks:
                    continue
                self._schedule_offline_notice(record.agent_id, 0.0, graceful=False)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("startup sweep failed")

    async def _housekeeping(self) -> None:
        try:
            while True:
                await asyncio.sleep(600)
                removed = await self.store.purge_expired_codes()
                if removed:
                    log.debug("purged %d expired pairing codes", removed)
        except asyncio.CancelledError:
            pass

    async def send_command(self, agent_id: str, payload: dict, timeout: float) -> dict:
        conn = self._agents.get(agent_id)
        if conn is None:
            raise AgentOffline()
        request_id = uuid.uuid4().hex
        fut: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (agent_id, fut)
        try:
            try:
                await conn.send({**payload, "type": "command", "id": request_id})
            except Exception as exc:
                raise AgentDisconnected() from exc
            try:
                return await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError as exc:
                raise CommandTimeout() from exc
        finally:
            self._pending.pop(request_id, None)

    def reply_from_agent(self, message: dict) -> OutgoingReply:
        text = message.get("text") if isinstance(message.get("text"), str) else ""
        text = text.strip()[:MAX_REPLY_TEXT]
        transcript = message.get("transcript")
        transcript = transcript.strip()[:MAX_REPLY_TEXT] if isinstance(transcript, str) and transcript.strip() else None
        reply = OutgoingReply(text=text, transcript=transcript)

        voice = message.get("voice")
        if isinstance(voice, dict):
            try:
                data = b64decode(voice.get("data"), MAX_VOICE_BYTES)
                mime = str(voice.get("mime") or "audio/mpeg")[:64]
                ext = {"audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav"}.get(mime, "bin")
                reply.voice = Attachment(data=data, filename=f"ressy.{ext}", mime=mime)
            except ValueError:
                log.warning("dropping malformed voice payload")

        images = message.get("images")
        if isinstance(images, list):
            for item in images[:MAX_IMAGES]:
                if not isinstance(item, dict):
                    continue
                try:
                    data = b64decode(item.get("data"), MAX_IMAGE_BYTES)
                except ValueError:
                    log.warning("dropping malformed image payload")
                    continue
                mime = str(item.get("mime") or "image/jpeg")[:64]
                name = clean_name(item.get("name"), fallback="immagine.jpg")
                reply.images.append(Attachment(data=data, filename=name, mime=mime))
        return reply

    async def handle_agent_message(self, conn: AgentConnection, message: dict) -> None:
        kind = message.get("type")
        if kind == "reply":
            request_id = message.get("id")
            entry = self._pending.get(request_id) if isinstance(request_id, str) else None
            if entry is not None and entry[0] == conn.agent_id and not entry[1].done():
                entry[1].set_result(message)
            return
        if kind == "pair_request":
            await self._send_pair_code(conn)
            return
        if kind == "notify":
            await self._agent_notify(conn, message)
            return
        if kind == "unlink":
            await self._agent_unlink(conn, message)
            return
        if kind == "rename":
            name = clean_name(message.get("name"), fallback=conn.name)
            conn.name = name
            await self.store.touch_agent(conn.agent_id, name=name)
            return
        if kind == "ping":
            await conn.send({"type": "pong"})
            return
        log.debug("ignoring unknown message type %r from %s", kind, conn.agent_id[:8])

    async def _send_pair_code(self, conn: AgentConnection) -> None:
        code, expires_at = await self.store.create_pair_code(conn.agent_id, self.settings.pair_code_ttl_s)
        hints: dict[str, dict] = {}
        for platform, fe in self._frontends.items():
            try:
                hints[platform] = fe.pair_hint(code)
            except Exception:
                log.exception("pair_hint failed for %s", platform)
        await conn.send(
            {
                "type": "pair_code",
                "code": code,
                "expires_in": int(expires_at - time.time()),
                "platforms": hints,
            }
        )

    async def _agent_notify(self, conn: AgentConnection, message: dict) -> None:
        reply = self.reply_from_agent(message)
        if not reply.text and reply.voice is None and not reply.images:
            return
        links = await self.store.links_for_agent(conn.agent_id)
        target = message.get("target")
        if isinstance(target, dict):
            links = [
                link
                for link in links
                if link.platform == target.get("platform") and link.user_id == str(target.get("user_id"))
            ]
        for link in links:
            await self._deliver(link, reply)

    async def _agent_unlink(self, conn: AgentConnection, message: dict) -> None:
        platform = message.get("platform")
        user_id = message.get("user_id")
        if not isinstance(platform, str) or not isinstance(user_id, str):
            return
        link = await self.store.get_link(platform, user_id)
        if link is None or link.agent_id != conn.agent_id:
            await self.push_links(conn.agent_id)
            return
        await self.store.delete_link(platform, user_id)
        await self._deliver(link, OutgoingReply(text=texts.unlinked_by_pc(conn.name)))
        await self.push_links(conn.agent_id)

    async def push_links(self, agent_id: str, linked: LinkRecord | None = None) -> None:
        conn = self._agents.get(agent_id)
        if conn is None:
            return
        try:
            if linked is not None:
                await conn.send({"type": "linked", "link": linked.public()})
            links = await self.store.links_for_agent(agent_id)
            await conn.send({"type": "links", "links": [link.public() for link in links]})
        except Exception:
            log.warning("could not push links to %s", agent_id[:8])
