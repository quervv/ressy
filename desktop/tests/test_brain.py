from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from ressy.brain.agent import MAX_STEPS, Brain
from ressy.brain.groq import ChatResult, GroqAuthError, GroqClient, GroqRateLimited, model_params, strip_citations
from ressy.tools.registry import Channel, Tool, ToolRegistry, params

VOICE = Channel("voice")


class FakeGroq:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def chat(self, messages, *, models, tools=None, tool_choice=None, **kwargs):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        return ChatResult(message=self.script.pop(0), model=models[0])


def tool_call(name, args, call_id="c1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def make_brain(settings, script, tools):
    registry = ToolRegistry()
    registry.extend(tools)
    groq = FakeGroq(script)
    return Brain(settings, groq, registry, services=None), groq


def test_tool_loop_runs_tools_and_answers(settings):
    opened = []

    def open_app(ctx, args):
        opened.append(args["name"])
        return "Ho avviato Spotify."

    settings.quick_commands = False
    brain, groq = make_brain(
        settings,
        [tool_call("open_app", {"name": "spotify"}), {"role": "assistant", "content": "Ecco Spotify!"}],
        [Tool("open_app", "apre", params({"name": {"type": "string"}}, ["name"]), open_app)],
    )
    result = asyncio.run(brain.respond("apri spotify", VOICE))
    assert opened == ["spotify"]
    assert result.text == "Ecco Spotify!"
    second = groq.calls[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["id"] == "c1"
    assert "content" not in second[-2]
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "name": "open_app",
                          "content": json.dumps({"ok": True, "esito": "Ho avviato Spotify."}, ensure_ascii=False)}
    assert brain.memory.history("voice") == [
        {"role": "user", "content": "apri spotify"},
        {"role": "assistant", "content": "Ecco Spotify!"},
    ]


def test_sleep_flag_and_system_prompt(settings):
    def go_to_sleep(ctx, args):
        ctx.sleep_requested = True
        return "ok"

    settings.user_name = "Alex"
    brain, groq = make_brain(
        settings,
        [tool_call("go_to_sleep", {}), {"role": "assistant", "content": "A dopo, Alex!"}],
        [Tool("go_to_sleep", "dormi", params(), go_to_sleep, remote=False)],
    )
    result = asyncio.run(brain.respond("grazie è tutto", VOICE))
    assert result.sleep is True
    system = groq.calls[0]["messages"][0]["content"]
    assert "Alex" in system and "voce" in system


def test_step_limit_forces_a_final_answer(settings):
    brain, groq = make_brain(
        settings,
        [tool_call("noop", {}, f"c{i}") for i in range(MAX_STEPS)] + [{"role": "assistant", "content": "Ho finito."}],
        [Tool("noop", "nulla", params(), lambda c, a: "ok")],
    )
    result = asyncio.run(brain.respond("fai cose", Channel("telegram", "1")))
    assert result.text == "Ho finito."
    assert groq.calls[-1]["tool_choice"] == "none"


def test_model_params_per_family():
    assert model_params("openai/gpt-oss-120b") == {"reasoning_effort": "low", "include_reasoning": False}
    assert model_params("qwen/qwen3.8-27b") == {"reasoning_effort": "none"}
    assert model_params("some/other") == {}


def test_strip_citations():
    assert strip_citations("Oggi piove a Roma【1†L3-L5】.") == "Oggi piove a Roma."


def _client_with(handler) -> GroqClient:
    client = GroqClient(lambda: "gsk_test")
    client._client = httpx.AsyncClient(base_url="https://api.groq.com/openai/v1", transport=httpx.MockTransport(handler))
    return client


def test_chat_falls_back_to_next_model_on_rate_limit():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["model"])
        if body["model"] == "a":
            return httpx.Response(429, json={"error": {"message": "slow down", "code": "rate_limit_exceeded"}},
                                  headers={"retry-after": "30"})
        assert request.headers["Authorization"] == "Bearer gsk_test"
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    client = _client_with(handler)
    result = asyncio.run(client.chat([{"role": "user", "content": "x"}], models=["a", "b"]))
    assert seen == ["a", "b"] and result.model == "b" and result.message["content"] == "ok"


def test_chat_all_rate_limited_and_bad_key():
    def limited(request):
        return httpx.Response(429, json={"error": {"message": "slow"}}, headers={"retry-after": "30"})

    with pytest.raises(GroqRateLimited):
        asyncio.run(_client_with(limited).chat([{"role": "user", "content": "x"}], models=["a", "b"]))

    def unauthorized(request):
        return httpx.Response(401, json={"error": {"message": "Invalid API Key", "code": "invalid_api_key"}})

    with pytest.raises(GroqAuthError):
        asyncio.run(_client_with(unauthorized).chat([{"role": "user", "content": "x"}], models=["a", "b"]))


def test_missing_key_is_an_auth_error():
    client = GroqClient(lambda: "  ")
    with pytest.raises(GroqAuthError):
        asyncio.run(client.chat([{"role": "user", "content": "x"}], models=["a"]))


def test_invisible_characters_are_dropped_from_answers():
    from ressy.brain.agent import clean_answer

    zw = chr(0x200B)
    assert clean_answer(f"Video {zw * 3}  {zw}") == "Video"
    assert clean_answer(f"Ciao{zw} Marco") == "Ciao Marco"
