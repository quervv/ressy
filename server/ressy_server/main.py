from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from aiohttp import web

from . import __version__
from .hub import Hub
from .sessions import SessionService
from .settings import Settings, load_dotenv
from .storage import Store
from .web import create_app

log = logging.getLogger("ressy")


class _RedactTokens(logging.Filter):

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            message = record.getMessage()
            redacted = message
            for secret in self._secrets:
                redacted = redacted.replace(secret, "***")
            if redacted != message:
                record.msg = redacted
                record.args = None
        return True


def setup_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    handler.addFilter(_RedactTokens([settings.telegram_token, settings.discord_token]))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    for noisy in ("httpx", "telegram", "discord", "aiohttp.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def serve(settings: Settings, stop: asyncio.Event, ready: "asyncio.Future[int] | None" = None) -> None:
    store = await Store.open(settings.db_path)
    hub = Hub(store, settings)
    sessions = SessionService(hub, store, settings)

    frontends: list = []
    if settings.telegram_token:
        from .frontends.telegram_bot import TelegramFrontend

        frontends.append(TelegramFrontend(settings.telegram_token, sessions))
    if settings.discord_token:
        from .frontends.discord_bot import DiscordFrontend

        frontends.append(DiscordFrontend(settings.discord_token, sessions, settings))
    for frontend in frontends:
        hub.add_frontend(frontend)

    runner = web.AppRunner(create_app(hub), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, settings.host, settings.port)
    started: list = []
    try:
        await site.start()
        port = settings.port
        server = getattr(site, "_server", None)
        if server is not None and server.sockets:
            port = server.sockets[0].getsockname()[1]
        log.info("Ressy server %s listening on %s:%d", __version__, settings.host, port)
        if ready is not None and not ready.done():
            ready.set_result(port)
        for frontend in frontends:
            await frontend.start()
            started.append(frontend)
        await hub.start()
        await stop.wait()
    finally:
        log.info("shutting down")
        await hub.drain_notices()
        await hub.shutdown()
        for frontend in reversed(started):
            await frontend.stop()
        await runner.cleanup()
        await store.close()


async def amain() -> int:
    load_dotenv(os.environ.get("RESSY_ENV_FILE", ".env"))
    settings = Settings.from_env()
    setup_logging(settings)
    for problem in settings.validate():
        log.error(problem)
    if settings.validate():
        return 2

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await serve(settings, stop)
    except Exception:
        log.exception("fatal error")
        return 1
    return 0


def main() -> None:
    try:
        code = asyncio.run(amain())
    except KeyboardInterrupt:
        code = 0
    raise SystemExit(code)
