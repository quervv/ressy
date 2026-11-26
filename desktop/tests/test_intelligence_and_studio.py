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
    assert audio_tracks and any(t["segments"][0]["volume"] == 0.20 for t in audio_tracks)

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
    assert dlg.result_payload["caption_mode"] == "word"
    assert dlg.result_payload["kinetic_broll"] is True
    assert dlg.result_payload["auto_captions"] is True
    assert dlg.result_payload["progress_bar"] is True
    assert dlg.result_payload["render_preview"] is True

    dlg2 = VideoUploadDialog(defaults={
        "files": [str(mp4)],
        "caption_mode": "phrase",
        "kinetic_broll": False,
    })
    dlg2._accept()
    assert dlg2.result_payload is not None
    assert dlg2.result_payload["caption_mode"] == "phrase"
    assert dlg2.result_payload["kinetic_broll"] is False


def test_tiktok_pro_editing_primitives_and_ffmpeg_filtergraph(monkeypatch, tmp_path: Path):
    import wave
    import numpy as np

    vert = video.ClipInfo(tmp_path / "v.mp4", 12.0, 576, 1024, 30.0, True)
    wide = video.ClipInfo(tmp_path / "w.mp4", 6.0, 1920, 1080, 30.0, True)
    assert video._aspect_matches(vert, (1080, 1920)) is True
    assert video._aspect_matches(wide, (1080, 1920)) is False

    chunks = video._chunk_words_into_timeline(
        [{"text": "nuovo browser per vinted", "start": 1.0, "end": 3.0}],
        uppercase=False,
        max_words_per_chunk=2,
    )
    assert len(chunks) == 2
    assert chunks[0]["text"] == "nuovo browser"
    assert chunks[1]["text"] == "per vinted"
    assert chunks[0]["start_s"] >= 1.0 and chunks[1]["start_s"] + chunks[1]["duration_s"] <= 3.05

    from ressy.speech.local_stt import LocalWhisper

    class FakeModel:
        def transcribe(self, audio, **_kw):
            return [SimpleNamespace(text=" ciao mondo ", t0=120, t1=360)]

    lw = LocalWhisper()
    monkeypatch.setattr(lw, "_load", lambda _name: FakeModel())
    out_stt = lw.transcribe(np.zeros(16000, dtype=np.float32), name="base-q5_1", language="it", prompt="")
    assert out_stt["segments"][0]["start"] == pytest.approx(1.2, abs=0.01)
    assert out_stt["segments"][0]["end"] == pytest.approx(3.6, abs=0.01)

    speech_phrases = [
        {"text": "Nuovo Browser / per Vinted", "start_s": 0.08, "duration_s": 2.4, "is_hook": True, "mode": "hook_neon", "color": "#00E5FF", "pill": "#111318"},
        *[{"text": w, "start_s": 2.1 + i * 1.1, "duration_s": 0.9, "is_hook": False, "mode": "word", "color": "#FFFFFF", "pill": "#111318"}
          for i, w in enumerate(["ecco come", "crei nuovi", "profili sicuri", "senza blocco", "tutto veloce", "risultato finale"])],
    ]
    slides, badges = video._plan_broll_elements(speech_phrases, 12.0, enabled=True)
    assert slides and badges
    assert any(s["variant"] == "warp_grid" for s in slides)

    hook_png = tmp_path / "hook.png"
    pov_png = tmp_path / "pov.png"
    word_png = tmp_path / "word.png"
    slide_warp = tmp_path / "slide_w.png"
    slide_glow = tmp_path / "slide_g.png"
    badge_png = tmp_path / "badge.png"
    sfx_wav = tmp_path / "sfx.wav"

    video._render_phrase_card(hook_png, speech_phrases[0], (540, 960))
    video._render_phrase_card(pov_png, {"text": "POV: EDIT PRO", "is_hook": True, "mode": "hook_pov", "color": "#111111", "pill": "#FFFFFF"}, (540, 960))
    video._render_phrase_card(word_png, {"text": "questo browser", "is_hook": False, "mode": "word", "color": "#FFFFFF", "pill": "#111111"}, (540, 960))
    video._render_cutaway_slide(slide_warp, "PROFILI", "profili sicuri", "browser", (540, 960), variant="warp_grid")
    video._render_cutaway_slide(slide_glow, "VELOCE", "tutto veloce", "spark", (540, 960), variant="radial_glow")
    video._render_floating_badge(badge_png, "browser", "browser", (540, 960))
    assert video._synthesize_sfx_wav(sfx_wav, 8.0, [("sub", 0.1), ("whoosh", 2.1), ("pop", 4.5)]) is True

    for p in (hook_png, pov_png, word_png, slide_warp, slide_glow, badge_png):
        assert p.is_file() and Image.open(p).size == (540, 960)
    with wave.open(str(sfx_wav), "rb") as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        assert wf.getnchannels() == 2 and wf.getframerate() == 44100
        assert int(np.max(np.abs(pcm))) > 0

    vert.path.write_bytes(b"\x00" * 64)
    bg_png = tmp_path / "bg.png"
    Image.new("RGB", (64, 64), (10, 10, 10)).save(bg_png)
    cmd = video._build_ffmpeg_cmd(
        "ffmpeg",
        tmp_path / "out.mp4",
        [vert],
        bg_png,
        [(speech_phrases[0], hook_png)],
        None,
        (1080, 1920),
        ["zoom_punch"],
        color_grade="vivid",
        broll_pngs=[(slides[0], slide_warp)],
        badge_pngs=[(badges[0], badge_png)],
        sfx_path=sfx_wav,
        bg_mode="auto",
    )
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "-itsoffset" not in cmd
    assert "repeatlast=1:enable=" in fg
    assert "split=" in fg and "concat=n=" in fg
    assert "vibrance=" in fg and "eq=" not in fg
    assert "[bg]" not in fg


def test_custom_ai_server_config_client_and_routing(monkeypatch):
    import httpx
    from ressy.config import Settings, normalize_custom_url
    from ressy.brain.providers import CustomServerClient, LLMRouter
    from ressy.speech import local_stt

    monkeypatch.setattr(local_stt, "is_downloaded", lambda _m: True)

    assert normalize_custom_url("") == ""
    assert normalize_custom_url("127.0.0.1:8088") == "http://127.0.0.1:8088/v1"
    assert normalize_custom_url("https://my-gpu.example.com/v1/") == "https://my-gpu.example.com/v1"
    assert normalize_custom_url("http://192.168.1.42:11434") == "http://192.168.1.42:11434/v1"

    s = Settings(llm_provider="custom", custom_base_url="", custom_api_key="")
    assert s.brain_problem != ""

    s2 = Settings(llm_provider="custom", custom_base_url="127.0.0.1:8088", custom_api_key="")
    s2._sanitize()
    assert s2.custom_base_url == "http://127.0.0.1:8088/v1"
    assert "custom" in s2.providers_with_keys()
    assert s2.brain_problem == ""

    seen_auth: list[str] = []
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("authorization", ""))
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen2.5-14b-custom"}]})
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            seen_models.append(body.get("model", ""))
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "Risposta dal tuo server AI", "tool_calls": None}}],
                "model": body.get("model"),
            })
        return httpx.Response(404)

    async def run_client():
        client_nokey = CustomServerClient(lambda: "", lambda: "http://localhost:8088")
        client_nokey._client_base = "http://localhost:8088/v1"
        client_nokey._client = httpx.AsyncClient(
            base_url="http://localhost:8088/v1",
            transport=httpx.MockTransport(handler),
        )
        try:
            models = await client_nokey.list_models()
            assert models == ["qwen2.5-14b-custom"]
            res = await client_nokey.chat([{"role": "user", "content": "ciao"}], models=[""])
            assert res.message["content"] == "Risposta dal tuo server AI"
            assert seen_models[-1] == "qwen2.5-14b-custom"
            assert seen_auth[-1] == ""

            client_key = CustomServerClient(lambda: "sec-tok-99", lambda: "http://localhost:8088/v1")
            client_key._client_base = "http://localhost:8088/v1"
            client_key._client = httpx.AsyncClient(
                base_url="http://localhost:8088/v1",
                transport=httpx.MockTransport(handler),
            )
            await client_key.chat([{"role": "user", "content": "ciao"}], models=["llama3.3"])
            assert seen_auth[-1] == "Bearer sec-tok-99"
            assert seen_models[-1] == "llama3.3"
            await client_key.aclose()
        finally:
            await client_nokey.aclose()

    asyncio.run(run_client())

    from ressy.brain import providers

    router = LLMRouter(s2)
    assert router.client() is router.custom
    assert router.name == "Il tuo server AI"
    assert providers._CLIENTS["custom"] is CustomServerClient


def test_self_hosted_model_server_runner_and_brain_setup_ui(qapp, monkeypatch, tmp_path: Path):
    from ressy.brain import local_llm, model_server
    from ressy.config import Settings
    from ressy.ui.brain_setup import BrainSetup

    model_file = tmp_path / "qwen-custom.gguf"
    model_file.write_bytes(b"GGUF" + b"\x00" * 32)
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"MZ")

    cfg = model_server.ModelServerConfig(
        model_path=str(model_file),
        host="0.0.0.0",
        port=8099,
        api_key="ressy-secret",
    )
    cmd = model_server.build_launch_command(exe, cfg)
    assert "--host" in cmd and "0.0.0.0" in cmd
    assert "--port" in cmd and "8099" in cmd
    assert "--api-key" in cmd and "ressy-secret" in cmd
    assert "--jinja" in cmd

    urls = model_server.server_urls(8099, expose_lan=True)
    assert urls[0] == "http://127.0.0.1:8099/v1"

    class FakeProc:
        def __init__(self):
            self.alive = True
            self.terminated = False

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.terminated = True
            self.alive = False

        def wait(self, timeout=None):
            return 0

    fake_proc = FakeProc()
    monkeypatch.setattr(local_llm, "runtime_ready", lambda: True)
    monkeypatch.setattr(local_llm, "server_exe", lambda: exe)
    monkeypatch.setattr(model_server.subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr(model_server, "check_health", lambda url, api_key="", timeout=2.0: (True, ["qwen-custom"]))

    runner = model_server.ModelServerRunner()
    started = runner.start(cfg, wait_s=5.0)
    assert started == ["qwen-custom"]
    assert runner.running is True
    runner.stop()
    assert runner.running is False and fake_proc.terminated is True

    setup = BrainSetup()
    assert "custom" in setup.cards.cards
    assert len(setup.cards.cards) == 6
    setup.load("custom", {"custom": "ressy-secret"}, {"custom": "qwen-custom"}, "", "127.0.0.1:8099")
    vals = setup.values()
    assert vals["llm_provider"] == "custom"
    assert vals["custom_base_url"] == "http://127.0.0.1:8099/v1"
    assert vals["custom_api_key"] == "ressy-secret"
    assert vals["custom_model"] == "qwen-custom"


def test_discord_anti_screenshot_loop_quick_paths_and_router_fixes(monkeypatch, settings, tmp_path: Path):
    import httpx
    from ressy.brain import quick
    from ressy.tools import build_registry, discord
    from ressy.tools.registry import NeedsInputError

    q1 = quick.match("scrivi a Karpa su discord ciao da ressy")
    assert q1 is not None and q1.tool == "send_discord_message"
    assert q1.args == {"recipient": "Karpa", "message": "ciao da ressy", "kind": "user"}

    q2 = quick.match("manda nel canale generale su discord: arrivo tra poco")
    assert q2 is not None and q2.tool == "send_discord_message"
    assert q2.args == {"recipient": "generale", "message": "arrivo tra poco", "kind": "channel"}

    q3 = quick.match("scrivi su discord a Marco ehi come va")
    assert q3 is not None and q3.tool == "send_discord_message"
    assert q3.args["recipient"] == "Marco" and q3.args["message"] == "ehi come va"

    assert quick.match("Scrivi a Marco ciao") is None

    assert discord._clean_name("il canale generale") == "generale"
    assert "epok" in discord._queries("vocale epok", "channel")
    assert discord.chat_confirmed("Amici - Discord", "epok | Server - Discord", "epok", "channel")

    shots_taken = []
    monkeypatch.setattr("ressy.tools.screen.grab", lambda *a, **kw: shots_taken.append(1))
    reg = build_registry()
    ctx = ToolContext(channel=VOICE, services=SimpleNamespace(apps=None, settings=settings, stt=None))
    raw_err = asyncio.run(reg.invoke("send_discord_message", {"message": "ciao", "kind": "user"}, ctx))
    err_data = json.loads(raw_err)
    assert err_data["ok"] is False
    assert err_data.get("needs_input") is True
    assert "A chi devo scrivere" in err_data["errore"]
    assert shots_taken == [] and ctx.images == []

    class LoopingIfAllowedLLM:
        def __init__(self):
            self.calls = 0

        def chain(self):
            return ["local"]

        async def chat(self, messages, *, models=None, tools=None, tool_choice=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return ChatResult({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "c1", "type": "function", "function": {
                        "name": "send_discord_message",
                        "arguments": json.dumps({"message": "ciao", "kind": "user"}),
                    }}],
                }, model="qwen2.5-3b")
            raise AssertionError("Brain must ask user directly instead of spinning extra tool rounds")

    llm_loop = LoopingIfAllowedLLM()
    brain = Brain(settings, llm_loop, reg, services=SimpleNamespace(apps=None, settings=settings, stt=None))
    brain_res = asyncio.run(brain.respond("manda un messaggio su discord", VOICE))
    assert llm_loop.calls == 1
    assert "A chi devo scrivere" in brain_res.text

    sent_schemas: list[list[str]] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        branches = json["response_format"]["json_schema"]["schema"]["anyOf"]
        sent_schemas.append([b["properties"]["azione"]["const"] for b in branches])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"azione":"rispondi","argomenti":{},"risposta":"ok"}'}}]})

    monkeypatch.setattr(local_llm.httpx, "post", fake_post)

    class StubSrv:
        base_url = "http://127.0.0.1:1"
        key = "k"

        def ensure(self, _n):
            pass

    lc = local_llm.LocalLLMClient(lambda: "qwen2.5-3b", server=StubSrv())
    all_tools = reg.schemas(VOICE)
    asyncio.run(lc.chat([{"role": "user", "content": "manda un messaggio su discord"}], tools=all_tools))
    assert "take_screenshot" not in sent_schemas[-1]
    asyncio.run(lc.chat([{"role": "user", "content": "fammi uno screenshot"}], tools=all_tools))
    assert "take_screenshot" in sent_schemas[-1]

    assert local_llm.result_reply([
        {"role": "user", "content": "scrivi su discord"},
        {"role": "assistant", "tool_calls": [{"id": "a", "function": {"name": "send_discord_message", "arguments": "{}"}}]},
        {"role": "tool", "name": "send_discord_message", "content": json.dumps({"ok": False, "errore": "A chi devo scrivere su Discord?", "needs_input": True})},
    ]) == "A chi devo scrivere su Discord?"

    blocked = local_llm._repeat_guard(
        {"role": "assistant", "content": "", "tool_calls": [{"id": "3", "function": {"name": "open_app", "arguments": '{"name": "Discord"}'}}]},
        [
            {"role": "user", "content": "scrivi su discord"},
            {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "open_app", "arguments": '{"name": "Discord"}'}}]},
            {"role": "tool", "tool_call_id": "1", "name": "open_app", "content": '{"ok": true, "esito": "Ho avviato Discord."}'},
            {"role": "assistant", "tool_calls": [{"id": "2", "function": {"name": "send_discord_message", "arguments": '{"message": "x"}'}}]},
            {"role": "tool", "tool_call_id": "2", "name": "send_discord_message", "content": '{"ok": false, "errore": "A chi?"}'},
        ],
    )
    assert "tool_calls" not in blocked

    settings.llm_provider = "groq"
    settings.groq_api_key = "gsk_test"
    router = LLMRouter(settings)
    seen_groq_models: list[str] = []

    class RecordingGroq:
        usage = None

        async def chat(self, messages, *, models, **kwargs):
            seen_groq_models.extend(models)
            return ChatResult({"role": "assistant", "content": "ok"}, models[0])

    router.groq = RecordingGroq()
    asyncio.run(router.chat([{"role": "user", "content": "ciao"}], models=["qwen2.5-1.5b"]))
    assert "qwen2.5-1.5b" not in seen_groq_models
    assert seen_groq_models[0] == settings.llm_model
