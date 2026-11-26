from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from ressy import paths, system_integration
from ressy.brain import local_llm, planner, quick
from ressy.config import Settings
from ressy.core import hotkey
from ressy.speech import textnorm, tts
from ressy.tools import apps, platform_os, video
from ressy.tools.registry import Channel, ToolContext


class _DummyUiWithUpload:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requested = False

    def request_video_upload(self, req: dict) -> None:
        self.requested = True
        req["result"]["payload"] = self.payload
        req["event"].set()


class _FakeApps:
    def find(self, name: str):
        return None, []


def _ctx(ui=None) -> ToolContext:
    services = SimpleNamespace(apps=_FakeApps(), settings=Settings(), stt=None, ui=ui)
    return ToolContext(channel=Channel("voice", "Voice"), services=services)


def _fake_clip(path: Path) -> Path:
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
    return path


def test_edit_video_asks_for_upload_when_no_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(video, "_open_editor_app", lambda ctx, ed, p: True)
    result = video.edit_video(_ctx(ui=None), {"editor": "capcut"})
    assert "CapCut" in result
    assert "Carica" in result or "Upload" in result


def test_edit_video_ui_upload_builds_capcut_draft(monkeypatch, tmp_path: Path) -> None:
    clip = _fake_clip(tmp_path / "gameplay.mp4")
    drafts = tmp_path / "capcut_drafts"
    drafts.mkdir()
    monkeypatch.setenv("RESSY_CAPCUT_DRAFTS", str(drafts))
    monkeypatch.setattr(video, "videos_dir", lambda: tmp_path / "Videos")
    monkeypatch.setattr(video, "probe_clip", lambda p: video.ClipInfo(p, 9.0, 1080, 1920, 30.0, True))
    monkeypatch.setattr(video, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(video, "_open_editor_app", lambda ctx, ed, p: True)

    ui = _DummyUiWithUpload({
        "files": [str(clip)],
        "editor": "capcut",
        "style": "viral",
        "aspect_ratio": "9:16",
        "title": "MOMENTO EPICO",
        "phrases": ["GUARDA QUI", "CLUTCH FINALE"],
        "render_preview": False,
    })
    res = video.edit_video(_ctx(ui=ui), {})
    assert ui.requested
    assert "CapCut" in res

    root_meta = drafts / "root_meta_info.json"
    assert root_meta.is_file()
    rm = json.loads(root_meta.read_text(encoding="utf-8"))
    assert len(rm["all_draft_store"]) == 1
    draft_dir = Path(rm["all_draft_store"][0]["draft_fold_path"])
    content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
    meta = json.loads((draft_dir / "draft_meta_info.json").read_text(encoding="utf-8"))

    assert content["canvas_config"]["width"] == 1080
    assert content["canvas_config"]["height"] == 1920
    tracks_by_type = [t["type"] for t in content["tracks"]]
    assert "video" in tracks_by_type
    assert "text" in tracks_by_type
    texts = [json.loads(m["content"])["text"] for m in content["materials"]["texts"]]
    assert "MOMENTO EPICO" in texts
    assert "CLUTCH FINALE" in texts
    assert meta["draft_materials"][0]["value"]


def test_edit_video_davinci_resolve_creates_fcpxml_and_calls_api(monkeypatch, tmp_path: Path) -> None:
    clip = _fake_clip(tmp_path / "vlog.mp4")
    monkeypatch.setattr(video, "videos_dir", lambda: tmp_path / "Videos")
    monkeypatch.setattr(video, "probe_clip", lambda p: video.ClipInfo(p, 6.0, 1920, 1080, 30.0, False))
    monkeypatch.setattr(video, "find_ffmpeg", lambda: None)

    calls: list[str] = []

    class FakeMediaPool:
        def ImportMedia(self, files):
            calls.append(f"import:{len(files)}")
            return files

        def ImportTimelineFromFile(self, path):
            calls.append(f"fcpxml:{Path(path).name}")
            return object()

    class FakeProject:
        def GetMediaPool(self):
            return FakeMediaPool()

    class FakePM:
        def CreateProject(self, name):
            calls.append(f"project:{name}")
            return FakeProject()

    class FakeResolve:
        def GetProjectManager(self):
            return FakePM()

        def OpenPage(self, page):
            calls.append(f"page:{page}")

    monkeypatch.setattr(video, "_connect_davinci_resolve", lambda launch_if_closed=True: FakeResolve())
    res = video.edit_video(_ctx(), {
        "editor": "davinci",
        "files": [str(clip)],
        "aspect_ratio": "16:9",
        "title": "INTRO TOP",
        "phrases": ["PRIMO PASSO", "RISULTATO FINALE"],
    })
    assert "DaVinci Resolve" in res
    assert any(c.startswith("project:Ressy_") for c in calls)
    assert "fcpxml:timeline.fcpxml" in calls
    assert "page:edit" in calls

    bundles = list((tmp_path / "Videos" / "Ressy Edits").iterdir())
    assert len(bundles) == 1
    xml_path = bundles[0] / "timeline.fcpxml"
    assert xml_path.is_file()
    tree = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    assert tree.tag == "fcpxml"
    assert (bundles[0] / "background.png").is_file()
    assert (bundles[0] / "captions.srt").is_file()
    assert (bundles[0] / "phrase_01.png").is_file()


def test_video_quick_and_planner_and_textnorm() -> None:
    assert "CapCut" in textnorm.fix_spoken_text("apri cap cut e poi edita")
    assert "DaVinci Resolve" in textnorm.fix_spoken_text("usa da vinci")

    q1 = quick.match("edita un video con capcut")
    assert q1 is not None and q1.tool == "edit_video" and q1.args["editor"] == "capcut"
    q2 = quick.match("edit a video on davinci resolve")
    assert q2 is not None and q2.tool == "edit_video" and q2.args["editor"] == "davinci"

    steps = planner.fallback_plan("apri capcut e edita un video")
    assert len(steps) == 2
    assert "CapCut" in steps[1].text


def test_cross_platform_paths_and_autostart(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".xdg"))
    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.app_dir() == tmp_path / ".xdg" / "Ressy"

    system_integration.set_autostart(True)
    assert system_integration.autostart_enabled()
    desktop_entry = tmp_path / ".xdg" / "autostart" / "ressy.desktop"
    assert "[Desktop Entry]" in desktop_entry.read_text(encoding="utf-8")
    system_integration.set_autostart(False)
    assert not system_integration.autostart_enabled()

    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.app_dir() == tmp_path / "Library" / "Application Support" / "Ressy"
    assert paths.user_folder("videos") == tmp_path / "Movies"
    system_integration.set_autostart(True)
    assert system_integration.autostart_enabled()
    plist = tmp_path / "Library" / "LaunchAgents" / "top.ressy.desktop.plist"
    assert "<string>top.ressy.desktop</string>" in plist.read_text(encoding="utf-8")
    system_integration.set_autostart(False)
    assert not system_integration.autostart_enabled()


def test_local_llm_tar_gz_runtime_install(monkeypatch, tmp_path: Path) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = b"#!/bin/sh\necho ok\n"
        info = tarfile.TarInfo("build/bin/llama-server")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    raw = buf.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    archive = tmp_path / "llama.tar.gz"
    archive.write_bytes(raw)
    target = tmp_path / "runtime"
    target.mkdir()

    monkeypatch.setattr(local_llm, "_runtime_spec", lambda: ("https://example/llama.tar.gz", digest, 10, "llama-server"))
    out = local_llm.install_runtime(archive, target)
    assert (out / "llama-server").is_file()
    assert (out / local_llm._READY_MARK).is_file()


def test_unix_app_discovery_and_shell_safety(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(platform_os, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_os, "IS_MACOS", False)
    monkeypatch.setattr(platform_os, "IS_LINUX", True)
    apps_dir = tmp_path / ".local/share/applications"
    apps_dir.mkdir(parents=True)
    (apps_dir / "spotify.desktop").write_text("[Desktop Entry]\nName=Spotify\nExec=spotify %U\nType=Application\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(apps.sys, "platform", "linux")

    found = dict(platform_os.find_unix_apps())
    assert found.get("Spotify") == "spotify"
    with pytest.raises(ValueError):
        platform_os.run_unix_shell("rm -rf /", tmp_path)


def test_unix_tts_and_hotkey_translation(monkeypatch) -> None:
    from pynput.keyboard import Key, KeyCode

    assert hotkey._pynput_to_vk(KeyCode.from_char("k")) == 0x4B
    assert hotkey._pynput_to_vk(Key.f8) == 0x77

    from ressy.audio.player import AudioPlayer

    s = Settings(language="en", tts_engine="sapi")
    speaker = tts.Speaker(s, AudioPlayer(lambda: None))
    called: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        called.append(list(cmd))
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"RIFFdemo")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert speaker.sapi_wav("Hello world") == b"RIFFdemo"
    assert called and called[0][0] == "say"


def test_requirements_guards_winrt_for_windows_only() -> None:
    req = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    winrt_lines = [line.strip() for line in req.splitlines() if "winrt-" in line and not line.strip().startswith("#")]
    assert winrt_lines
    for line in winrt_lines:
        assert 'sys_platform == "win32"' in line


def test_video_upload_dialog_populates_and_accepts(tmp_path: Path) -> None:
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ressy.ui.video_dialog import VideoUploadDialog

    _app = QApplication.instance() or QApplication([])
    clip = _fake_clip(tmp_path / "sample.mp4")
    dlg = VideoUploadDialog({"files": [str(clip)], "editor": "capcut", "title": "HOOK TEST", "phrases": ["UNO", "DUE"]})
    assert dlg.file_list.count() == 1
    dlg._accept()
    assert dlg.result_payload is not None
    assert dlg.result_payload["files"] == [str(clip)]
    assert dlg.result_payload["editor"] == "capcut"
    assert dlg.result_payload["phrases"] == ["UNO", "DUE"]
    dlg.close()
