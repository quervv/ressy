from __future__ import annotations

import asyncio

import pytest

from ressy.config import Settings
from ressy.remote import client as remote_client
from ressy.remote.local_bot import LocalBot, _import_server


class FakeTelegram:
    platform = "telegram"

    def __init__(self, token, sessions, *args, **kwargs) -> None:
        self.sent = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def notify(self, link, reply) -> None:
        self.sent.append(reply)

    def bot_info(self) -> dict:
        return {"username": "MioRessyBot"}

    def pair_hint(self, code: str) -> dict:
        return {"url": f"https://t.me/MioRessyBot?start={code}", "instruction": f"/collega {code}"}


class BrokenTelegram(FakeTelegram):
    async def start(self) -> None:
        raise RuntimeError("401 Unauthorized")


@pytest.fixture
def bot_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings()
    settings.remote_enabled = True
    settings.remote_mode = "local"
    settings.telegram_token = "123456789:" + "A" * 35
    settings.ensure_identity()
    return settings


def _patch(monkeypatch, frontend) -> None:
    _import_server()
    import ressy_server.frontends.telegram_bot as tg

    monkeypatch.setattr(tg, "TelegramFrontend", frontend)


def test_app_connects_to_its_own_bot(bot_settings, monkeypatch):
    _patch(monkeypatch, FakeTelegram)
    asyncio.run(_connects(bot_settings))


async def _connects(bot_settings):
    bot = LocalBot(bot_settings)
    events: list = []
    client = remote_client.RemoteClient(bot_settings, lambda m: asyncio.sleep(0, {}), lambda k, d: events.append((k, d)))
    client.url_provider = lambda: bot.url
    url = await bot.start()
    assert url.startswith("ws://127.0.0.1:")
    client.start()
    for _ in range(100):
        if client.state == remote_client.ONLINE:
            break
        await asyncio.sleep(0.05)
    assert client.state == remote_client.ONLINE
    assert client.bots["telegram"]["username"] == "MioRessyBot"
    await client.stop()
    await bot.stop()
    assert not bot.running


def test_bad_token_is_reported(bot_settings, monkeypatch):
    _patch(monkeypatch, BrokenTelegram)
    asyncio.run(_bad_token(bot_settings))


async def _bad_token(bot_settings):
    errors: list[str] = []
    bot = LocalBot(bot_settings, on_error=errors.append)
    try:
        await bot.start()
    except Exception:
        pass
    for _ in range(50):
        if errors or bot.error:
            break
        await asyncio.sleep(0.05)
    assert "token" in (bot.error or "".join(errors))
    await bot.stop()
