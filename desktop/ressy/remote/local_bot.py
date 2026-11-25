from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..paths import app_dir

log = logging.getLogger("ressy.bot")


def _import_server() -> Any:
    try:
        import ressy_server.main as server_main
    except ImportError:
        source = Path(__file__).resolve().parents[3] / "server"
        if source.is_dir() and str(source) not in sys.path:
            sys.path.insert(0, str(source))
        import ressy_server.main as server_main
    return server_main


class BotError(RuntimeError):
    pass


class LocalBot:
    def __init__(self, settings: Settings, on_error: Callable[[str], None] | None = None) -> None:
        self.settings = settings
        self._on_error = on_error
        self.port = 0
        self.error = ""
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws/agent" if self.running and self.port else ""

    def _server_settings(self) -> Any:
        from ressy_server.settings import Settings as ServerSettings

        folder = app_dir() / "bot"
        folder.mkdir(parents=True, exist_ok=True)
        return ServerSettings(
            telegram_token=self.settings.telegram_token,
            discord_token=self.settings.discord_token,
            discord_invite_url=self.settings.discord_invite_url,
            host="127.0.0.1",
            port=0,
            db_path=str(folder / "bot.db"),
            announce_first_connect=True,
            startup_sweep_delay_s=10 ** 7,
        )

    async def start(self) -> str:
        await self.stop()
        if not self.settings.has_bot_token:
            raise BotError("Manca il token del bot.")
        server_main = _import_server()
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[int] = loop.create_future()
        self._stop = asyncio.Event()
        self.error = ""
        self._task = asyncio.create_task(
            server_main.serve(self._server_settings(), self._stop, ready), name="ressy-bot"
        )

        def _done(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                self.error = describe(exc)
                log.error("bot stopped: %s", self.error)
                if not ready.done():
                    ready.set_exception(BotError(self.error))
                elif self._on_error is not None:
                    self._on_error(self.error)

        self._task.add_done_callback(_done)
        try:
            self.port = await asyncio.wait_for(asyncio.shield(ready), timeout=30)
        except asyncio.TimeoutError as exc:
            await self.stop()
            raise BotError("Il bot non è partito in tempo.") from exc
        await asyncio.sleep(0)
        log.info("bot running on 127.0.0.1:%d", self.port)
        return self.url

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        if self._stop is not None:
            self._stop.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=10)
        except (asyncio.TimeoutError, Exception):
            task.cancel()
        self.port = 0


def describe(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc)
    if name in ("InvalidToken", "LoginFailure") or "Unauthorized" in text or "401" in text:
        return "Il token del bot non è valido: copialo di nuovo da BotFather o dal Discord Developer Portal."
    if name in ("NetworkError", "TimedOut", "ClientConnectorError", "ConnectError"):
        return "Non riesco a raggiungere Telegram o Discord: controlla la connessione."
    return f"Il bot si è fermato ({name})."
