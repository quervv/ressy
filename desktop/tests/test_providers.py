from __future__ import annotations

import asyncio
import json
import struct

import httpx
import numpy as np
import pytest

from ressy.brain.groq import GroqAuthError, GroqRateLimited
from ressy.brain.providers import ClaudeClient, GeminiClient, LLMRouter, _to_anthropic, _tools_to_anthropic
from ressy.speech import local_stt


def test_openai_history_becomes_anthropic_messages():
    raw = [{"type": "thinking", "thinking": "", "signature": "sig"},
           {"type": "tool_use", "id": "t1", "name": "open_app", "input": {"name": "spotify"}}]
    system, msgs = _to_anthropic([
        {"role": "system", "content": "Sei Ressy."},
        {"role": "user", "content": "apri spotify e discord"},
        {"role": "assistant", "content": "", "tool_calls": [], "_claude": raw},
        {"role": "tool", "tool_call_id": "t1", "name": "open_app", "content": json.dumps({"ok": True})},
        {"role": "tool", "tool_call_id": "t2", "name": "open_app", "content": json.dumps({"ok": False})},
        {"role": "assistant", "content": "Fatto",
         "tool_calls": [{"id": "x", "function": {"name": "f", "arguments": "{\"a\": 1}"}}]},
    ])
    assert system == "Sei Ressy."
    assert msgs[1] == {"role": "assistant", "content": raw}
    assert msgs[2]["role"] == "user" and [b["tool_use_id"] for b in msgs[2]["content"]] == ["t1", "t2"]
    assert "is_error" not in msgs[2]["content"][0] and msgs[2]["content"][1]["is_error"] is True
    assert msgs[3]["content"][1] == {"type": "tool_use", "id": "x", "name": "f", "input": {"a": 1}}


def test_tool_schema_conversion():
    tools = _tools_to_anthropic([{"type": "function", "function": {
        "name": "weather", "description": "meteo", "parameters": {"type": "object", "properties": {}}}}])
    assert tools == [{"name": "weather", "description": "meteo", "input_schema": {"type": "object", "properties": {}}}]


def _claude_with(handler) -> ClaudeClient:
    import anthropic
    import httpx2

    def handler2(request):
        response = handler(httpx.Request(request.method, str(request.url), headers=dict(request.headers),
                                         content=request.read()))
        return httpx2.Response(response.status_code, content=response.content, headers=dict(response.headers))

    client = ClaudeClient(lambda: "sk-ant-test")
    client._client = anthropic.AsyncAnthropic(
        api_key="sk-ant-test", max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler2)),
    )
    client._client_key = "sk-ant-test"
    return client


def _message(content, stop="tool_use", model="claude-opus-5-5"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": content,
            "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_claude_chat_tool_call_and_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        return httpx.Response(200, json=_message([
            {"type": "thinking", "thinking": "", "signature": "abc"},
            {"type": "text", "text": "Apro Spotify."},
            {"type": "tool_use", "id": "toolu_1", "name": "open_app", "input": {"name": "spotify"}},
        ]))

    client = _claude_with(handler)
    tools = [{"type": "function", "function": {"name": "open_app", "description": "apre",
                                               "parameters": {"type": "object", "properties": {}}}}]
    result = asyncio.run(client.chat(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "apri spotify"}],
        models=["claude-opus-5-5"], tools=tools, tool_choice="auto",
    ))
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5" and body["system"] == "S"
    assert "temperature" not in body and "thinking" not in body
    assert body["output_config"] == {"effort": "low"}
    assert body["fallbacks"] == "default" and "server-side-fallback" in seen["beta"]
    assert body["tool_choice"] == {"type": "auto"}
    msg = result.message
    assert msg["content"] == "Apro Spotify."
    assert msg["tool_calls"][0]["id"] == "toolu_1"
    assert json.loads(msg["tool_calls"][0]["function"]["arguments"]) == {"name": "spotify"}
    assert msg["_claude"][0]["type"] == "thinking" and msg["_claude"][0]["signature"] == "abc"


def test_claude_haiku_skips_the_fallback_beta():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_message([{"type": "text", "text": "Ciao"}], stop="end_turn",
                                                 model="claude-haiku-5-5"))

    result = asyncio.run(_claude_with(handler).chat([{"role": "user", "content": "ciao"}], models=["claude-haiku-5-5"]))
    assert "fallbacks" not in seen["body"] and result.message["content"] == "Ciao"


def test_claude_errors_map_to_ressy_errors():
    def bad_key(request):
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "x"}})

    with pytest.raises(GroqAuthError) as err:
        asyncio.run(_claude_with(bad_key).chat([{"role": "user", "content": "x"}], models=["claude-opus-5-5"]))
    assert err.value.provider == "Claude"

    def limited(request):
        return httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "x"}})

    with pytest.raises(GroqRateLimited):
        asyncio.run(_claude_with(limited).chat([{"role": "user", "content": "x"}], models=["claude-opus-5-5"]))


def test_claude_missing_key():
    with pytest.raises(GroqAuthError):
        asyncio.run(ClaudeClient(lambda: "").chat([{"role": "user", "content": "x"}], models=["claude-opus-5-5"]))


def _gemini_with(handler) -> GeminiClient:
    client = GeminiClient(lambda: "AIza-test")
    client._client = httpx.AsyncClient(base_url=GeminiClient.BASE, transport=httpx.MockTransport(handler))
    return client


def test_gemini_uses_the_openai_endpoint_and_maps_bad_keys():
    seen = {}

    def ok(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Ciao"},
                                                      "finish_reason": "stop"}]})

    result = asyncio.run(_gemini_with(ok).chat([{"role": "user", "content": "x", "_private": 1}],
                                               models=["gemini-2.5-flash"]))
    assert seen["url"].startswith("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    assert seen["body"]["reasoning_effort"] == "low" and "_private" not in seen["body"]["messages"][0]
    assert result.message["content"] == "Ciao"

    def bad(request):
        return httpx.Response(400, json=[{"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}}])

    with pytest.raises(GroqAuthError) as err:
        asyncio.run(_gemini_with(bad).chat([{"role": "user", "content": "x"}], models=["gemini-2.5-flash"]))
    assert err.value.provider == "Gemini"


def test_gemini_transcribe_and_web_answer_use_native_api():
    seen = []

    def handler(request):
        seen.append((str(request.url), json.loads(request.content), request.headers.get("x-goog-api-key")))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "apri spotify"}]}}]})

    client = _gemini_with(handler)
    out = asyncio.run(client.transcribe(b"RIFF", filename="v.wav", mime="audio/wav", model="gemini-2.5-flash"))
    assert out == {"text": "apri spotify"}
    url, body, key = seen[0]
    assert url.endswith("/v1beta/models/gemini-2.5-flash:generateContent") and key == "AIza-test"
    assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "audio/wav"
    asyncio.run(client.web_answer("chi ha vinto?"))
    assert seen[1][1]["tools"] == [{"google_search": {}}]


def test_router_follows_the_users_choice(settings):
    router = LLMRouter(settings)
    settings.llm_provider = "claude"
    settings.claude_model = "claude-sonnet-5-5"
    assert router.client() is router.claude and router.models() == ["claude-sonnet-5-5"] and router.name == "Claude"
    settings.llm_provider = "gemini"
    assert router.client() is router.gemini and router.models()[0] == settings.gemini_model
    settings.llm_provider = "groq"
    assert router.client() is router.groq and router.models() == settings.llm_models()


def test_brain_readiness_per_provider(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(local_stt, "app_dir", lambda: tmp_path)
    settings.llm_provider = "claude"
    settings.stt_engine = "groq"
    assert not settings.brain_ready and "Claude" in settings.brain_problem
    settings.anthropic_api_key = "sk-ant-x"
    assert settings.brain_ready
    settings.stt_engine = "local"
    assert not settings.brain_ready and "modello vocale" in settings.brain_problem
    local_stt.model_path(settings.local_stt_model).write_bytes(b"\0" * 61_000_000)
    assert settings.brain_ready


def _ogg(packets: list[bytes]) -> bytes:
    out = bytearray()
    for seq, packet in enumerate(packets):
        lacing = [255] * (len(packet) // 255) + [len(packet) % 255]
        header = b"OggS" + bytes([0, 2 if seq == 0 else 0]) + struct.pack("<qIII", seq * 960, 1, seq, 0)
        out += header + bytes([len(lacing)]) + bytes(lacing) + packet
    return bytes(out)


def test_opus_voice_note_decodes_to_16k_mono():
    import discord.opus as opus

    opus._load_default()
    encoder = opus.Encoder()
    t = np.arange(48000) / 48000
    tone = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16)
    stereo = np.repeat(tone[:, None], 2, axis=1).reshape(-1)
    frames = [encoder.encode(stereo[i:i + 1920].tobytes(), 960) for i in range(0, len(stereo) - 1919, 1920)]
    head = b"OpusHead" + bytes([1, 2]) + struct.pack("<HIhB", 312, 48000, 0, 0)
    pcm = local_stt.decode_any(_ogg([head, b"OpusTags" + b"\0" * 8, *frames]), "audio/ogg")
    assert abs(len(pcm) - 16000) < 400
    assert np.abs(pcm[2000:]).max() > 3000


def test_local_engine_without_model_explains_what_to_do(settings, tmp_path, monkeypatch):
    from ressy.brain.groq import GroqError
    from ressy.speech import stt as stt_module
    from ressy.speech.stt import SpeechToText

    monkeypatch.setattr(local_stt, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(stt_module, "voiced_seconds", lambda pcm, rate: 1.0)
    settings.stt_engine = "local"
    stt = SpeechToText(settings, llm=None)
    with pytest.raises(GroqError) as err:
        asyncio.run(stt.transcribe_pcm(np.zeros(16000, dtype=np.int16), 16000))
    assert err.value.code == "model_missing"


def test_silence_never_reaches_the_speech_model(settings):
    from ressy.speech.stt import SpeechToText

    class Boom:
        def __getattr__(self, name):
            raise AssertionError("no request for silence")

    stt = SpeechToText(settings, llm=Boom())
    hiss = np.random.default_rng(1).normal(0, 80, 16000 * 2).astype(np.int16)
    result = asyncio.run(stt.transcribe_pcm(hiss, 16000))
    assert result.text == "" and result.rejected == "silence"
