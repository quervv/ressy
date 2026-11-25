from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from . import texts
from .frontends.base import Identity, OutgoingReply
from .hub import AgentDisconnected, AgentOffline, CommandTimeout, Hub
from .protocol import MAX_AUDIO_BYTES, MAX_COMMAND_TEXT, b64encode, normalize_pair_code
from .ratelimit import SlidingWindow
from .settings import Settings
from .storage import VOICE_ALWAYS, VOICE_AUTO, VOICE_NEVER, LinkRecord, Store
from .timefmt import format_last_seen, get_zone

log = logging.getLogger("ressy.sessions")

_ON = {"on", "si", "sì", "yes", "1", "attiva", "attivi", "true"}
_OFF = {"off", "no", "0", "disattiva", "disattivi", "false"}
_VOICE = {
    "sempre": VOICE_ALWAYS,
    "always": VOICE_ALWAYS,
    "on": VOICE_ALWAYS,
    "auto": VOICE_AUTO,
    "automatico": VOICE_AUTO,
    "mai": VOICE_NEVER,
    "never": VOICE_NEVER,
    "off": VOICE_NEVER,
}


class SessionService:
    def __init__(self, hub: Hub, store: Store, settings: Settings) -> None:
        self.hub = hub
        self.store = store
        self.settings = settings
        self._tz = get_zone(settings.timezone)
        self._locks: defaultdict[tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._commands = SlidingWindow(settings.max_commands_per_minute, 60)
        self._link_failures = SlidingWindow(settings.max_link_failures, 600)

    def _last_seen(self, ts: float | None) -> str:
        return format_last_seen(ts, time.time(), self._tz)

    def welcome_text(self, platform: str) -> str:
        return texts.welcome(platform, self.settings.public_url)

    def help_text(self, platform: str) -> str:
        return texts.help_text(platform)

    async def _refresh_contact(self, identity: Identity, link: LinkRecord) -> None:
        if link.chat_id != identity.chat_id or link.display != identity.display:
            await self.store.update_link_contact(identity.platform, identity.user_id, identity.chat_id, identity.display)

    async def gate(self, identity: Identity) -> bool:
        if await self.store.is_blocked(identity.platform, identity.user_id):
            return False
        owner = await self.store.owner(identity.platform)
        if owner is None or owner.user_id == identity.user_id:
            return True
        if await self.store.block(identity.platform, identity.user_id, identity.display):
            log.warning("blocked %s:%s, the bot belongs to someone else", identity.platform, identity.user_id)
            await self.hub.deliver(
                owner, OutgoingReply(text=texts.intruder_alert(identity.platform, identity.display, identity.user_id))
            )
        return False

    async def link(self, identity: Identity, raw_code: str | None) -> str:
        if not raw_code or not raw_code.strip():
            return texts.LINK_USAGE.format(command=texts.cmd(identity.platform, "collega"))
        if not self._link_failures.allowed(identity.key):
            return texts.LINK_RATE
        code = normalize_pair_code(raw_code)
        agent_id = await self.store.consume_pair_code(code) if code else None
        if agent_id is None:
            self._link_failures.hit(identity.key)
            return texts.LINK_BAD
        agent = await self.store.get_agent(agent_id)
        if agent is None:
            return texts.LINK_BAD
        self._link_failures.reset(identity.key)

        previous = await self.store.get_link(identity.platform, identity.user_id)
        link = LinkRecord(
            platform=identity.platform,
            user_id=identity.user_id,
            chat_id=identity.chat_id,
            display=identity.display,
            agent_id=agent_id,
            presence_alerts=previous.presence_alerts if previous else True,
            voice_mode=previous.voice_mode if previous else VOICE_AUTO,
            linked_at=time.time(),
        )
        await self.store.upsert_link(link)
        if not self.hub.is_online(agent_id):
            await self.store.set_offline_notified(agent_id, True)
        else:
            await self.store.set_offline_notified(agent_id, False)
        if previous is not None and previous.agent_id != agent_id:
            await self.hub.push_links(previous.agent_id)
        await self.hub.push_links(agent_id, linked=link)
        log.info("linked %s:%s to agent %s", identity.platform, identity.user_id, agent_id[:8])
        return texts.link_ok(agent.name, self.hub.is_online(agent_id))

    async def unlink(self, identity: Identity) -> str:
        link = await self.store.delete_link(identity.platform, identity.user_id)
        if link is None:
            return texts.NOT_LINKED_SHORT
        agent = await self.store.get_agent(link.agent_id)
        await self.hub.push_links(link.agent_id)
        return texts.unlinked(agent.name if agent else "PC")

    async def status(self, identity: Identity) -> str:
        link = await self.store.get_link(identity.platform, identity.user_id)
        if link is None:
            return texts.NOT_LINKED.format(command=texts.cmd(identity.platform, "collega"))
        await self._refresh_contact(identity, link)
        agent = await self.store.get_agent(link.agent_id)
        if agent is None:
            return texts.NOT_LINKED_SHORT
        return texts.status(
            agent.name,
            self.hub.is_online(agent.agent_id),
            self._last_seen(agent.last_seen),
            link.presence_alerts,
            link.voice_mode,
        )

    async def set_presence_alerts(self, identity: Identity, arg: str | None) -> str:
        link = await self.store.get_link(identity.platform, identity.user_id)
        if link is None:
            return texts.NOT_LINKED.format(command=texts.cmd(identity.platform, "collega"))
        value = (arg or "").strip().lower()
        if value in _ON:
            await self.store.set_link_prefs(identity.platform, identity.user_id, presence_alerts=True)
            return texts.presence_set(True)
        if value in _OFF:
            await self.store.set_link_prefs(identity.platform, identity.user_id, presence_alerts=False)
            return texts.presence_set(False)
        return texts.presence_usage(identity.platform, link.presence_alerts)

    async def set_voice_mode(self, identity: Identity, arg: str | None) -> str:
        link = await self.store.get_link(identity.platform, identity.user_id)
        if link is None:
            return texts.NOT_LINKED.format(command=texts.cmd(identity.platform, "collega"))
        value = (arg or "").strip().lower()
        if value in _VOICE:
            mode = _VOICE[value]
            await self.store.set_link_prefs(identity.platform, identity.user_id, voice_mode=mode)
            return texts.voice_set(mode)
        return texts.voice_usage(identity.platform, link.voice_mode)

    async def handle_message(
        self,
        identity: Identity,
        *,
        text: str | None = None,
        audio: bytes | None = None,
        audio_mime: str | None = None,
        sent_at: float | None = None,
    ) -> OutgoingReply:
        if sent_at is not None and time.time() - sent_at > self.settings.stale_message_s:
            return OutgoingReply(text=texts.STALE)

        link = await self.store.get_link(identity.platform, identity.user_id)
        if link is None:
            if text and normalize_pair_code(text) and len(text.strip()) <= 12:
                return OutgoingReply(text=await self.link(identity, text))
            return OutgoingReply(text=texts.NOT_LINKED.format(command=texts.cmd(identity.platform, "collega")))
        await self._refresh_contact(identity, link)

        text = (text or "").strip()[:MAX_COMMAND_TEXT]
        if not text and not audio:
            return OutgoingReply(text=texts.UNSUPPORTED)
        if audio is not None and len(audio) > MAX_AUDIO_BYTES:
            return OutgoingReply(text=texts.AUDIO_TOO_LARGE)
        if not self._commands.hit(identity.key):
            return OutgoingReply(text=texts.RATE_LIMIT)

        async with self._locks[identity.key]:
            agent = await self.store.get_agent(link.agent_id)
            if agent is None:
                return OutgoingReply(text=texts.NOT_LINKED_SHORT)
            if not self.hub.is_online(agent.agent_id):
                return OutgoingReply(text=texts.offline(agent.name, self._last_seen(agent.last_seen)))

            want_voice = link.voice_mode == VOICE_ALWAYS or (link.voice_mode == VOICE_AUTO and audio is not None)
            payload: dict = {
                "source": {
                    "platform": identity.platform,
                    "user_id": identity.user_id,
                    "display": identity.display,
                },
                "want_voice": want_voice,
            }
            if text:
                payload["text"] = text
            if audio is not None:
                payload["audio"] = {"mime": (audio_mime or "audio/ogg").split(";")[0], "data": b64encode(audio)}

            try:
                answer = await self.hub.send_command(agent.agent_id, payload, self.settings.command_timeout_s)
            except AgentOffline:
                return OutgoingReply(text=texts.offline(agent.name, self._last_seen(agent.last_seen)))
            except AgentDisconnected:
                return OutgoingReply(text=texts.DISCONNECTED_DURING)
            except CommandTimeout:
                return OutgoingReply(text=texts.TIMEOUT)

        reply = self.hub.reply_from_agent(answer)
        if not reply.text and reply.voice is None and not reply.images:
            reply.text = texts.EMPTY_REPLY if answer.get("ok", True) else texts.AGENT_ERROR
        return reply
