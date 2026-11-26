from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ressy.brain import local_llm
from ressy.brain.agent import Brain
from ressy.brain.groq import ChatResult
from ressy.brain.providers import LLMRouter
from ressy.core import controller as ctl
from ressy.speech import textnorm
from ressy.tools import apps, more, video, web
from ressy.tools.registry import Channel, Tool, ToolContext, ToolRegistry, params
from ressy.ui.video_dialog import VideoUploadDialog
from ressy.ui.video_studio import VideoStudioWindow

VOICE = Channel("voice")


class _ScriptLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def chat(self, messages, *, models, tools=None, tool_choice=None, **kwargs):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        return ChatResult(message=self.script.pop(0), model=models[0])


def _say(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _call(name: str, args: dict, cid: str = "c1") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}],
    }


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_brain_isolates_unrelated_new_request_and_keeps_followups(settings):
    settings.quick_commands = False
    ran: list[tuple[str, dict]] = []

    def do_open(ctx, args):
        ran.append(("open_app", args))
        return "Ho aperto Spotify."

    def do_weather(ctx, args):
        ran.append(("weather", args))
        return f"A {args.get('city', 'Roma')} oggi ci sono 22°C."

    reg = ToolRegistry()
    reg.extend([
        Tool("open_app", "Apri app", params({"name": {"type": "string"}}, ["name"]), do_open),
        Tool("weather", "Meteo", params({"city": {"type": "string"}}), do_weather),
    ])
    llm = _ScriptLLM([
        _call("open_app", {"name": "Spotify"}, "c1"),
        _say("Ho aperto Spotify."),
        _call("weather", {"city": "Roma"}, "c2"),
        _say("A Roma oggi ci sono 22°C."),
        _call("weather", {"city": "Roma"}, "c3"),
        _say("Domani sole a Roma, 24°C."),
    ])
    brain = Brain(settings, llm, reg, services=None)

    r1 = asyncio.run(brain.respond("apri Spotify", VOICE))
    assert "Spotify" in r1.text

    r2 = asyncio.run(brain.respond("che tempo fa a Roma", VOICE))
    assert "22°C" in r2.text
    turn2_user_assistant = [m for m in llm.calls[-2]["messages"] if m["role"] in ("user", "assistant")]
    assert not any("Spotify" in str(m.get("content") or "") for m in turn2_user_assistant)

    r3 = asyncio.run(brain.respond("e domani?", VOICE))
    assert "24°C" in r3.text
    turn3_contents = " ".join(str(m.get("content") or "") for m in llm.calls[-2]["messages"])
    assert "Roma" in turn3_contents


def test_brain_nudges_out_of_lazy_refusal(settings):
    settings.quick_commands = False
    reg = ToolRegistry()
    reg.extend([
        Tool(
            "run_python",
            "Esegue Python",
            params({"code": {"type": "string"}}, ["code"]),
            lambda ctx, a: "file_creato.png",
        )
    ])
    llm = _ScriptLLM([
        _say("Mi dispiace, non posso creare grafici direttamente."),
        _call("run_python", {"code": "print('ok')"}, "c1"),
        _say("Ho creato il grafico file_creato.png per te."),
    ])
    brain = Brain(settings, llm, reg, services=None)
    res = asyncio.run(brain.respond("creami un grafico a barre sul desktop", VOICE))
    assert "Ho creato il grafico" in res.text
    assert res.performed
    assert len(llm.calls) == 3


def test_local_llm_avoids_rispondi_kv_lockin_and_allows_error_recovery():
    messages = [
        {"role": "system", "content": "SYS_CLOUD"},
        {"role": "user", "content": "che ore sono"},
        {"role": "assistant", "content": "Sono le 18:00."},
        {"role": "user", "content": "apri la calcolatrice"},
    ]
    chat = local_llm.to_local_messages(messages, "SYS_LOCAL")
    assert not any('"azione": "rispondi"' in str(m.get("content") or "") for m in chat)
    assert chat[-1]["content"].strip().endswith("apri la calcolatrice")

    fail_turn = [
        {"role": "user", "content": "apri calcolatrice"},
        _call("open_app", {"name": "calcolatice"}),
        {"role": "tool", "name": "open_app", "content": json.dumps({"ok": False, "errore": "Non trovata. Forse: Calcolatrice?"})},
    ]
    assert local_llm.result_reply(fail_turn) is None

    retry_diff = local_llm._repeat_guard(_call("open_app", {"name": "Calcolatrice"}), fail_turn)
    assert "tool_calls" in retry_diff
    retry_same = local_llm._repeat_guard(_call("open_app", {"name": "calcolatice"}), fail_turn)
    assert "tool_calls" not in retry_same


def test_controller_hold_during_thinking_bumps_generation_and_sleep_clears_memory(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(ctl, "app_dir", lambda: tmp_path)
    settings.remote_enabled = False
    settings.sounds_enabled = False

    class MemoryBrain:
        def __init__(self):
            self.calls = []
            self.cleared = []
            self.memory = SimpleNamespace(clear=lambda key: self.cleared.append(key))

        async def respond(self, text, channel, **kwargs):
            self.calls.append(text)
            return ctl.TurnResult(text="Risposta")

    c = ctl.Controller(settings, ui=SimpleNamespace(**{k: (lambda *a: None) for k in ("state", "show_hud", "hide_hud", "ressy_line", "user_line", "status", "toast", "open_settings", "remote_state", "links", "linked", "pair_code", "pair_error")}))
    c.brain = MemoryBrain()
    c.speaker = SimpleNamespace(speak=lambda *a, **k: asyncio.sleep(0), interrupt=lambda: None)
    c.mic = SimpleNamespace(running=False, start=lambda *a: None, stop=lambda: None)
    c.player = SimpleNamespace(playing=False, play=lambda *a, **k: True, stop=lambda: None)
    c.cue_player = c.player

    async def scenario():
        await c._start_async()
        try:
            c.awake = True
            c.state = ctl.THINKING
            before_gen = c._gen
            c._on_hold()
            assert c._gen > before_gen
            await c._sleep_with_goodbye()
            assert ctl.VOICE.key in c.brain.cleared
        finally:
            if c._ptt_deadline is not None:
                c._ptt_deadline.cancel()
            for task in c._tasks:
                task.cancel()
            c.reminders.stop()

    asyncio.run(scenario())


def test_phonetic_app_matching_and_web_fallback(monkeypatch, tmp_path: Path):
    assert "Fortnite" in textnorm.fix_spoken_text("apri fortreta")
    idx = apps.AppIndex(tmp_path / "apps.json")
    idx._apps = [
        apps.AppEntry("Fortnite", "com.epicgames.launcher://apps/Fortnite"),
        apps.AppEntry("Foto", "Microsoft.Windows.Photos_8wekyb3d8bbwe!App"),
        apps.AppEntry("Discord", "com.squirrel.Discord.Discord"),
    ]
    idx._loaded_at = 9e12
    entry, _ = idx.find("fortreta")
    assert entry is not None and entry.name == "Fortnite"
    phon_entry, _ = idx.find("diskort")
    assert phon_entry is not None and phon_entry.name == "Discord"
    assert idx.find("photoshop")[0] is None

    opened_urls: list[str] = []
    monkeypatch.setattr("ressy.tools.web._open", lambda url: opened_urls.append(url))
    ctx = ToolContext(channel=VOICE, services=SimpleNamespace(apps=idx))
    res = apps.open_app(ctx, {"name": "youtube"})
    assert "youtube" in res.lower() and opened_urls == ["https://www.youtube.com"]


def test_more_resolve_path_leading_folder_and_find_files_full_path(monkeypatch, tmp_path: Path):
    dl = tmp_path / "Downloads"
    desk = tmp_path / "Desktop"
    dl.mkdir()
    desk.mkdir()
    target = dl / "appunti_roma.txt"
    target.write_text("ciao", encoding="utf-8")

    monkeypatch.setattr(more, "_home", lambda: tmp_path)
    monkeypatch.setattr(more, "user_folder", lambda k: dl if k == "downloads" else desk)
    if os.name == "nt":
        monkeypatch.setattr(more.winapi, "known_folder", lambda k: str(dl if k == "downloads" else desk))

    resolved = more.resolve_path("Download/appunti_roma.txt")
    assert resolved == target.resolve()

    found = more.find_files(ToolContext(channel=VOICE, services=None), {"query": "appunti_roma", "folder": str(dl)})
    assert str(target.resolve()) in found or "appunti_roma.txt" in found


def test_router_web_answer_uses_keyless_fallback_on_local(settings, monkeypatch):
    settings.llm_provider = "local"
    settings.groq_api_key = ""
    router = LLMRouter(settings)

    async def fake_fallback(q: str, *, language: str = "it") -> str:
        return f"Risultato live per: {q}"

    monkeypatch.setattr(web, "fallback_web_answer", fake_fallback)
    out = asyncio.run(router.web_answer("prezzo oro oggi", language="it"))
    assert "Risultato live per: prezzo oro oggi" in out


def test_video_resolve_media_handles_typos_and_fake_dirs(monkeypatch, tmp_path: Path):
    vids = tmp_path / "Videos"
    vids.mkdir()
    real = vids / "partita_epica.mp4"
    real.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    monkeypatch.setattr(video, "user_folder", lambda k: vids if k == "videos" else tmp_path / k)
    assert video._resolve_media_file(r"C:\Users\utente\Download\partita_epica.mpp4") == real.resolve()


def test_video_pro_capcut_ffmpeg_and_live_studio_stream(monkeypatch, tmp_path: Path):
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    bgm = tmp_path / "beat.mp3"
    for f in (clip1, clip2, bgm):
        f.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    drafts = tmp_path / "capcut_drafts"
    drafts.mkdir()
    monkeypatch.setenv("RESSY_CAPCUT_DRAFTS", str(drafts))
    monkeypatch.setattr(video, "videos_dir", lambda: tmp_path / "Videos")
    monkeypatch.setattr(video, "probe_clip", lambda p: video.ClipInfo(p, 4.0, 1080, 1920, 30.0, True))
    monkeypatch.setattr(video, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(video, "_open_editor_app", lambda ctx, ed, p: True)

    events: list[dict] = []
    statuses: list[str] = []
    ui = SimpleNamespace(
        update_video_studio=lambda ev: events.append(dict(ev)),
        status=lambda s: statuses.append(s),
    )
    ctx = ToolContext(channel=VOICE, services=SimpleNamespace(ui=ui, apps=None, settings=None, stt=None))

    res = video.edit_video(
        ctx,
        {
            "editor": "capcut",
            "files": [str(clip1), str(clip2)],
            "music": str(bgm),
            "style": "cinematic",
            "color_grade": "teal_orange",
            "transition": "zoom_whip",
            "title": "VIAGGIO TOP",
            "phrases": ["MOMENTO UNO", "GRAN FINALE"],
            "render_preview": False,
        },
    )
    assert "CapCut" in res
    kinds = [e["type"] for e in events]
    assert kinds[0] == "init"
    assert "stage" in kinds and kinds[-1] == "done"
    assert any(e.get("preview_path") and Path(e["preview_path"]).is_file() for e in events)
    assert statuses

    rm = json.loads((drafts / "root_meta_info.json").read_text(encoding="utf-8"))
    draft_dir = Path(rm["all_draft_store"][0]["draft_fold_path"])
    dc = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
    assert dc["ressy_profile"] == {"color_grade": "teal_orange", "transition": "zoom_whip"}
    assert dc["materials"]["transitions"]
    assert dc["materials"]["audio_fades"]
    fg_segs = dc["tracks"][1]["segments"]
    assert any(s.get("common_keyframes") for s in fg_segs)
    audio_tracks = [t for t in dc["tracks"] if t["type"] == "audio"]
    assert audio_tracks and audio_tracks[0]["segments"][0]["volume"] == 0.20

    c_info = [video.ClipInfo(clip1, 4.0, 1080, 1920, 30.0, True), video.ClipInfo(clip2, 4.0, 1080, 1920, 30.0, True)]
    bg = draft_dir.parent / "bg.png"
    Image.new("RGB", (64, 64), (10, 10, 10)).save(bg)
    cmd = video._build_ffmpeg_cmd(
        "ffmpeg",
        tmp_path / "out.mp4",
        c_info,
        bg,
        [],
        bgm,
        (1080, 1920),
        ["zoom_punch"],
        color_grade="teal_orange",
        transition="zoom_whip",
    )
    fgraph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=slideleft" in fgraph
    assert "acrossfade=" in fgraph
    assert "colorbalance=" in fgraph
    assert "amix=inputs=2" in fgraph
    assert "fade=t=in" in fgraph


def test_video_studio_window_and_dialog_ui(qapp, tmp_path: Path):
    preview = tmp_path / "frame.png"
    Image.new("RGB", (320, 480), (60, 40, 120)).save(preview)
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"fake")

    win = VideoStudioWindow()
    win.apply_event({
        "type": "init",
        "project_name": "Ressy_Demo",
        "project_dir": str(tmp_path),
        "editor": "CapCut",
        "style": "viral",
        "aspect_ratio": "9:16",
        "duration": 8.0,
        "message": "Avvio test",
        "show": False,
    })
    assert win.progress.value() > 0
    win.apply_event({
        "type": "stage",
        "stage": "effects",
        "done_stages": ["analyze", "assets", "captions"],
        "progress": 65,
        "playhead": 4.2,
        "preview_path": str(preview),
        "preview_label": "Compositing live",
        "transitions": [4.0],
        "tracks": [
            {"id": "V3", "label": "V3 TITOLI", "items": [{"start": 0.1, "end": 2.5, "text": "HOOK"}]},
            {"id": "V1", "label": "V1 VIDEO", "items": [{"start": 0.0, "end": 4.0, "text": "clip1", "keyframes": True}]},
        ],
    })
    assert win.progress.value() == 65
    assert win.timeline._playhead >= 0.0
    win.apply_event({"type": "done", "output_mp4": str(mp4), "project_dir": str(tmp_path), "message": "Pronto!"})
    assert win.progress.value() == 100
    assert win.open_mp4_btn.isEnabled()
    assert win.open_dir_btn.isEnabled()

    dlg = VideoUploadDialog(defaults={
        "files": [str(mp4)],
        "editor": "capcut",
        "transition": "flash",
        "color_grade": "teal_orange",
        "title": "TEST PRO",
        "phrases": ["A", "B"],
    })
    dlg._accept()
    assert dlg.result_payload is not None
    assert dlg.result_payload["transition"] == "flash"
    assert dlg.result_payload["color_grade"] == "teal_orange"
    assert dlg.result_payload["auto_captions"] is True
    assert dlg.result_payload["progress_bar"] is True
    assert dlg.result_payload["render_preview"] is True
