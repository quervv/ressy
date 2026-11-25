from __future__ import annotations

import asyncio
import time

from conftest import FakeAgent

from ressy_server import texts
from ressy_server.frontends.base import Identity

MARIO = Identity(platform="telegram", user_id="1001", chat_id="1001", display="@mario")


async def _pair(env, agent: FakeAgent, identity: Identity = MARIO) -> str:
    await agent.send({"type": "pair_request"})
    code_msg = await agent.expect("pair_code")
    assert len(code_msg["code"]) == 6
    assert code_msg["platforms"]["telegram"]["url"].endswith(code_msg["code"])
    answer = await env["sessions"].link(identity, code_msg["code"].lower())
    assert "Collegato" in answer and "PC-Test" in answer
    linked = await agent.expect("linked")
    assert linked["link"]["display"] == identity.display
    return code_msg["code"]


async def test_welcome_and_pairing(env):
    agent = FakeAgent(env["client"])
    welcome = await agent.connect()
    assert welcome["type"] == "welcome"
    assert welcome["links"] == []
    assert welcome["bots"]["telegram"]["username"] == "RessyTestBot"

    code = await _pair(env, agent)
    links = await agent.expect("links")
    assert [link["user_id"] for link in links["links"]] == ["1001"]

    again = await env["sessions"].link(MARIO, code)
    assert again == texts.LINK_BAD
    await agent.close()


async def test_command_roundtrip_and_voice(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)

    reply = await env["sessions"].handle_message(MARIO, text="apri spotify", sent_at=time.time())
    assert reply.text == "Fatto! (apri spotify)"
    assert reply.voice is not None and reply.voice.data == b"ID3"

    command = await agent.expect("command")
    assert command["source"] == {"platform": "telegram", "user_id": "1001", "display": "@mario"}
    assert command["want_voice"] is False

    reply = await env["sessions"].handle_message(MARIO, audio=b"OggS-fake", audio_mime="audio/ogg")
    command = await agent.expect("command")
    assert command["want_voice"] is True
    assert command["audio"]["mime"] == "audio/ogg"
    await agent.close()


async def test_offline_notice_and_refusal(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)

    await agent.close()
    notice = await env["frontend"].wait_for(lambda r: "disconnessa" in r.text)
    assert "PC-Test" in notice.text

    refused = await env["sessions"].handle_message(MARIO, text="apri discord")
    assert "NON verrà eseguito" in refused.text

    again = FakeAgent(env["client"], agent.agent_id, agent.secret)
    await again.connect()
    back = await env["frontend"].wait_for(lambda r: "di nuovo online" in r.text)
    assert "PC-Test" in back.text
    await again.close()


async def test_quick_reconnect_is_silent(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    await agent.close()
    again = FakeAgent(env["client"], agent.agent_id, agent.secret)
    await again.connect()
    await asyncio.sleep(0.6)
    assert not [r for _, r in env["frontend"].sent if "disconnessa" in r.text]
    await again.close()


async def test_graceful_quit_notifies_immediately(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    await agent.close(graceful=True)
    notice = await env["frontend"].wait_for(lambda r: "stata chiusa" in r.text, timeout=1.0)
    assert "PC-Test" in notice.text


async def test_wrong_secret_is_rejected(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await agent.close()
    impostor = FakeAgent(env["client"], agent.agent_id, "x" * 43)
    first = await impostor.connect()
    assert first["type"] == "error" and first["code"] == "auth_failed"


async def test_unlinked_user_and_bad_codes(env):
    stranger = Identity(platform="telegram", user_id="2002", chat_id="2002", display="@x")
    reply = await env["sessions"].handle_message(stranger, text="apri spotify")
    assert "non è ancora collegato" in reply.text
    for _ in range(5):
        assert await env["sessions"].link(stranger, "AAAAAA") == texts.LINK_BAD
    assert await env["sessions"].link(stranger, "AAAAAA") == texts.LINK_RATE


async def test_stale_messages_are_not_executed(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    reply = await env["sessions"].handle_message(MARIO, text="spegni il pc", sent_at=time.time() - 3600)
    assert reply.text == texts.STALE
    await asyncio.sleep(0.2)
    received = []
    while not agent.inbox.empty():
        received.append(agent.inbox.get_nowait()["type"])
    assert "command" not in received
    await agent.close()


async def test_timeout_when_agent_is_silent(env):
    agent = FakeAgent(env["client"])
    agent.auto_reply = None
    await agent.connect()
    await _pair(env, agent)
    reply = await env["sessions"].handle_message(MARIO, text="apri spotify")
    assert reply.text == texts.TIMEOUT
    await agent.close()


async def test_agent_side_unlink_and_notify(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    await agent.expect("links")

    await agent.send({"type": "notify", "text": "⏰ Promemoria: pizza", "target": {"platform": "telegram", "user_id": "1001"}})
    reminder = await env["frontend"].wait_for(lambda r: "Promemoria" in r.text)
    assert reminder.text == "⏰ Promemoria: pizza"

    await agent.send({"type": "unlink", "platform": "telegram", "user_id": "1001"})
    links = await agent.expect("links")
    assert links["links"] == []
    await env["frontend"].wait_for(lambda r: "ha scollegato" in r.text)
    reply = await env["sessions"].handle_message(MARIO, text="apri spotify")
    assert "non è ancora collegato" in reply.text
    await agent.close()


async def test_preferences(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    assert "sempre" in await env["sessions"].set_voice_mode(MARIO, "sempre")
    await env["sessions"].handle_message(MARIO, text="ciao")
    command = await agent.expect("command")
    assert command["want_voice"] is True
    assert "disattivati" in await env["sessions"].set_presence_alerts(MARIO, "off")
    status = await env["sessions"].status(MARIO)
    assert "online" in status and "disattivati" in status
    await agent.close()
    await asyncio.sleep(0.6)
    assert not [r for _, r in env["frontend"].sent if "disconnessa" in r.text]


async def test_bot_on_the_pc_announces_it_is_back(env):
    import dataclasses

    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    await agent.close()
    hub = env["hub"]
    hub.settings = dataclasses.replace(hub.settings, announce_first_connect=True, offline_grace_s=3600)
    hub._announced.clear()
    again = FakeAgent(env["client"], agent.agent_id, agent.secret)
    await again.connect()
    notice = await env["frontend"].wait_for(lambda r: "online" in r.text.lower(), timeout=1.0)
    assert "PC-Test" in notice.text
    await again.close()


async def test_quit_notice_is_sent_before_shutdown(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    await _pair(env, agent)
    env["frontend"].sent.clear()
    await agent.close(graceful=True)
    await env["hub"].drain_notices(2.0)
    assert any("stata chiusa" in r.text for _, r in env["frontend"].sent)


async def test_the_bot_belongs_to_the_first_account(env):
    agent = FakeAgent(env["client"])
    await agent.connect()
    sessions, frontend = env["sessions"], env["frontend"]

    luigi = Identity(platform="telegram", user_id="2002", chat_id="2002", display="@luigi")
    assert await sessions.gate(luigi) is True

    await _pair(env, agent)
    assert await sessions.gate(MARIO) is True
    assert await sessions.gate(luigi) is False
    alert = await frontend.wait_for(lambda r: "@luigi" in r.text)
    assert "bloccato" in alert.text and "2002" in alert.text
    sent = len(frontend.sent)
    assert await sessions.gate(luigi) is False
    await asyncio.sleep(0.05)
    assert len(frontend.sent) == sent

    await agent.send({"type": "pair_request"})
    await agent.expect("pair_code")
    assert await env["store"].is_blocked("telegram", "2002")

    discord_user = Identity(platform="discord", user_id="3003", chat_id="3003", display="Peach")
    assert await sessions.gate(discord_user) is True
    await agent.close()
