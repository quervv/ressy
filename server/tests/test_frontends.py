from __future__ import annotations

from ressy_server.frontends.base import Attachment, OutgoingReply
from ressy_server.hub import Hub
from ressy_server.sessions import SessionService
from ressy_server.settings import Settings
from ressy_server.storage import Store


async def _sessions() -> tuple[SessionService, Store]:
    settings = Settings(telegram_token="123456:TEST", discord_token="x", db_path=":memory:")
    store = await Store.open(":memory:")
    hub = Hub(store, settings)
    return SessionService(hub, store, settings), store


async def test_telegram_frontend_builds():
    from ressy_server.frontends.telegram_bot import TelegramFrontend

    sessions, store = await _sessions()
    try:
        frontend = TelegramFrontend("123456:TEST-TOKEN", sessions)
        assert frontend.platform == "telegram"
        assert len(frontend.app.handlers[0]) == 10
        frontend.username = "RessyBot"
        assert frontend.pair_hint("K7P2QX")["url"] == "https://t.me/RessyBot?start=K7P2QX"
    finally:
        await store.close()


async def test_discord_frontend_builds():
    from ressy_server.frontends.discord_bot import DiscordFrontend

    sessions, store = await _sessions()
    try:
        frontend = DiscordFrontend("token", sessions, sessions.settings)
        assert frontend.platform == "discord"
        assert "!collega K7P2QX" in frontend.pair_hint("K7P2QX")["instruction"]
    finally:
        await store.close()


def test_compose_text():
    reply = OutgoingReply(text="Fatto", transcript="apri spotify", voice=Attachment(b"x", "r.mp3", "audio/mpeg"))
    assert reply.compose_text() == "🎙️ «apri spotify»\n\nFatto"
