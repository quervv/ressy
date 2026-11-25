from __future__ import annotations

import asyncio
import json
import secrets
import sys
import uuid
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ressy_server.frontends.base import OutgoingReply
from ressy_server.hub import Hub
from ressy_server.sessions import SessionService
from ressy_server.settings import Settings
from ressy_server.storage import LinkRecord, Store
from ressy_server.web import create_app


class FakeFrontend:

    def __init__(self, platform: str = "telegram") -> None:
        self.platform = platform
        self.sent: list[tuple[str, OutgoingReply]] = []
        self.event = asyncio.Event()

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def notify(self, link: LinkRecord, reply: OutgoingReply) -> None:
        self.sent.append((link.user_id, reply))
        self.event.set()

    def bot_info(self) -> dict:
        return {"username": "RessyTestBot"}

    def pair_hint(self, code: str) -> dict:
        return {"url": f"https://t.me/RessyTestBot?start={code}", "instruction": f"/collega {code}"}

    async def wait_for(self, predicate, timeout: float = 3.0) -> OutgoingReply:
        async def _poll() -> OutgoingReply:
            while True:
                for _, reply in self.sent:
                    if predicate(reply):
                        return reply
                self.event.clear()
                await self.event.wait()

        return await asyncio.wait_for(_poll(), timeout)


class FakeAgent:

    def __init__(self, client: TestClient, agent_id: str | None = None, secret: str | None = None) -> None:
        self.client = client
        self.agent_id = agent_id or uuid.uuid4().hex
        self.secret = secret or secrets.token_urlsafe(32)
        self.ws = None
        self.inbox: asyncio.Queue[dict] = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self.auto_reply: str | None = "Fatto!"

    async def connect(self, name: str = "PC-Test") -> dict:
        self.ws = await self.client.ws_connect("/ws/agent")
        await self.ws.send_str(
            json.dumps(
                {
                    "type": "hello",
                    "protocol": 1,
                    "agent_id": self.agent_id,
                    "secret": self.secret,
                    "name": name,
                    "version": "1.0.0",
                }
            )
        )
        first = json.loads((await self.ws.receive(timeout=3)).data)
        if first.get("type") == "welcome":
            self._reader = asyncio.create_task(self._read())
        return first

    async def _read(self) -> None:
        async for msg in self.ws:
            data = json.loads(msg.data)
            if data.get("type") == "command" and self.auto_reply is not None:
                await self.send(
                    {
                        "type": "reply",
                        "id": data["id"],
                        "ok": True,
                        "text": f"{self.auto_reply} ({data.get('text') or 'audio'})",
                        "voice": {"mime": "audio/mpeg", "data": "SUQz"},
                    }
                )
            await self.inbox.put(data)

    async def send(self, payload: dict) -> None:
        await self.ws.send_str(json.dumps(payload))

    async def expect(self, kind: str, timeout: float = 3.0) -> dict:
        while True:
            data = await asyncio.wait_for(self.inbox.get(), timeout)
            if data.get("type") == kind:
                return data

    async def close(self, graceful: bool = False) -> None:
        if graceful:
            await self.send({"type": "bye", "reason": "quit"})
        await self.ws.close()
        if self._reader is not None:
            self._reader.cancel()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        telegram_token="x",
        db_path=":memory:",
        offline_grace_s=0.3,
        startup_sweep_delay_s=3600,
        command_timeout_s=1.5,
        stale_message_s=120,
    )


@pytest.fixture
async def env(settings: Settings):
    store = await Store.open(":memory:")
    hub = Hub(store, settings)
    frontend = FakeFrontend()
    hub.add_frontend(frontend)
    sessions = SessionService(hub, store, settings)
    client = TestClient(TestServer(create_app(hub)))
    await client.start_server()
    try:
        yield {"store": store, "hub": hub, "frontend": frontend, "sessions": sessions, "client": client}
    finally:
        await hub.shutdown()
        await client.close()
        await store.close()
