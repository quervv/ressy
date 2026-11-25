from __future__ import annotations

import asyncio
import hashlib
import json
import zipfile

import httpx
import pytest

from ressy.brain import local_llm
from ressy.brain.local_llm import (
    LlamaServer,
    LocalLLMClient,
    build_prompt,
    parse_reply,
    to_local_messages,
)
from ressy.brain.providers import LLMRouter
from ressy.brain.usage import UsageTracker

OPEN_APP = {"type": "function", "function": {
    "name": "open_app", "description": "Avvia un programma o un'app installata (es. Spotify). Altro.",
    "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}}
VOLUME = {"type": "function", "function": {
    "name": "set_volume", "description": "Volume del PC",
    "parameters": {"type": "object", "properties": {"level": {"type": "integer"},
                                                    "change": {"type": "string", "enum": ["up", "down"]}}}}}
DISCORD = {"type": "function", "function": {"name": "send_discord_message", "description": "Scrive su Discord",
                                            "parameters": {"type": "object", "properties": {}}}}


def test_prompt_has_one_short_line_per_tool():
    prompt = build_prompt([OPEN_APP, VOLUME], "Alex")
    assert "PC di Alex" in prompt
    assert "- open_app(name: string): Avvia un programma o un'app installata" in prompt
    assert "- set_volume(level?: integer, change?: up|down): Volume del PC" in prompt


def test_reply_becomes_a_tool_call_or_an_answer():
    call = parse_reply('{"azione": "open_app", "argomenti": {"name": "Spotify"}, "risposta": ""}', {"open_app"}, "x1")
    assert call["tool_calls"][0]["function"] == {"name": "open_app", "arguments": '{"name": "Spotify"}'}
    said = parse_reply('{"azione": "rispondi", "argomenti": {}, "risposta": "Ciao!"}', {"open_app"}, "x2")
    assert said == {"role": "assistant", "content": "Ciao!"}
    unknown = parse_reply('{"azione": "format_disk", "argomenti": {}, "risposta": "No."}', {"open_app"}, "x3")
    assert "tool_calls" not in unknown
    assert parse_reply("non json", set(), "x4")["content"] == "non json"


def test_history_is_rendered_as_plain_turns():
    messages = [
        {"role": "system", "content": "lungo prompt di Ressy"},
        {"role": "user", "content": "apri spotify"},
        {"role": "assistant", "tool_calls": [{"id": "c", "function": {"name": "open_app", "arguments": '{"name":"spotify"}'}}]},
        {"role": "tool", "name": "open_app", "content": '{"ok": true, "esito": "Ho avviato Spotify."}'},
    ]
    chat = to_local_messages(messages, "SYS")
    assert chat[0] == {"role": "system", "content": "SYS"}
    assert json.loads(chat[2]["content"]) == {"azione": "open_app", "argomenti": {"name": "spotify"}, "risposta": ""}
    assert chat[3]["content"].startswith("Risultato di open_app:")


class StubServer:
    base_url = "http://127.0.0.1:1"
    key = "k"

    def __init__(self):
        self.started = []

    def ensure(self, name):
        self.started.append(name)

    def stop(self):
        pass


def _client(monkeypatch, reply: dict):
    sent = []

    def post(url, headers=None, json=None, timeout=None):
        sent.append((url, headers, json))
        return httpx.Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(reply)}}],
                                         "usage": {"total_tokens": 42}})

    monkeypatch.setattr(local_llm.httpx, "post", post)
    server = StubServer()
    client = LocalLLMClient(lambda: "qwen2.5-0.5b", server=server)
    return client, server, sent


def test_client_asks_llama_server_with_a_json_schema(monkeypatch):
    client, server, sent = _client(monkeypatch, {"azione": "open_app", "argomenti": {"name": "Brave"}, "risposta": ""})
    result = asyncio.run(client.chat([{"role": "user", "content": "apri brave"}], tools=[OPEN_APP, DISCORD]))
    assert server.started == ["qwen2.5-0.5b"]
    url, headers, body = sent[0]
    assert url == "http://127.0.0.1:1/v1/chat/completions" and headers["Authorization"] == "Bearer k"
    branches = body["response_format"]["json_schema"]["schema"]["anyOf"]
    actions = sorted(b["properties"]["azione"]["const"] for b in branches)
    assert actions == ["open_app", "rispondi"]
    app = next(b for b in branches if b["properties"]["azione"]["const"] == "open_app")
    assert app["properties"]["argomenti"]["additionalProperties"] is False
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert result.message["tool_calls"][0]["function"]["name"] == "open_app"


def test_no_tools_when_only_an_answer_is_wanted(monkeypatch):
    client, _, sent = _client(monkeypatch, {"azione": "rispondi", "argomenti": {}, "risposta": "Fatto."})
    asyncio.run(client.chat([{"role": "user", "content": "ok"}], tools=[OPEN_APP], tool_choice="none"))
    branches = sent[0][2]["response_format"]["json_schema"]["schema"]["anyOf"]
    assert [b["properties"]["azione"]["const"] for b in branches] == ["rispondi"]


def test_a_tool_result_is_said_without_asking_the_model(monkeypatch):
    client, _, sent = _client(monkeypatch, {"azione": "rispondi", "argomenti": {}, "risposta": "x"})
    history = [
        {"role": "user", "content": "apri brave"},
        {"role": "assistant", "tool_calls": [{"id": "a", "function": {"name": "open_app", "arguments": "{}"}}]},
        {"role": "tool", "name": "open_app", "content": '{"ok": true, "esito": "Ho avviato Brave."}'},
    ]
    result = asyncio.run(client.chat(history, tools=[OPEN_APP]))
    assert result.message["content"] == "Ho avviato Brave." and sent == []


def test_a_repeated_action_turns_into_its_result(monkeypatch):
    client, _, _ = _client(monkeypatch, {"azione": "open_app", "argomenti": {"name": "Brave"}, "risposta": ""})
    history = [
        {"role": "user", "content": "apri brave"},
        {"role": "assistant", "tool_calls": [{"id": "a", "function": {"name": "open_app", "arguments": "{}"}}]},
        {"role": "tool", "name": "open_app", "content": '{"ok": true, "esito": "Ho avviato Brave."}'},
    ]
    result = asyncio.run(client.chat(history, tools=[OPEN_APP]))
    assert result.message == {"role": "assistant", "content": "Ho avviato Brave."}


def test_server_stays_on_this_pc_with_a_key():
    server = LlamaServer()
    server.port, server.key = 4321, "segreto"
    cmd = server.command(local_llm.model_path("qwen2.5-0.5b"))
    assert cmd[0].endswith("llama-server.exe")
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--api-key") + 1] == "segreto"


def _zip(tmp_path):
    archive = tmp_path / "llama.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in ("llama-server.exe", "llama.dll", "ggml-cpu-haswell.dll", "LICENSE-LLVM-OpenMP",
                     "llama-cli.exe", "llama-tts.exe"):
            zf.writestr(name, b"x" * 10)
    return archive


def test_runtime_must_match_the_official_hash(tmp_path):
    with pytest.raises(OSError):
        local_llm.install_runtime(_zip(tmp_path), tmp_path / "out")


def test_runtime_keeps_only_what_the_server_needs(tmp_path, monkeypatch):
    archive = _zip(tmp_path)
    monkeypatch.setattr(local_llm, "LLAMA_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    target = tmp_path / "out"
    target.mkdir()
    local_llm.install_runtime(archive, target)
    assert sorted(p.name for p in target.iterdir()) == [
        ".ressy-ok", "LICENSE-LLVM-OpenMP", "ggml-cpu-haswell.dll", "llama-server.exe", "llama.dll"]


def test_download_size_counts_the_engine_once():
    assert local_llm.download_size_mb("qwen2.5-0.5b") == 491 + local_llm.LLAMA_MB


def test_the_ai_on_the_pc_is_always_the_last_reserve(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm, "is_downloaded", lambda name: True)
    settings.gemini_api_key = "AIza_test"
    settings.local_llm_model = "qwen2.5-0.5b"
    usage = UsageTracker(tmp_path / "u.json")
    usage.record_limited("gemini", "", 60)
    router = LLMRouter(settings, usage=usage)
    assert router.chain() == ["groq", "gemini", "local"]
    assert router.models("local") == ["qwen2.5-0.5b"]
    settings.llm_provider = "local"
    assert router.chain()[0] == "local"
    assert settings.brain_problem == "" or "voce" in settings.brain_problem.lower()


def test_without_the_model_the_pc_brain_asks_for_it(settings, monkeypatch):
    monkeypatch.setattr(local_llm, "is_downloaded", lambda name: False)
    settings.llm_provider = "local"
    settings.local_llm_model = "qwen2.5-0.5b"
    assert "modello AI sul PC" in settings.brain_problem
