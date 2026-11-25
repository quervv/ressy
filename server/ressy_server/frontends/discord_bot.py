from __future__ import annotations

import asyncio
import contextlib
import io
import logging

import discord

from .. import texts
from ..protocol import MAX_AUDIO_BYTES
from ..sessions import SessionService
from ..settings import Settings
from ..storage import LinkRecord
from .base import Identity, OutgoingReply, split_text

log = logging.getLogger("ressy.discord")

TEXT_LIMIT = 1900
PREFIXES = ("!", "/")
AUDIO_EXT = (".ogg", ".oga", ".opus", ".mp3", ".m4a", ".wav", ".webm", ".flac")


class _Client(discord.Client):
    def __init__(self, frontend: "DiscordFrontend", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.frontend = frontend

    async def on_ready(self) -> None:
        self.frontend.ready.set()
        log.info("Discord bot %s ready", self.user)

    async def on_message(self, message: discord.Message) -> None:
        try:
            await self.frontend.handle(message)
        except Exception:
            log.exception("Discord handler error")
            with contextlib.suppress(Exception):
                await message.channel.send(texts.INTERNAL_ERROR)


class DiscordFrontend:
    platform = "discord"

    def __init__(self, token: str, sessions: SessionService, settings: Settings) -> None:
        self.token = token
        self.sessions = sessions
        self.settings = settings
        self.ready = asyncio.Event()
        intents = discord.Intents.default()
        self.client = _Client(self, intents=intents)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self.client.start(self.token))
        ready_wait = asyncio.create_task(self.ready.wait())
        done, _ = await asyncio.wait({self._task, ready_wait}, timeout=60, return_when=asyncio.FIRST_COMPLETED)
        if self._task in done:
            ready_wait.cancel()
            exc = self._task.exception()
            raise RuntimeError(f"Discord bot failed to start: {exc!r}")
        if ready_wait not in done:
            ready_wait.cancel()
            log.warning("Discord is not ready after 60s; it will keep trying in the background")

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            await self.client.close()
        if self._task is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._task, timeout=10)

    def bot_info(self) -> dict:
        user = self.client.user
        return {
            "username": user.name if user else None,
            "id": str(user.id) if user else None,
            "invite_url": self.settings.discord_invite_url or None,
        }

    def pair_hint(self, code: str) -> dict:
        user = self.client.user
        name = user.name if user else "Ressy"
        return {
            "url": self.settings.discord_invite_url or None,
            "instruction": f"Scrivi in privato al bot {name}: !collega {code}",
        }

    async def _send(self, channel: discord.abc.Messageable, reply: OutgoingReply) -> None:
        files: list[discord.File] = []
        if reply.voice is not None:
            files.append(discord.File(io.BytesIO(reply.voice.data), filename=reply.voice.filename))
        for image in reply.images:
            files.append(discord.File(io.BytesIO(image.data), filename=image.filename))
        chunks = split_text(reply.compose_text(), TEXT_LIMIT)
        if not chunks:
            if files:
                await channel.send(files=files)
            return
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            if last and files:
                await channel.send(chunk, files=files)
            else:
                await channel.send(chunk)

    async def notify(self, link: LinkRecord, reply: OutgoingReply) -> None:
        user_id = int(link.user_id)
        user = self.client.get_user(user_id) or await self.client.fetch_user(user_id)
        channel = user.dm_channel or await user.create_dm()
        try:
            await self._send(channel, reply)
        except discord.Forbidden:
            log.info("cannot DM discord user %s; skipping notification", link.user_id)

    async def delete_chat(self, channel: discord.DMChannel) -> None:
        me = self.client.user
        try:
            async for old in channel.history(limit=200):
                if me is not None and old.author.id == me.id:
                    with contextlib.suppress(discord.HTTPException):
                        await old.delete()
        except discord.HTTPException:
            log.info("could not clean the DM with an intruder", exc_info=True)

    async def handle(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        author = message.author
        ident = Identity(
            platform="discord",
            user_id=str(author.id),
            chat_id=str(message.channel.id),
            display=getattr(author, "global_name", None) or author.name,
        )
        if not await self.sessions.gate(ident):
            await self.delete_chat(message.channel)
            return
        content = (message.content or "").strip()

        if content[:1] in PREFIXES:
            name, _, rest = content[1:].partition(" ")
            name = name.lower()
            arg = rest.strip() or None
            answer: str | None = None
            if name in ("collega", "link"):
                answer = await self.sessions.link(ident, arg)
            elif name in ("stato", "status"):
                answer = await self.sessions.status(ident)
            elif name in ("scollega", "unlink"):
                answer = await self.sessions.unlink(ident)
            elif name in ("notifiche", "notify"):
                answer = await self.sessions.set_presence_alerts(ident, arg)
            elif name in ("voce", "voice"):
                answer = await self.sessions.set_voice_mode(ident, arg)
            elif name in ("aiuto", "help"):
                answer = self.sessions.help_text(self.platform)
            elif name == "start":
                answer = self.sessions.welcome_text(self.platform)
            if answer is not None:
                for chunk in split_text(answer, TEXT_LIMIT):
                    await message.channel.send(chunk)
                return

        audio = next(
            (
                a
                for a in message.attachments
                if (a.content_type or "").startswith("audio/") or a.filename.lower().endswith(AUDIO_EXT)
            ),
            None,
        )
        if audio is not None and audio.size > MAX_AUDIO_BYTES:
            await message.channel.send(texts.AUDIO_TOO_LARGE)
            return
        if audio is None and not content:
            await message.channel.send(texts.UNSUPPORTED)
            return

        async with message.channel.typing():
            if audio is not None:
                data = await audio.read()
                mime = (audio.content_type or "audio/ogg").split(";")[0]
                reply = await self.sessions.handle_message(
                    ident, text=content or None, audio=data, audio_mime=mime, sent_at=message.created_at.timestamp()
                )
            else:
                reply = await self.sessions.handle_message(ident, text=content, sent_at=message.created_at.timestamp())
        await self._send(message.channel, reply)
