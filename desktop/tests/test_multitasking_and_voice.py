from __future__ import annotations

import asyncio
import json
import time
import zipfile

import httpx
import numpy as np
import pytest

from ressy.audio.mic import RATE
from ressy.audio.pcm import prepare_for_stt
from ressy.brain import local_llm, planner, quick
from ressy.brain.agent import Brain
from ressy.brain.groq import ChatResult
from ressy.core import controller as ctl
from ressy.speech.stt import clean_transcription
from ressy.speech.textnorm import fix_spoken_text
from ressy.speech.wake import is_sleep_command, loose_wake
from ressy.tools import apps, build_registry, discord, more, reminders, screen, system, web, winapi
from ressy.tools.registry import Channel, Tool, ToolContext, ToolError, ToolRegistry, params
from test_controller import make as make_controller, run

VOICE = Channel("voice")


def test_fix_spoken_text_handles_whisper_italian_slips():
    assert fix_spoken_text("apri discorso è scrivi a marco ciao") == "apri Discord e scrivi a marco ciao"
    assert fix_spoken_text("apri spotifai") == "apri Spotify"
    assert fix_spoken_text("apri uozzap") == "apri WhatsApp"
    assert fix_spoken_text("apri time is") == "apri time.is"
    assert fix_spoken_text("fammi un discorso") == "fammi un discorso"
    assert fix_spoken_text("hey Ressy, what time is it") == "hey Ressy, what time is it"


def test_stt_keeps_foreign_names_at_moderate_logprob_and_strips_noise():
    seg = {"text": "apri Discord e scrivi a Marco", "no_speech_prob": 0.0, "avg_logprob": -1.5, "compression_ratio": 1.1}
    assert clean_transcription({"segments": [seg]}).ok
    silence = {"text": "ciao", "no_speech_prob": 0.8, "avg_logprob": -0.9, "compression_ratio": 1.0}
    assert not clean_transcription({"segments": [silence]}).ok


def test_prepare_for_stt_keeps_soft_speech_after_a_brief_click():
    click = np.zeros(int(RATE * 0.03), dtype=np.int16)
    click[:50] = 28000
    t = np.arange(int(RATE * 1.0))
    soft = (np.sin(t / 6.0) * 600).astype(np.int16)
    pcm = np.concatenate([np.zeros(RATE, dtype=np.int16), click, soft, np.zeros(RATE, dtype=np.int16)])
    out = prepare_for_stt(pcm, RATE)
    assert out.size > RATE * 0.8


def test_extra_wake_and_sleep_variants():
    assert loose_wake("Ricci sveglia apri Discord").remainder == "apri Discord"
    assert is_sleep_command("va bene grazie")
    assert is_sleep_command("ok vai a dormire")


@pytest.mark.parametrize("text, expected", [
    ("apri discord è scrivi a marco ciao", ["apri discord", "scrivi a marco ciao"]),
    ("apri discorso è scrivi a marco ciao", ["apri Discord", "scrivi a marco ciao"]),
    ("apri discord scrivi a marco ciao", ["apri discord", "scrivi a marco ciao"]),
    ("puoi aprire discord e scrivere a marco che arrivo", ["puoi aprire discord", "scrivere a marco che arrivo"]),
    ("apri discord e gli scrivi ciao", ["apri discord", "gli scrivi ciao"]),
    ("apri discord, scrivi a marco che arrivo, metti un timer di 5 minuti e crea la cartella compiti",
     ["apri discord", "scrivi a marco che arrivo", "metti un timer di 5 minuti", "crea la cartella compiti"]),
])
def test_planner_splits_spoken_multitasking_variants(text, expected):
    assert planner.split_actions(text) == expected
    assert planner.looks_compound(text)


def test_fallback_plan_propagates_discord_and_editor_context():
    steps = planner.fallback_plan("apri discord e scrivi a marco ciao")
    assert steps == [
        planner.Step("apri discord", False),
        planner.Step("su Discord, scrivi a marco ciao", False),
    ]
    editor_steps = planner.fallback_plan("apri blocco note e scrivi lista spesa")
    assert editor_steps == [
        planner.Step("apri blocco note", False),
        planner.Step("in blocco note, scrivi lista spesa", True),
    ]


def test_local_brain_runs_apri_discord_e_scrivi_a_x(settings):
    done = []

    class LocalStyleLLM:
        def chain(self):
            return ["local"]

        async def chat(self, messages, *, models=None, tools=None, tool_choice=None, **kwargs):
            note = messages[-1]["content"]
            assert "send_discord_message" in {t["function"]["name"] for t in tools}
            if "su Discord" in note:
                return ChatResult({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "send_discord_message",
                            "arguments": json.dumps({"recipient": "Marco", "message": "che non va", "kind": "user"}),
                        },
                    }],
                }, model="qwen2.5-1.5b")
            return ChatResult({"role": "assistant", "content": "Fatto."}, model="qwen2.5-1.5b")

    registry = ToolRegistry()
    registry.add(Tool("open_app", "apre", params({"name": {"type": "string"}}, ["name"]),
                      lambda c, a: (done.append(("open_app", a["name"])) or "Ho aperto Discord: è pronto.")))
    registry.add(Tool("send_discord_message", "discord",
                      params({"recipient": {"type": "string"}, "message": {"type": "string"},
                              "kind": {"type": "string"}}, ["message"]),
                      lambda c, a: (done.append(("send_discord_message", a)) or f"Messaggio inviato su Discord a {a['recipient']}.")))

    brain = Brain(settings, LocalStyleLLM(), registry, services=None)
    result = asyncio.run(brain.respond("apri discord e scrivi a Marco questo non va", VOICE))
    assert done == [
        ("open_app", "discord"),
        ("send_discord_message", {"recipient": "Marco", "message": "che non va", "kind": "user"}),
    ]
    assert "Ho aperto Discord: è pronto." in result.text
    assert "Messaggio inviato su Discord a Marco." in result.text

    done.clear()
    result2 = asyncio.run(brain.respond("apri discord e scrivi a Marco che arrivo", VOICE))
    assert done == [
        ("open_app", "discord"),
        ("send_discord_message", {"recipient": "Marco", "message": "arrivo", "kind": "user"}),
    ]
    assert "Messaggio inviato su Discord a Marco." in result2.text


def test_step_data_context_flows_from_read_to_next_step(settings):
    class FakeLLM:
        def __init__(self):
            self.notes = []

        async def chat(self, messages, *, models=None, tools=None, tool_choice=None, **kwargs):
            content = messages[-1]["content"]
            if "dividi" in messages[0]["content"].lower():
                return ChatResult({"role": "assistant", "content": json.dumps({
                    "steps": [
                        {"do": "leggi gli appunti", "needs_previous": False},
                        {"do": "manda su Discord a Marco quello che hai letto", "needs_previous": True},
                    ]
                })}, model="m")
            self.notes.append(content)
            if messages[-1]["role"] == "tool":
                return ChatResult({"role": "assistant", "content": "Negli appunti c'è codice 42."}, model="m")
            if "azione 1:" in content:
                return ChatResult({"role": "assistant", "content": None, "tool_calls": [
                    {"id": "1", "type": "function", "function": {"name": "clipboard", "arguments": '{"action":"get"}'}}
                ]}, model="m")
            return ChatResult({"role": "assistant", "content": None, "tool_calls": [
                {"id": "2", "type": "function", "function": {
                    "name": "send_discord_message",
                    "arguments": json.dumps({"recipient": "Marco", "message": "codice 42"}),
                }}
            ]}, model="m")

    registry = ToolRegistry()
    registry.add(Tool("clipboard", "clip", params({"action": {"type": "string"}}, ["action"]),
                      lambda c, a: "Negli appunti c'è:\ncodice 42"))
    registry.add(Tool("send_discord_message", "dc",
                      params({"recipient": {"type": "string"}, "message": {"type": "string"}}, ["message"]),
                      lambda c, a: f"Inviato: {a['message']}"))
    settings.quick_commands = False
    llm = FakeLLM()
    brain = Brain(settings, llm, registry, services=None)
    result = asyncio.run(brain.respond("leggi gli appunti e mandali a Marco su Discord", VOICE))
    assert "codice 42" in llm.notes[-1]
    assert "Inviato: codice 42" in result.text


def test_local_llm_1_5b_includes_discord_and_continues_on_looking(monkeypatch):
    sent = []

    def post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"azione":"rispondi","argomenti":{},"risposta":"Ok"}'}}]})

    monkeypatch.setattr(local_llm.httpx, "post", post)

    class Stub:
        base_url = "http://127.0.0.1:1"
        key = "k"

        def ensure(self, name):
            pass

    client = local_llm.LocalLLMClient(lambda: "qwen2.5-1.5b", server=Stub())
    tools = build_registry().schemas(VOICE)
    asyncio.run(client.chat([{"role": "user", "content": "scrivi su discord a Marco ciao"}], tools=tools))
    actions = {b["properties"]["azione"]["const"] for b in sent[0]["response_format"]["json_schema"]["schema"]["anyOf"]}
    assert {"send_discord_message", "window_action", "notes", "timer", "clipboard", "find_files"} <= actions

    assert local_llm.result_reply([
        {"role": "user", "content": "leggi lo schermo e clicca OK"},
        {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "read_screen", "arguments": "{}"}}]},
        {"role": "tool", "name": "read_screen", "content": '{"ok": true, "esito": "OK"}'},
    ]) is None
    assert local_llm.result_reply([
        {"role": "user", "content": "apri Discord a sinistra"},
        {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "open_app", "arguments": "{}"}}]},
        {"role": "tool", "name": "open_app", "content": '{"ok": true, "esito": "Ho aperto Discord: è pronto."}'},
    ]) is None


def test_discord_canary_titles_and_switcher_filters():
    assert discord._chat_name("@Marco - Discord Canary") == "@Marco"
    assert discord.chat_confirmed("Amici - Discord Canary", "@Marco - Discord Canary", "Marco", "user")

    def line(text, y):
        return screen.Line(text, tuple(screen.Word(w, 100 + i * 50, y, 40, 14) for i, w in enumerate(text.split())))

    lines = [
        line("ho parlato con trisercia ieri", 80),
        line("@trisercia", 150),
        line("MESSAGGI DIRETTI", 180),
        line("Trisser trisser_99", 210),
    ]
    choice = discord.pick_result(lines, "trisercia", "@trisercia")
    assert choice is not None and "Trisser" in choice[2]


@pytest.mark.parametrize("said, tool, args_sub", [
    ("apri google punto it", "open_url", {"url": "google.it"}),
    ("scrivi su discord a Marco: ci vediamo dopo", "send_discord_message",
     {"recipient": "Marco", "message": "ci vediamo dopo", "kind": "user"}),
    ("manda su discord a Luca che arrivo alle 5", "send_discord_message",
     {"recipient": "Luca", "message": "arrivo alle 5", "kind": "user"}),
    ("su discord, scrivi a Marco ciao", "send_discord_message",
     {"recipient": "Marco", "message": "ciao", "kind": "user"}),
    ("scrivi qui su discord: arrivo", "send_discord_message",
     {"message": "arrivo", "kind": "current"}),
    ("leggi discord di Marco", "read_discord_chat", {"recipient": "Marco", "kind": "user"}),
    ("metti un timer di 5 minuti per la pasta", "timer", {"action": "start", "minutes": 5.0, "label": "la pasta"}),
    ("avvia il cronometro", "timer", {"action": "stopwatch_start"}),
    ("segna nella spesa latte e pane", "notes", {"action": "add", "text": "latte e pane", "category": "spesa"}),
    ("leggi la lista della spesa", "notes", {"action": "list", "category": "spesa"}),
    ("cerca cuffie bluetooth su amazon", "web_search", {"query": "cuffie bluetooth", "site": "amazon"}),
    ("metti Discord a sinistra", "window_action", {"action": "snap_left", "app": "discord"}),
    ("mostra il desktop", "window_action", {"action": "minimize_all"}),
    ("passa a Chrome", "focus_app", {"name": "chrome"}),
    ("leggi gli appunti", "clipboard", {"action": "get"}),
    ("scorri giù", "mouse_action", {"action": "scroll_down"}),
    ("togli il muto", "set_volume", {"change": "mute"}),
    ("svuota il cestino", "system_control", {"action": "empty_recycle_bin"}),
])
def test_new_quick_commands(said, tool, args_sub):
    found = quick.match(said)
    assert found is not None and found.tool == tool
    for k, v in args_sub.items():
        assert found.args[k] == v


def test_quick_math_extended_and_fun():
    assert quick.match("quanto fa 2 + 3 * 4").answer == "Fa 14."
    assert quick.match("il 20% di 150").answer == "Fa 30."
    assert quick.match("radice quadrata di 144").answer == "Fa 12."
    assert quick.match("lancia una moneta").answer in ("Testa!", "Croce!")
    assert quick.match("tira un dado").answer.startswith("È uscito ")


def test_apps_find_refreshes_stale_index_when_best_score_is_low(tmp_path):
    idx = apps.AppIndex(tmp_path / "apps.json")
    idx._apps = [apps.AppEntry("OneNote", "OneNote")]
    idx._loaded_at = time.time() - 120
    refreshed = []
    idx.refresh = lambda: (refreshed.append(1), idx._apps.append(apps.AppEntry("Fortnite", "epic://fn")), 2)[-1]
    entry, _ = idx.find("fortnite")
    assert refreshed == [1] and entry is not None and entry.name == "Fortnite"


def test_file_zip_unzip_find_and_notes(tmp_path, monkeypatch):
    desktop = tmp_path / "Desktop"
    docs = tmp_path / "Documents"
    desktop.mkdir()
    docs.mkdir()
    monkeypatch.setattr(more, "_home", lambda: tmp_path.resolve())
    monkeypatch.setattr(winapi, "known_folder", lambda k: str(desktop if k == "desktop" else docs))
    monkeypatch.setattr(more, "app_dir", lambda: tmp_path)

    folder = desktop / "progetto"
    folder.mkdir()
    (folder / "relazione.txt").write_text("contenuto", encoding="utf-8")
    ctx = ToolContext(channel=VOICE, services=None)

    assert "Ho compresso" in more.file_action(ctx, {"action": "zip", "name": "progetto", "new_name": "backup"})
    assert (desktop / "backup.zip").is_file()
    assert "Ho estratto" in more.file_action(ctx, {"action": "unzip", "name": "backup.zip", "destination": "documenti"})
    assert (docs / "progetto" / "relazione.txt").read_text(encoding="utf-8") == "contenuto"

    bad_zip = desktop / "evil.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../../outside.txt", "nope")
    with pytest.raises(ToolError, match="non sicuri"):
        more.file_action(ctx, {"action": "unzip", "name": "evil.zip"})

    found = more.find_files(ctx, {"query": "relazione"})
    assert "relazione.txt" in found

    assert "latte" in more.notes_tool(ctx, {"action": "add", "text": "latte", "category": "spesa"})
    assert "latte" in more.notes_tool(ctx, {"action": "list", "category": "spesa"})
    assert "tolto" in more.notes_tool(ctx, {"action": "remove", "text": "latte"})
    assert "nessuna nota" in more.notes_tool(ctx, {"action": "list"})


def test_read_webpage_ssrf_and_html_cleaning(monkeypatch):
    ctx = ToolContext(channel=VOICE, services=None)
    with pytest.raises(ToolError, match="locali o privati"):
        web.read_webpage(ctx, {"url": "http://127.0.0.1:8080/secret"})

    class Resp:
        url = "https://example.com/news"
        text = "<html><head><style>x{}</style><script>alert(1)</script></head><body><h1>Titolo</h1><p>Ciao &amp; benvenuto.</p></body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(web.socket, "getaddrinfo", lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    monkeypatch.setattr(web.httpx, "get", lambda *a, **kw: Resp())
    out = web.read_webpage(ctx, {"url": "example.com/news"})
    assert "Titolo" in out and "Ciao & benvenuto." in out and "alert" not in out


def test_system_control_processes_disks_and_clipboard(monkeypatch):
    ctx = ToolContext(channel=VOICE, services=None)
    assert "GB liberi" in system.system_control(ctx, {"action": "disk_space"})
    assert "RAM" in system.system_control(ctx, {"action": "top_processes"})

    box = {"clip": ""}
    monkeypatch.setattr(winapi, "set_clipboard_text", lambda text: box.__setitem__("clip", text))
    monkeypatch.setattr(winapi, "get_clipboard_text", lambda: box["clip"])
    monkeypatch.setattr(winapi, "clear_clipboard", lambda: box.__setitem__("clip", ""))
    assert "copiato" in system.clipboard(ctx, {"action": "set", "text": "prova 123"})
    assert "prova 123" in system.clipboard(ctx, {"action": "get"})
    assert "svuotato" in system.clipboard(ctx, {"action": "clear"})
    assert "vuoti" in system.clipboard(ctx, {"action": "get"})


def test_timer_and_scheduled_command(make_controller, tmp_path):
    c, ui = make_controller()

    async def scenario():
        svc = reminders.ReminderService(tmp_path / "rem.json", c._announce_reminder)
        c.reminders = svc
        c.services.reminders = svc
        svc.start()
        try:
            ctx = ToolContext(channel=VOICE, services=c.services)
            msg = await reminders.timer_tool(ctx, {"action": "start", "seconds": 0.15, "command": "apri spotify"})
            assert "Eseguirò «apri spotify»" in msg
            await asyncio.sleep(0.35)
            await asyncio.wait_for(c._queue.join(), timeout=3)
            assert ("apri spotify", "voice") in c.brain.requests
        finally:
            svc.stop()

    run(c, scenario)
