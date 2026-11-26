from __future__ import annotations

import asyncio
import json
import time

import pytest

from ressy.brain import planner
from ressy.brain.agent import Brain
from ressy.brain.groq import ChatResult
from ressy.tools.registry import Channel, Tool, ToolContext, ToolError, ToolRegistry, params

VOICE = Channel("voice")


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def chat(self, messages, *, models, tools=None, tool_choice=None, **kwargs):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        return ChatResult(message=self.script.pop(0), model=models[0])


def say(text):
    return {"role": "assistant", "content": text}


def call(name, args, call_id="c1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def calls(*items):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        for i, (name, args) in enumerate(items)]}


def plan(*steps):
    return say(json.dumps({"steps": [{"do": s, "needs_previous": n} for s, n in steps]}, ensure_ascii=False))


def make(settings, script, tools):
    settings.quick_commands = False
    registry = ToolRegistry()
    registry.extend(tools)
    llm = FakeLLM(script)
    return Brain(settings, llm, registry, services=None), llm


def recorder(done, name, result="ok", fail=None):
    def run(ctx, args):
        done.append((name, args))
        if fail:
            raise ToolError(fail)
        return result
    return Tool(name, name, params({"name": {"type": "string"}, "message": {"type": "string"}}), run)


@pytest.mark.parametrize("text, pieces", [
    ("apri discord e scrivi a marco che arrivo tra 10 minuti e poi crea una cartella compiti",
     ["apri discord", "scrivi a marco che arrivo tra 10 minuti", "crea una cartella compiti"]),
    ("Apri Discord, scrivi a Marco ciao e poi crea la cartella prova.",
     ["Apri Discord", "scrivi a Marco ciao", "crea la cartella prova."]),
    ("dimmi che tempo fa e apri spotify", ["dimmi che tempo fa", "apri spotify"]),
    ("open discord and send hi to marco then create a folder named test",
     ["open discord", "send hi to marco", "create a folder named test"]),
    ("scrivi a luca: compra il pane e passa da me, poi apri spotify",
     ["scrivi a luca: compra il pane e passa da me", "apri spotify"]),
    ("Ressy apri Discord. Scrivi a Marco «ci vediamo alle 5, porta la palla» e crea una cartella foto",
     ["Ressy apri Discord", "Scrivi a Marco «ci vediamo alle 5, porta la palla»", "crea una cartella foto"]),
    ("ciao Ressy, come va, apri Discord e scrivi a Marco ciao",
     ["ciao Ressy, come va, apri Discord", "scrivi a Marco ciao"]),
])
def test_requests_with_several_orders_are_cut_where_each_starts(text, pieces):
    assert planner.split_actions(text) == pieces
    assert planner.looks_compound(text)


@pytest.mark.parametrize("text", [
    "scrivi a Marco che io e Luca arriviamo",
    "scrivi a luca: compra il pane e passa da me",
    "Scrivi a Marco: arrivo tardi. Porta il pane.",
    "apri discord e spotify",
    "come stai e che fai?",
    "ricordami tra 10 minuti di chiamare marco e luca",
    "ricordami dopo cena di chiamare la nonna",
    "che ore sono",
])
def test_single_requests_are_left_whole(text):
    assert not planner.looks_compound(text)
    assert planner.split_actions(text) == [text]


def test_parse_plan_accepts_the_model_json_and_rejects_the_rest():
    steps = planner.parse_plan('Ecco: {"steps": [{"do": "apri Discord", "needs_previous": true}, '
                               '"crea la cartella x", {"do": "scrivi nel Blocco note", "needs_previous": true}]}')
    assert steps == [planner.Step("apri Discord"), planner.Step("crea la cartella x"),
                     planner.Step("scrivi nel Blocco note", True)]
    assert planner.parse_plan("non lo so") is None
    assert planner.parse_plan('{"steps": []}') is None
    assert len(planner.parse_plan(json.dumps({"steps": [f"passo {i}" for i in range(20)]}))) == planner.MAX_PLAN_STEPS


def test_each_step_is_done_in_order_and_the_answer_says_all_of_it(settings):
    done = []
    brain, llm = make(settings, [
        plan(("apri Discord", False), ("manda su Discord a Marco il messaggio «ciao»", False),
             ("crea la cartella «prova»", False)),
        call("open_app", {"name": "Discord"}),
        call("send_discord_message", {"name": "Marco", "message": "ciao"}),
        call("create_folder", {"name": "prova"}),
    ], [
        recorder(done, "open_app", "Ho aperto Discord: è pronto."),
        recorder(done, "send_discord_message", "Messaggio inviato su Discord a Marco."),
        recorder(done, "create_folder", "La cartella prova è stata creata sul Desktop."),
    ])
    steps_seen = []
    result = asyncio.run(brain.respond("apri discord e scrivi a marco ciao e poi crea la cartella prova", VOICE,
                                       on_step=lambda i, n, t: steps_seen.append((i, n))))
    assert [name for name, _ in done] == ["open_app", "send_discord_message", "create_folder"]
    assert result.text == ("Ho aperto Discord: è pronto. Messaggio inviato su Discord a Marco. "
                           "La cartella prova è stata creata sul Desktop.")
    assert steps_seen == [(1, 3), (2, 3), (3, 3)]
    assert len(llm.calls) == 4
    note = llm.calls[2]["messages"][-1]["content"]
    assert "Ora fai solo l'azione 2: manda su Discord a Marco il messaggio «ciao»" in note
    assert "Già fatto: 1) apri Discord → Ho aperto Discord: è pronto." in note
    assert brain.memory.history("voice")[-1]["content"] == result.text


def test_a_step_that_needs_the_failed_one_is_skipped_the_others_still_run(settings):
    done = []
    brain, llm = make(settings, [
        plan(("apri il Blocco note", False), ("scrivi nel Blocco note «ciao»", True), ("crea la cartella «x»", False)),
        call("open_app", {"name": "Blocco note"}),
        say("Non trovo il Blocco note su questo PC."),
        call("create_folder", {"name": "x"}),
    ], [
        recorder(done, "open_app", fail="Non trovo nessun programma chiamato 'Blocco note'."),
        recorder(done, "type_text"),
        recorder(done, "create_folder", "La cartella x è stata creata."),
    ])
    result = asyncio.run(brain.respond("apri il blocco note e scrivici ciao e crea la cartella x", VOICE))
    assert [name for name, _ in done] == ["open_app", "create_folder"]
    assert result.text.startswith("Non trovo il Blocco note su questo PC.")
    assert "Non ho fatto «scrivi nel Blocco note «ciao»», perché serviva il passo prima." in result.text
    assert result.text.endswith("La cartella x è stata creata.") or "La cartella x è stata creata." in result.text


def test_a_missing_detail_stops_the_plan_and_asks(settings):
    done = []
    brain, llm = make(settings, [
        plan(("manda un messaggio su Discord", False), ("crea la cartella «x»", False)),
        say("A chi devo scriverlo?"),
    ], [recorder(done, "create_folder")])
    result = asyncio.run(brain.respond("manda un messaggio su discord e crea la cartella x", VOICE))
    assert done == []
    assert result.text == "Poi devo ancora: «crea la cartella «x»». A chi devo scriverlo?"


def test_opening_an_app_is_not_the_end_of_a_step_that_writes_in_it(settings):
    done = []
    brain, llm = make(settings, [
        plan(("apri Spotify", False), ("scrivi nel Blocco note «ciao»", False)),
        call("open_app", {"name": "Spotify"}),
        call("open_app", {"name": "Blocco note"}),
        call("type_text", {"name": "ciao"}),
    ], [recorder(done, "open_app", "Aperto."), recorder(done, "type_text", "Ho scritto ciao.")])
    result = asyncio.run(brain.respond("apri spotify e scrivi nel blocco note ciao", VOICE))
    assert [name for name, _ in done] == ["open_app", "open_app", "type_text"]
    assert result.text == "Aperto. Ho scritto ciao."


def test_a_plan_that_is_one_step_goes_the_usual_way(settings):
    done = []
    brain, llm = make(settings, [
        plan(("manda a Luca il messaggio «compra il pane e passa da me»", False)),
        call("send_discord_message", {"name": "Luca", "message": "compra il pane e passa da me"}),
        say("Fatto, ho scritto a Luca."),
    ], [recorder(done, "send_discord_message", "Messaggio inviato.")])
    result = asyncio.run(brain.respond("manda a luca compra il pane e passa da me", VOICE))
    assert done == [("send_discord_message", {"name": "Luca", "message": "compra il pane e passa da me"})]
    assert result.text == "Fatto, ho scritto a Luca."
    assert llm.calls[1]["messages"][-1] == {"role": "user", "content": "manda a luca compra il pane e passa da me"}


def test_without_a_usable_plan_the_words_decide_the_steps(settings):
    brain, llm = make(settings, [say("non so")], [])
    steps = asyncio.run(brain._plan("apri discord e poi crea la cartella prova"))
    assert steps == [planner.Step("apri discord"), planner.Step("crea la cartella prova")]

    class OnThePC(FakeLLM):
        def chain(self):
            return ["local"]

    brain.llm = OnThePC([])
    assert asyncio.run(brain._plan("apri discord e crea la cartella prova")) == [
        planner.Step("apri discord"), planner.Step("crea la cartella prova")]
    assert brain.llm.calls == []


def test_after_a_failed_action_the_rest_of_the_reply_is_not_run(settings):
    done = []
    brain, llm = make(settings, [
        calls(("open_app", {"name": "Blocco note"}), ("type_text", {"name": "ciao"})),
        say("Il Blocco note non si apre."),
    ], [recorder(done, "open_app", fail="Non si apre."), recorder(done, "type_text")])
    result = asyncio.run(brain.respond("fammi una nota", VOICE))
    assert [name for name, _ in done] == ["open_app"]
    skipped = json.loads(llm.calls[1]["messages"][-1]["content"])
    assert skipped["ok"] is False and skipped["errore"].startswith("Non eseguito")
    assert result.text == "Il Blocco note non si apre."


def test_a_message_is_never_sent_twice_in_one_request(settings):
    done = []
    args = {"name": "Marco", "message": "ciao"}
    brain, llm = make(settings, [
        call("send_discord_message", args, "a"),
        call("send_discord_message", args, "b"),
        say("Fatto."),
    ], [recorder(done, "send_discord_message", "Inviato a Marco.")])
    asyncio.run(brain.respond("saluta marco", VOICE))
    assert len(done) == 1
    again = json.loads(llm.calls[2]["messages"][-1]["content"])
    assert again == {"ok": True, "esito": "Già fatto poco fa: Inviato a Marco."}


def test_actions_on_the_screen_take_turns_across_requests():
    active, peak = [0], [0]

    async def drive(ctx, args):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.05)
        active[0] -= 1
        return "fatto"

    registry = ToolRegistry()
    registry.add(Tool("type_text", "scrive", params(), drive, uses_screen=True))
    registry.add(Tool("press_keys", "preme", params(), drive, uses_screen=True))
    registry.add(Tool("weather", "meteo", params(), drive))

    async def main():
        voice = ToolContext(channel=VOICE, services=None)
        telegram = ToolContext(channel=Channel("telegram", "1"), services=None)
        await asyncio.gather(registry.invoke("type_text", {}, voice), registry.invoke("press_keys", {}, telegram))
        screen_peak = peak[0]
        peak[0] = 0
        await asyncio.gather(registry.invoke("type_text", {}, voice), registry.invoke("weather", {}, telegram))
        return screen_peak, peak[0]

    screen_peak, mixed_peak = asyncio.run(main())
    assert screen_peak == 1
    assert mixed_peak == 2


def test_open_app_waits_until_the_window_is_ready_and_in_front(monkeypatch):
    from ressy.tools import apps, winapi

    window = winapi.Window(hwnd=42, title="Discord", pid=7, class_name="Chrome_WidgetWin_1")
    polls = {"n": 0}

    def matching(name):
        polls["n"] += 1
        return [window] if polls["n"] > 3 else []

    focused, launched = [], []
    monkeypatch.setattr(apps, "_matching_windows", matching)
    monkeypatch.setattr(apps, "launch", lambda entry: launched.append(entry.name))
    monkeypatch.setattr(apps.time, "sleep", lambda s: None)
    monkeypatch.setattr(winapi, "window_size", lambda hwnd: (1200, 800))
    monkeypatch.setattr(winapi, "foreground_window", lambda: 1)
    monkeypatch.setattr(winapi, "focus_window", lambda hwnd: focused.append(hwnd) or True)
    monkeypatch.setattr(winapi, "input_desktop_available", lambda: True)
    monkeypatch.setattr(winapi, "wait_input_idle", lambda pid, timeout=5.0: True)

    class Index:
        def find(self, name):
            return apps.AppEntry("Discord", "com.squirrel.Discord.Discord"), []

    ctx = ToolContext(channel=VOICE, services=type("S", (), {"apps": Index()})())
    assert apps.open_app(ctx, {"name": "discord"}) == "Ho aperto Discord: è pronto."
    assert launched == ["Discord"] and focused == [42]


def test_open_app_does_not_wait_forever_for_a_window(monkeypatch):
    from ressy.tools import apps, winapi

    clock = {"t": 0.0}
    monkeypatch.setattr(apps, "_matching_windows", lambda name: [])
    monkeypatch.setattr(apps, "launch", lambda entry: None)
    monkeypatch.setattr(apps.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(apps.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(winapi, "foreground_window", lambda: 1)

    class Index:
        def find(self, name):
            return apps.AppEntry("Tray Tool", "Vendor.TrayTool"), []

    ctx = ToolContext(channel=VOICE, services=type("S", (), {"apps": Index()})())
    started = time.perf_counter()
    assert "non si vede ancora" in apps.open_app(ctx, {"name": "tray tool"})
    assert clock["t"] >= apps.READY_TIMEOUT_S and time.perf_counter() - started < 2


@pytest.fixture()
def home(tmp_path, monkeypatch):
    from ressy.tools import more, winapi

    names = {"desktop": "Desktop", "documents": "Documents", "downloads": "Downloads", "pictures": "Pictures",
             "music": "Music", "videos": "Videos"}
    for name in names.values():
        (tmp_path / name).mkdir()
    monkeypatch.setattr(more, "_home", lambda: tmp_path.resolve())
    monkeypatch.setattr(winapi, "known_folder", lambda key: str(tmp_path / names[key]) if key in names else None)
    return tmp_path.resolve()


def _act(**args):
    from ressy.tools import more

    return more.file_action(ToolContext(channel=VOICE, services=None), args)


def test_files_can_be_renamed_moved_copied_and_binned(home, monkeypatch):
    from ressy.tools import more, winapi

    desktop = home / "Desktop"
    (desktop / "note.txt").write_text("ciao", encoding="utf-8")
    assert _act(action="rename", name="note.txt", new_name="lista") == "Ho rinominato il file note.txt in lista.txt."
    assert _act(action="copy", name="lista.txt", destination="documenti") == \
        "Ho copiato il file lista.txt in Documenti."
    assert (home / "Documents" / "lista.txt").read_text(encoding="utf-8") == "ciao"
    assert _act(action="move", name="lista.txt", destination="Desktop/scuola") == \
        f"Ho spostato il file lista.txt in Desktop{more.os.sep}scuola."
    assert (desktop / "scuola" / "lista.txt").exists() and not (desktop / "lista.txt").exists()

    binned = []
    monkeypatch.setattr(winapi, "recycle", lambda path: binned.append(path) or True)
    assert "nel Cestino" in _act(action="delete", name="scuola")
    assert binned == [str(desktop / "scuola")]


def test_the_main_folders_and_missing_files_are_refused(home):
    with pytest.raises(ToolError, match="cartelle principali"):
        _act(action="delete", name="Documents", folder=str(home))
    with pytest.raises(ToolError, match="Non trovo"):
        _act(action="delete", name="non-esiste.txt")
    (home / "Desktop" / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ToolError, match="nuovo nome"):
        _act(action="rename", name="a.txt", new_name="b/c")
    with pytest.raises(ToolError, match="quale cartella"):
        _act(action="move", name="a.txt")


def test_create_folder_says_where_as_one_would(home):
    from ressy.tools import more

    ctx = ToolContext(channel=VOICE, services=None)
    assert more.create_folder(ctx, {"name": "compiti"}) == "La cartella compiti è stata creata sul Desktop."
    assert more.create_folder(ctx, {"name": "compiti"}) == "La cartella compiti esisteva già sul Desktop."


def test_wait_for_seconds_or_for_an_app(monkeypatch):
    from ressy.tools import apps, more, winapi

    slept = []
    monkeypatch.setattr(more.time, "sleep", lambda s: slept.append(s))
    ctx = ToolContext(channel=VOICE, services=None)
    assert more.wait(ctx, {"seconds": 3}) == "Ho aspettato 3 secondi."
    assert more.wait(ctx, {"seconds": 999}) == "Ho aspettato 120 secondi."
    assert slept == [3.0, 120.0]

    ready = winapi.Window(hwnd=5, title="Discord", pid=9, class_name="x")
    monkeypatch.setattr(apps, "wait_until_ready", lambda name, before, timeout: ready if name == "Discord" else None)
    assert more.wait(ctx, {"app": "Discord"}) == "Discord è aperto e pronto."
    with pytest.raises(ToolError, match="non si è aperto"):
        more.wait(ctx, {"app": "Pippo", "seconds": 5})
    with pytest.raises(ToolError, match="Quanti secondi"):
        more.wait(ctx, {})
