from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

from ressy_server.frontends.base import Identity

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))

from ressy.config import Settings as AgentSettings
from ressy.remote.client import AUTH_FAILED, ONLINE, REPLACED, RemoteClient

MARIO = Identity(platform="telegram", user_id="1001", chat_id="1001", display="@mario")


def agent_settings(env, tmp_path: Path, name: str = "PC-Desktop") -> AgentSettings:
    settings = AgentSettings()
    settings._path = tmp_path / f"{name}.json"
    settings.ensure_identity()
    settings.device_name = name
    settings.server_url = str(env["client"].make_url("/ws/agent")).replace("http://", "ws://", 1)
    settings.remote_enabled = True
    settings.remote_mode = "server"
    return settings


async def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


@pytest.fixture
def events():
    return []


def make_client(settings, events, handler=None) -> RemoteClient:
    async def default_handler(message: dict) -> dict:
        return {"ok": True, "text": f"Eseguito: {message.get('text')}", "voice": {"mime": "audio/mpeg", "data": "SUQz"}}

    return RemoteClient(settings, handler or default_handler, lambda kind, data: events.append((kind, data)))


async def test_desktop_client_pairs_runs_commands_notifies_and_unlinks(env, tmp_path, events):
    received: list[dict] = []

    async def handler(message: dict) -> dict:
        received.append(message)
        return {"ok": True, "text": f"Eseguito: {message.get('text')}", "voice": {"mime": "audio/mpeg", "data": "SUQz"}}

    client = make_client(agent_settings(env, tmp_path), events, handler)
    client.start()
    try:
        await wait_until(lambda: client.state == ONLINE)
        assert ("state", {"state": ONLINE, "detail": ""}) in events

        pair = await client.request_pair_code()
        assert pair["platforms"]["telegram"]["url"].endswith(pair["code"])
        answer = await env["sessions"].link(MARIO, pair["code"])
        assert "PC-Desktop" in answer
        await wait_until(lambda: any(kind == "linked" for kind, _ in events))
        await wait_until(lambda: [link["user_id"] for link in client.links] == ["1001"])

        reply = await env["sessions"].handle_message(MARIO, text="apri spotify", sent_at=time.time())
        assert reply.text == "Eseguito: apri spotify"
        assert reply.voice is not None and reply.voice.data == b"ID3"
        assert received[0]["source"] == {"platform": "telegram", "user_id": "1001", "display": "@mario"}

        assert await client.notify("⏰ Promemoria: test", target={"platform": "telegram", "user_id": "1001"})
        await env["frontend"].wait_for(lambda r: r.text == "⏰ Promemoria: test")

        await client.unlink("telegram", "1001")
        await env["frontend"].wait_for(lambda r: "ha scollegato" in r.text)
        await wait_until(lambda: client.links == [])
    finally:
        await client.stop()


async def test_closing_the_app_warns_on_telegram(env, tmp_path, events):
    client = make_client(agent_settings(env, tmp_path), events)
    client.start()
    await wait_until(lambda: client.state == ONLINE)
    pair = await client.request_pair_code()
    await env["sessions"].link(MARIO, pair["code"])
    await wait_until(lambda: client.links != [])

    await client.stop("quit")
    notice = await env["frontend"].wait_for(lambda r: "è stata chiusa" in r.text)
    assert "PC-Desktop" in notice.text

    reply = await env["sessions"].handle_message(MARIO, text="apri spotify", sent_at=time.time())
    assert "NON" in reply.text


async def test_wrong_secret_is_refused(env, tmp_path, events):
    good = agent_settings(env, tmp_path, "PC-A")
    first = make_client(good, events)
    first.start()
    await wait_until(lambda: first.state == ONLINE)
    await first.stop()

    thief = agent_settings(env, tmp_path, "PC-B")
    thief.agent_id = good.agent_id
    other_events: list = []
    second = make_client(thief, other_events)
    second.start()
    try:
        await wait_until(lambda: second.state == AUTH_FAILED)
    finally:
        await second.stop()


async def test_same_identity_on_two_pcs_is_reported(env, tmp_path, events):
    settings = agent_settings(env, tmp_path)
    first = make_client(settings, events)
    first.start()
    await wait_until(lambda: first.state == ONLINE)

    clone_events: list = []
    clone = make_client(settings, clone_events)
    clone.start()
    try:
        await wait_until(lambda: clone.state == ONLINE)
        await wait_until(lambda: first.state == REPLACED)
        await asyncio.sleep(0.3)
        assert clone.state == ONLINE
    finally:
        await clone.stop()
        await first.stop()
