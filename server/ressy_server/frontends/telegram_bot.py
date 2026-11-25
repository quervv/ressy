from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict, deque
from typing import Awaitable

from telegram import BotCommand, InputFile, LinkPreviewOptions, Update
from telegram.constants import ChatAction
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from .. import texts
from ..protocol import MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS
from ..sessions import SessionService
from ..storage import LinkRecord
from .base import Identity, OutgoingReply, split_text

log = logging.getLogger("ressy.telegram")

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
TEXT_LIMIT = 4000
PRIVATE = filters.ChatType.PRIVATE
TRACKED_PER_CHAT = 300


class TelegramFrontend:
    platform = "telegram"

    def __init__(self, token: str, sessions: SessionService) -> None:
        self.sessions = sessions
        self.username: str | None = None
        self.app = Application.builder().token(token).concurrent_updates(True).build()
        self._messages: defaultdict[int, deque[int]] = defaultdict(lambda: deque(maxlen=TRACKED_PER_CHAT))

        self.app.add_handler(TypeHandler(Update, self._gate), group=-1)
        add = self.app.add_handler
        add(CommandHandler("start", self._on_start, filters=PRIVATE))
        add(CommandHandler(["collega", "link"], self._on_link, filters=PRIVATE))
        add(CommandHandler(["stato", "status"], self._on_status, filters=PRIVATE))
        add(CommandHandler(["scollega", "unlink"], self._on_unlink, filters=PRIVATE))
        add(CommandHandler(["notifiche", "notify"], self._on_notify, filters=PRIVATE))
        add(CommandHandler(["voce", "voice"], self._on_voice_pref, filters=PRIVATE))
        add(CommandHandler(["aiuto", "help"], self._on_help, filters=PRIVATE))
        add(MessageHandler(PRIVATE & (filters.VOICE | filters.AUDIO), self._on_audio))
        add(MessageHandler(PRIVATE & filters.TEXT & ~filters.COMMAND, self._on_text))
        add(MessageHandler(PRIVATE & ~filters.COMMAND & ~filters.TEXT & ~filters.VOICE & ~filters.AUDIO, self._on_other))
        self.app.add_error_handler(self._on_error)

    async def start(self) -> None:
        await self.app.initialize()
        me = await self.app.bot.get_me()
        self.username = me.username
        try:
            await self.app.bot.set_my_commands(
                [
                    BotCommand("collega", "Collega questo account al tuo PC"),
                    BotCommand("stato", "Stato del PC collegato"),
                    BotCommand("voce", "Risposte vocali: sempre, auto o mai"),
                    BotCommand("notifiche", "Avvisi quando il PC va offline/online"),
                    BotCommand("scollega", "Scollega questo account"),
                    BotCommand("aiuto", "Come funziona Ressy"),
                ]
            )
        except TelegramError:
            log.warning("could not set the bot command menu", exc_info=True)
        await self.app.start()
        assert self.app.updater is not None
        await self.app.updater.start_polling(allowed_updates=["message"])
        log.info("Telegram bot @%s ready", self.username)

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self.app.updater is not None and self.app.updater.running:
                await self.app.updater.stop()
        with contextlib.suppress(Exception):
            if self.app.running:
                await self.app.stop()
        with contextlib.suppress(Exception):
            await self.app.shutdown()

    def bot_info(self) -> dict:
        return {"username": self.username, "url": f"https://t.me/{self.username}" if self.username else None}

    def pair_hint(self, code: str) -> dict:
        url = f"https://t.me/{self.username}?start={code}" if self.username else None
        return {"url": url, "instruction": f"Apri il link oppure invia /collega {code} al bot."}

    @staticmethod
    def _identity(update: Update) -> Identity:
        user = update.effective_user
        chat = update.effective_chat
        assert user is not None and chat is not None
        display = f"@{user.username}" if user.username else (user.full_name or str(user.id))
        return Identity(platform="telegram", user_id=str(user.id), chat_id=str(chat.id), display=display)

    def _track(self, chat_id: int, message_id: int | None) -> None:
        if message_id is not None:
            self._messages[chat_id].append(message_id)

    async def _gate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, chat, message = update.effective_user, update.effective_chat, update.effective_message
        if user is None or chat is None or chat.type != "private":
            return
        if message is not None:
            self._track(chat.id, message.message_id)
        if await self.sessions.gate(self._identity(update)):
            return
        await self.delete_chat(chat.id)
        raise ApplicationHandlerStop

    async def delete_chat(self, chat_id: int) -> None:
        ids = sorted(set(self._messages.pop(chat_id, ())))
        for start in range(0, len(ids), 100):
            try:
                await self.app.bot.delete_messages(chat_id=chat_id, message_ids=ids[start : start + 100])
            except TelegramError:
                log.info("could not delete some messages in chat %s", chat_id, exc_info=True)

    async def _reply_text(self, update: Update, text: str) -> None:
        message = update.effective_message
        if message is None:
            return
        for chunk in split_text(text, TEXT_LIMIT):
            sent = await message.reply_text(chunk, link_preview_options=NO_PREVIEW)
            self._track(message.chat_id, sent.message_id)

    async def _keep_action(self, chat_id: int, action: str, stop: asyncio.Event) -> None:
        while not stop.is_set():
            with contextlib.suppress(Exception):
                await self.app.bot.send_chat_action(chat_id=chat_id, action=action)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=4.5)

    async def _with_action(self, chat_id: int, action: str, work: Awaitable[OutgoingReply]) -> OutgoingReply:
        stop = asyncio.Event()
        indicator = asyncio.create_task(self._keep_action(chat_id, action, stop))
        try:
            return await work
        finally:
            stop.set()
            await indicator

    async def send_reply(self, chat_id: int, reply: OutgoingReply) -> None:
        bot = self.app.bot
        for chunk in split_text(reply.compose_text(), TEXT_LIMIT):
            sent = await bot.send_message(chat_id=chat_id, text=chunk, link_preview_options=NO_PREVIEW)
            self._track(chat_id, sent.message_id)
        if reply.voice is not None:
            voice = reply.voice
            try:
                if voice.mime in ("audio/mpeg", "audio/ogg", "audio/mp4"):
                    await bot.send_voice(chat_id=chat_id, voice=InputFile(voice.data, filename=voice.filename))
                else:
                    await bot.send_document(chat_id=chat_id, document=InputFile(voice.data, filename=voice.filename))
            except TelegramError:
                log.warning("send_voice failed, falling back to a document", exc_info=True)
                with contextlib.suppress(TelegramError):
                    await bot.send_document(chat_id=chat_id, document=InputFile(voice.data, filename=voice.filename))
        for image in reply.images:
            try:
                await bot.send_photo(chat_id=chat_id, photo=InputFile(image.data, filename=image.filename))
            except TelegramError:
                log.warning("send_photo failed, sending the image as a document", exc_info=True)
                with contextlib.suppress(TelegramError):
                    await bot.send_document(chat_id=chat_id, document=InputFile(image.data, filename=image.filename))

    async def notify(self, link: LinkRecord, reply: OutgoingReply) -> None:
        try:
            await self.send_reply(int(link.chat_id), reply)
        except Forbidden:
            log.info("user %s blocked the bot; skipping notification", link.user_id)

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        ident = self._identity(update)
        if context.args:
            await self._reply_text(update, await self.sessions.link(ident, context.args[0]))
        else:
            await self._reply_text(update, self.sessions.welcome_text(self.platform))

    async def _on_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        code = " ".join(context.args) if context.args else None
        await self._reply_text(update, await self.sessions.link(self._identity(update), code))

    async def _on_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply_text(update, await self.sessions.status(self._identity(update)))

    async def _on_unlink(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply_text(update, await self.sessions.unlink(self._identity(update)))

    async def _on_notify(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = context.args[0] if context.args else None
        await self._reply_text(update, await self.sessions.set_presence_alerts(self._identity(update), arg))

    async def _on_voice_pref(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = context.args[0] if context.args else None
        await self._reply_text(update, await self.sessions.set_voice_mode(self._identity(update), arg))

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply_text(update, self.sessions.help_text(self.platform))

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or not message.text:
            return
        ident = self._identity(update)
        reply = await self._with_action(
            message.chat_id,
            ChatAction.TYPING,
            self.sessions.handle_message(ident, text=message.text, sent_at=message.date.timestamp()),
        )
        await self.send_reply(message.chat_id, reply)

    async def _on_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        media = message.voice or message.audio
        if media is None:
            return
        if (media.file_size or 0) > MAX_AUDIO_BYTES or (media.duration or 0) > MAX_AUDIO_SECONDS:
            await self._reply_text(update, texts.AUDIO_TOO_LARGE)
            return
        ident = self._identity(update)

        async def work() -> OutgoingReply:
            tg_file = await context.bot.get_file(media.file_id)
            data = bytes(await tg_file.download_as_bytearray())
            return await self.sessions.handle_message(
                ident,
                text=message.caption,
                audio=data,
                audio_mime=media.mime_type or "audio/ogg",
                sent_at=message.date.timestamp(),
            )

        reply = await self._with_action(message.chat_id, ChatAction.RECORD_VOICE, work())
        await self.send_reply(message.chat_id, reply)

    async def _on_other(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._reply_text(update, texts.UNSUPPORTED)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Telegram handler error", exc_info=context.error)
        if isinstance(update, Update) and update.effective_chat is not None:
            with contextlib.suppress(Exception):
                await context.bot.send_message(chat_id=update.effective_chat.id, text=texts.INTERNAL_ERROR)
