from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from typing import Any, Awaitable, Callable, TypeVar

log = logging.getLogger("ressy.loop")

T = TypeVar("T")


class AsyncRunner:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="ressy-loop", daemon=True)
        self._ready = threading.Event()

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(5)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.set_exception_handler(self._on_exception)
        self.loop.call_soon(self._ready.set)
        try:
            self.loop.run_forever()
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.run_until_complete(self.loop.shutdown_default_executor())
            except Exception:
                log.debug("loop cleanup", exc_info=True)
            self.loop.close()

    @staticmethod
    def _on_exception(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, asyncio.CancelledError)):
            return
        log.error("event loop: %s", context.get("message"), exc_info=exc)

    def submit(self, coro: Awaitable[T]) -> concurrent.futures.Future[T]:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, fn: Callable[..., Any], *args: Any) -> None:
        if self.loop.is_closed():
            return
        try:
            self.loop.call_soon_threadsafe(fn, *args)
        except RuntimeError:
            pass

    def stop(self, timeout: float = 5.0) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout)
