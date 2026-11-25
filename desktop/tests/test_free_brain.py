from __future__ import annotations

import asyncio

import httpx
import pytest

from ressy.brain import quick
from ressy.brain.agent import Brain
from ressy.brain.groq import ChatResult, GroqClient, GroqRateLimited
from ressy.brain.providers import LLMRouter, OpenRouterClient, pick_free_models
from ressy.brain.usage import UsageTracker, limits_from_headers, parse_duration
from ressy.speech.wake import loose_wake, match_wake
from ressy.tools.registry import Channel, Tool, ToolError, ToolRegistry, params

PHRASES = ["ressy sveglia", "sveglia ressy", "ressy svegliati"]


@pytest.mark.parametrize("heard", [
    "Ressi sveglia", "sveglia Ressi", "Ressisveglia.", "Ressie sveja", "Re si sveglia", "Rex sveglia",
    "Reggie sveglia", "Raissi sveglia", "Sveja!", "Svegliaressi", "Rossi, sveglia",
])
def test_sound_alikes_wake_ressy(heard):
    assert match_wake(heard, PHRASES).matched or loose_wake(heard).matched


@pytest.mark.parametrize("heard", ["Che ore sono", "Grazie", "Presto", "Apri Spotify", "Va bene", "Ciao a tutti"])
def test_ordinary_words_do_not_wake(heard):
    assert not match_wake(heard, PHRASES).matched and not loose_wake(heard).matched


def test_command_after_glued_wake_is_kept():
    assert loose_wake("Ressisveglia apri Brave").remainder == "apri Brave"


@pytest.mark.parametrize("said, tool, args", [
    ("Apri Brave", "open_app", {"name": "brave"}),
    ("Apri time.is sul browser", "open_url", {"url": "time.is"}),
    ("Che tempo fa a Roma domani?", "weather", {"city": "Roma"}),
    ("Che meteo c'è?", "weather", {}),
    ("Volume al 30%", "set_volume", {"level": 30}),
    ("Prossima canzone", "media_control", {"action": "next"}),
    ("Ressy, chiudi Chrome", "close_app", {"name": "chrome"}),
])
def test_quick_commands(said, tool, args):
    found = quick.match(said)
    assert found is not None and found.tool == tool and found.args == args


@pytest.mark.parametrize("said", [
    "Apri Spotify e metti una canzone", "Apri il file prova.txt", "apri prova.txt", "Scrivi a Marco ciao",
    "Che cosa sai fare?",
])
def test_longer_requests_go_to_the_ai(said):
    assert quick.match(said) is None


def test_usage_question_is_answered_locally():
    assert quick.match("Quanto usage mi rimane delle API key?").special == "usage"


class NoAI:
    async def chat(self, *args, **kwargs):
        raise AssertionError("the AI must not be asked")

    async def usage_report(self):
        return "Groq: ne restano 990."


def test_quick_command_runs_without_the_ai(settings):
    registry = ToolRegistry()
    registry.add(Tool("open_url", "apre", params({"url": {"type": "string"}}, ["url"]),
                      lambda ctx, a: f"Ho aperto {a['url']} nel browser."))
    brain = Brain(settings, NoAI(), registry, services=None)
    result = asyncio.run(brain.respond("Apri time.is sul browser", Channel("voice")))
    assert result.text == "Ho aperto time.is nel browser."
    assert result.performed == ["open_url: Ho aperto time.is nel browser."]
    assert asyncio.run(brain.respond("quanto mi resta delle api?", Channel("voice"))).text == "Groq: ne restano 990."


def test_failed_quick_command_falls_back_to_the_ai(settings):
    def missing(ctx, args):
        raise ToolError("non trovo l'app")

    class AI:
        async def chat(self, messages, **kwargs):
            return ChatResult({"role": "assistant", "content": "Ci penso io."}, "m")

    registry = ToolRegistry()
    registry.add(Tool("open_app", "apre", params({"name": {"type": "string"}}, ["name"]), missing))
    brain = Brain(settings, AI(), registry, services=None)
    assert asyncio.run(brain.respond("apri pippo", Channel("voice"))).text == "Ci penso io."


def test_groq_and_claude_headers():
    groq = limits_from_headers("groq", {
        "x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
        "x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "5000",
        "x-ratelimit-reset-requests": "2m59.56s", "x-ratelimit-reset-tokens": "7.66s",
    })
    assert groq["requests"]["remaining"] == 990 and groq["requests"]["window"] == "day"
    assert groq["tokens"]["limit"] == 8000 and groq["tokens"]["reset_s"] == pytest.approx(7.66)
    assert parse_duration("2m59.56s") == pytest.approx(179.56)
    claude = limits_from_headers("claude", {
        "anthropic-ratelimit-requests-limit": "50", "anthropic-ratelimit-requests-remaining": "49",
    })
    assert claude["requests"] == {"remaining": 49, "limit": 50, "window": "minute", "reset_s": None}


def test_usage_is_recorded_from_groq_answers(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={
            "x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "998",
            "x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "6000",
        }, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"total_tokens": 321}})

    tracker = UsageTracker(tmp_path / "usage.json")
    client = GroqClient(lambda: "gsk_x")
    client.usage = tracker
    client._client = httpx.AsyncClient(base_url=client.BASE, transport=httpx.MockTransport(handler))
    asyncio.run(client.chat([{"role": "user", "content": "ciao"}], models=["openai/gpt-oss-120b"]))
    assert tracker.today("groq") == {"requests": 1, "tokens": 321}
    text = " ".join(tracker.lines("groq"))
    assert "998 su 1.000" in text and "321 token" in text
    assert UsageTracker(tmp_path / "usage.json").today("groq")["tokens"] == 321


class Limited:
    usage = None

    async def chat(self, messages, **kwargs):
        raise GroqRateLimited("limite", status=429, provider="Groq")


class Answers:
    usage = None

    def __init__(self):
        self.models = None

    async def chat(self, messages, *, models, **kwargs):
        self.models = models
        return ChatResult({"role": "assistant", "content": "dalla riserva"}, models[0])


def test_router_moves_to_the_next_key_when_at_the_limit(settings, tmp_path):
    settings.gemini_api_key = "AIza_test"
    router = LLMRouter(settings, usage=UsageTracker(tmp_path / "u.json"))
    router.groq, router.gemini = Limited(), Answers()
    result = asyncio.run(router.chat([{"role": "user", "content": "ciao"}], models=["openai/gpt-oss-120b"]))
    assert result.message["content"] == "dalla riserva"
    assert router.gemini.models[0] == settings.gemini_model
    assert router.usage.blocked_for("groq") > 0
    assert router.chain() == ["groq", "gemini"]


def test_router_without_other_keys_suggests_one(settings, tmp_path):
    router = LLMRouter(settings, usage=UsageTracker(tmp_path / "u.json"))
    router.groq = Limited()
    with pytest.raises(GroqRateLimited) as info:
        asyncio.run(router.chat([{"role": "user", "content": "ciao"}]))
    assert "OpenRouter" in str(info.value)


def test_fallback_can_be_turned_off(settings, tmp_path):
    settings.gemini_api_key = "AIza_test"
    settings.llm_fallback = False
    router = LLMRouter(settings, usage=UsageTracker(tmp_path / "u.json"))
    assert router.chain() == ["groq"]


def test_free_openrouter_models_are_picked_and_ranked():
    models = [
        {"id": "paid/model", "pricing": {"prompt": "0.000001", "completion": "0.000002"},
         "supported_parameters": ["tools"]},
        {"id": "liquid/lfm-3-1.7b:free", "pricing": {"prompt": "0", "completion": "0"},
         "supported_parameters": ["tools"]},
        {"id": "google/gemma-4-31b-it:free", "pricing": {"prompt": "0", "completion": "0"},
         "supported_parameters": ["tools", "tool_choice"]},
        {"id": "x/no-tools:free", "pricing": {"prompt": "0", "completion": "0"},
         "supported_parameters": ["temperature"]},
        {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
    ]
    assert pick_free_models(models) == ["google/gemma-4-31b-it:free", "liquid/lfm-3-1.7b:free"]


def test_openrouter_key_check_reads_the_free_allowance(tmp_path):
    def handler(request):
        if request.url.path.endswith("/key"):
            assert request.headers["authorization"] == "Bearer sk-or-test"
            return httpx.Response(200, json={"data": {
                "is_free_tier": True, "limit": None, "limit_remaining": None,
                "free_model_daily_requests": {"used": 8, "limit": 50, "remaining": 42}}})
        return httpx.Response(200, json={"data": [
            {"id": "google/gemma-4-31b-it:free", "pricing": {"prompt": "0", "completion": "0"},
             "supported_parameters": ["tools"]}]})

    tracker = UsageTracker(tmp_path / "u.json")
    client = OpenRouterClient(lambda: "")
    client.usage = tracker
    client._client = httpx.AsyncClient(base_url=client.BASE, transport=httpx.MockTransport(handler))
    assert asyncio.run(client.list_models("sk-or-test")) == ["google/gemma-4-31b-it:free"]
    assert "42 su 50" in " ".join(tracker.lines("openrouter"))
