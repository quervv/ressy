from __future__ import annotations

import asyncio
import datetime as dt
import json
import time

import pytest

from ressy.tools import build_registry
from ressy.tools.apps import AppEntry, AppIndex
from ressy.tools.discord import chat_confirmed
from ressy.tools.registry import Channel, Tool, ToolContext, ToolError, ToolRegistry, coerce_args, params
from ressy.tools.reminders import ReminderService, parse_due
from ressy.tools.web import first_youtube_video, normalize_url

VOICE = Channel("voice")
TELEGRAM = Channel("telegram", "42", "@mario")


def test_every_tool_schema_is_well_formed():
    registry = build_registry()
    names = registry.names()
    assert len(names) == len(set(names))
    for tool_schema in registry.schemas(VOICE):
        fn = tool_schema["function"]
        assert tool_schema["type"] == "function"
        assert fn["name"].isidentifier() and len(fn["description"]) < 200
        assert fn["parameters"]["type"] == "object"
        for required in fn["parameters"]["required"]:
            assert required in fn["parameters"]["properties"]
    assert "go_to_sleep" in [s["function"]["name"] for s in registry.schemas(VOICE)]
    assert "go_to_sleep" not in [s["function"]["name"] for s in registry.schemas(TELEGRAM)]


def test_coerce_args_fixes_types_and_checks_required():
    tool = Tool("t", "d", params({"n": {"type": "integer"}, "f": {"type": "boolean"}, "s": {"type": "string",
                                  "enum": ["a", "b"]}}, ["n"]), lambda c, a: "")
    assert coerce_args(tool, {"n": "5", "f": "true", "s": "a", "extra": 1}) == {"n": 5, "f": True, "s": "a"}
    with pytest.raises(ToolError):
        coerce_args(tool, {"f": True})
    with pytest.raises(ToolError):
        coerce_args(tool, {"n": 1, "s": "zzz"})


def test_invoke_never_raises_and_reports_json():
    registry = ToolRegistry()

    def boom(ctx, args):
        raise RuntimeError("bug")

    def refuse(ctx, args):
        raise ToolError("Non posso.")

    async def ok(ctx, args):
        return "Fatto bene."

    registry.extend([Tool("boom", "", params(), boom), Tool("refuse", "", params(), refuse),
                     Tool("ok", "", params(), ok), Tool("local", "", params(), ok, remote=False)])
    ctx = ToolContext(TELEGRAM, services=None)

    async def run():
        return [
            json.loads(await registry.invoke("boom", "{}", ctx)),
            json.loads(await registry.invoke("refuse", "{}", ctx)),
            json.loads(await registry.invoke("ok", "{}", ctx)),
            json.loads(await registry.invoke("missing", "{}", ctx)),
            json.loads(await registry.invoke("ok", "{not json", ctx)),
            json.loads(await registry.invoke("local", "{}", ctx)),
        ]

    boom_r, refuse_r, ok_r, missing_r, bad_r, local_r = asyncio.run(run())
    assert boom_r["ok"] is False and "RuntimeError" in boom_r["errore"]
    assert refuse_r == {"ok": False, "errore": "Non posso."}
    assert ok_r == {"ok": True, "esito": "Fatto bene."}
    assert missing_r["ok"] is False
    assert bad_r["ok"] is False
    assert local_r["ok"] is False
    assert ctx.performed == ["ok: Fatto bene."]


APPS = [
    AppEntry("Calcolatrice", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    AppEntry("Discord", "com.squirrel.Discord.Discord"),
    AppEntry("Disinstalla Discord", "C:\\x\\unins000.exe"),
    AppEntry("Google Chrome", "Chrome"),
    AppEntry("Visual Studio Code", "Microsoft.VisualStudioCode"),
    AppEntry("Word", "Microsoft.Office.WINWORD.EXE.15"),
    AppEntry("WordPad", "{1AC14E77}\\wordpad.exe"),
    AppEntry("Spotify", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"),
    AppEntry("Blocco note", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),
    AppEntry("Telegram Desktop", "TelegramDesktop"),
]


@pytest.fixture()
def index(tmp_path):
    idx = AppIndex(tmp_path / "apps.json")
    idx._apps = list(APPS)
    idx._loaded_at = time.time()
    return idx


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("calcolatrice", "Calcolatrice"),
        ("Discord", "Discord"),
        ("chrome", "Google Chrome"),
        ("vs code", "Visual Studio Code"),
        ("word", "Word"),
        ("spotifi", "Spotify"),
        ("blocco note", "Blocco note"),
        ("notepad", "Blocco note"),
        ("telegram", "Telegram Desktop"),
    ],
)
def test_app_search(index, query, expected):
    entry, _ = index.find(query)
    assert entry is not None and entry.name == expected


def test_app_search_unknown_gives_no_launch(index):
    entry, alternatives = index.find("photoshop")
    assert entry is None


@pytest.mark.parametrize(
    ("before", "after", "recipient", "kind", "ok"),
    [
        ("Amici - Discord", "@Marco Rossi - Discord", "Marco", "user", True),
        ("Amici - Discord", "@marco_99 - Discord", "marco 99", "user", True),
        ("Amici - Discord", "@Luca - Discord", "Marco", "user", False),
        ("#generale | Server di Marco - Discord", "#generale | Server di Marco - Discord", "Marco", "user", False),
        ("Amici - Discord", "#generale | Server - Discord", "generale", "channel", True),
        ("Discord", "Discord", "Marco", "user", False),
        ("@Marco - Discord", "@Marco - Discord", "Marco", "user", True),
    ],
)
def test_discord_chat_confirmation(before, after, recipient, kind, ok):
    assert chat_confirmed(before, after, recipient, kind) is ok


@pytest.mark.parametrize(
    ("raw", "url"),
    [
        ("youtube", "https://www.youtube.com"),
        ("repubblica.it", "https://repubblica.it"),
        ("https://ressy.top/download", "https://ressy.top/download"),
        ("www.google.com:443", "https://www.google.com:443"),
    ],
)
def test_normalize_url(raw, url):
    assert normalize_url(raw) == url


@pytest.mark.parametrize("raw", ["javascript:alert(1)", "file:///C:/Windows", "non è un sito", "mailto:x@y.z"])
def test_normalize_url_refuses(raw):
    with pytest.raises(ToolError):
        normalize_url(raw)


def test_first_youtube_video():
    html = 'xx "videoRenderer":{"videoId":"dQw4w9WgXcQ","thumbnail":{},"title":{"runs":[{"text":"Canzone \\u0026 Co"}]'
    assert first_youtube_video(html) == ("dQw4w9WgXcQ", "Canzone & Co")
    assert first_youtube_video("<html>consent</html>") is None


def test_parse_due():
    now = dt.datetime(2026, 11, 25, 22, 30)
    assert parse_due(20, None, now) == (now + dt.timedelta(minutes=20)).timestamp()
    assert parse_due(None, "23:00", now) == dt.datetime(2026, 11, 25, 23, 0).timestamp()
    assert parse_due(None, "7", now) == dt.datetime(2026, 11, 26, 7, 0).timestamp()
    for bad in [(None, "25:00"), (None, "ieri"), (None, None), (-5, None), (60 * 24 * 40, None)]:
        with pytest.raises(ToolError):
            parse_due(*bad, now)


def test_reminder_service_fires_and_persists(tmp_path):
    fired = []

    async def announce(reminder, late):
        fired.append((reminder.text, late))

    async def run():
        service = ReminderService(tmp_path / "reminders.json", announce)
        service.start()
        service.add("bere acqua", time.time() + 0.2)
        keep = service.add("chiamare Luca", time.time() + 3600)
        assert len(service.list()) == 2
        await asyncio.sleep(0.5)
        service.stop()
        reloaded = ReminderService(tmp_path / "reminders.json", announce)
        reloaded.start()
        ids = [r.id for r in reloaded.list()]
        assert reloaded.cancel(keep.id) is not None
        reloaded.stop()
        return ids

    ids = asyncio.run(run())
    assert fired == [("bere acqua", False)]
    assert len(ids) == 1
