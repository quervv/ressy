from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ressy.audio.meter import Meter
from ressy.ui import logo, theme
from ressy.ui.bridge import UiBridge
from ressy.ui.hud import Hud, VoiceLines, clip_text
from ressy.ui.keys import key_name


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_voice_lines_rest_without_sound_and_follow_real_bands(qapp):
    lines = VoiceLines(theme.LEGEND, 52)
    silent = np.zeros(24, dtype=np.float32)
    for _ in range(30):
        assert lines.feed(silent) is False
    loud = np.linspace(1.0, 0.2, 24).astype(np.float32)
    assert lines.feed(loud) is True
    peak = lines._values.copy()
    assert peak.max() > 0.4
    assert peak[11] == peak[12]
    for _ in range(80):
        lines.feed(silent)
    assert float(lines._values.max()) == 0.0


def test_clip_text():
    assert clip_text("  ciao   mondo ", 20) == "ciao mondo"
    assert clip_text("uno due tre quattro cinque", 12) == "uno due tre…"


@pytest.mark.parametrize(
    ("vk", "text", "name"),
    [(0x4B, "k", "K"), (0x37, "7", "7"), (0x7B, "", "F12"), (0x13, "", "Pausa"), (0xC0, "ò", "Ò")],
)
def test_key_names(vk, text, name):
    assert key_name(vk, text) == name


def test_mark_svg_is_the_same_geometry():
    svg = logo.svg(backlight=True)
    assert svg.startswith("<svg") and 'viewBox="0 0 64 64"' in svg
    assert theme.ACCENT in svg and theme.BACKLIGHT in svg
    assert svg.count("<rect") == 6
    assert "<text" not in svg and "path" not in svg
    assert theme.BACKLIGHT not in logo.svg()
    assert theme.LILAC in logo.svg(two_tone=True)
    asleep = logo.svg(awake=False)
    assert asleep.count('height="8"') == 5

def _fake_controller(settings, listening: bool):
    return SimpleNamespace(
        settings=settings,
        remote=SimpleNamespace(state="offline"),
        player=SimpleNamespace(meter=Meter()),
        mic=SimpleNamespace(meter=Meter(), running=True),
        listening=listening,
        apply_settings=lambda **k: None,
        sleep=lambda: None,
    )


def _tone() -> np.ndarray:
    t = np.arange(480) / 16000
    return (0.3 * 32767 * np.sin(2 * np.pi * 300 * t)).astype(np.int16)


def test_hud_user_lines_only_move_while_ressy_listens(qapp, settings):
    for listening, expect_moving in ((False, False), (True, True)):
        ctrl = _fake_controller(settings, listening)
        hud = Hud(ctrl, UiBridge())
        ctrl.mic.meter.push(_tone(), 16000)
        hud._tick()
        assert (float(hud.user_lines._values.max()) > 0) is expect_moving
        hud.deleteLater()


def test_hud_state_vocabulary_and_presence(qapp, settings):
    settings.remote_enabled = True
    settings.telegram_token = "123456789:" + "A" * 35
    hud = Hud(_fake_controller(settings, True), UiBridge())
    for state, label in (("listening", "ASCOLTA"), ("thinking", "PENSA"), ("speaking", "PARLA")):
        hud.on_state(state)
        assert hud.state_legend.text() == label
    hud.on_remote_state("offline", "")
    assert not hud.mark.backlight and not hud.presence_legend.isHidden()
    hud.on_remote_state("online", "")
    assert hud.mark.backlight and hud.presence_legend.isHidden()
    hud.on_user_line("apri spotify", True)
    assert hud.user_label.text() == "«apri spotify»"
    hud.deleteLater()


def test_settings_dialog_saves_only_what_changed(qapp, settings):
    from ressy.ui.settings_dialog import SettingsDialog

    applied: list[dict] = []
    ctrl = SimpleNamespace(
        settings=settings,
        remote=SimpleNamespace(state="online", detail="", links=[]),
        hotkey=SimpleNamespace(enabled=True),
        apply_settings=lambda **k: applied.append(k),
        refresh_apps=lambda: None,
    )
    dialog = SettingsDialog(ctrl, UiBridge(), open_pairing=lambda: None)
    dialog._load()
    assert dialog._changes() == {"first_run_done": True}

    dialog.wake_phrases.setText(" , ")
    assert isinstance(dialog._changes(), str)
    dialog.wake_phrases.setText("Ressy Sveglia, ehi ressy")
    dialog.bot_setup.radios["server"].setChecked(True)
    dialog.bot_setup.server_url.setText("https://example.org")
    assert "ws://" in dialog._changes()
    dialog.bot_setup.radios["local"].setChecked(True)
    assert "token" in dialog._changes()
    dialog.bot_setup.tokens.telegram.setText("123456789:" + "A" * 35)
    remote = dialog._changes()
    assert remote["remote_enabled"] is True and remote["remote_mode"] == "local" if "remote_mode" in remote else remote["remote_enabled"]
    assert remote["telegram_token"].startswith("123456789:")
    dialog.bot_setup.radios["off"].setChecked(True)
    dialog.user_name.setText("Alex")
    changes = dialog._changes()
    assert changes == {"user_name": "Alex", "wake_phrases": ["ressy sveglia", "ehi ressy"], "first_run_done": True}
    dialog.deleteLater()


def test_config_with_bom_is_read(tmp_path):
    from ressy.config import Settings

    path = tmp_path / "config.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"remote_enabled": false}')
    assert Settings.load(path).remote_enabled is False


def test_mark_follows_state(qapp):
    from ressy.ui.hud import MarkWidget

    mark = MarkWidget()
    mark.set_state(mood="speaking")
    assert mark.awake
    mark.set_voice([0.0] * 24)
    assert mark._voice_target == [0.0] * 5
    mark.set_state(mood="asleep")
    assert not mark.awake and mark._voice_target == [1.0] * 5

def test_legacy_shared_server_is_dropped(tmp_path):
    from ressy.config import Settings

    path = tmp_path / "config.json"
    path.write_text('{"remote_enabled": true, "server_url": "wss://ressy.top/ws/agent"}', encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.server_url == "" and loaded.remote_enabled is False and not loaded.remote_ready


def test_token_shape_checks():
    from ressy.ui.bot_setup import check_server_url, check_token

    assert check_token("telegram", "123456789:" + "A" * 35) == ""
    assert check_token("telegram", "not a token")
    assert check_server_url("ws://192.168.1.10:8765/ws/agent") == ""
    assert check_server_url("http://x")


def test_bot_tokens_never_reach_the_logs():
    import logging

    from ressy.log import RedactFilter

    record = logging.LogRecord("x", 20, "", 0, "GET /bot123456789:" + "A" * 35 + "/getMe", None, None)
    RedactFilter().filter(record)
    assert "A" * 35 not in record.getMessage()


def test_brain_cards_keep_each_providers_key(qapp):
    from ressy.ui.brain_setup import BrainSetup

    brain = BrainSetup()
    brain.load("claude", {"groq": "gsk_a", "claude": "sk-ant-b", "gemini": ""}, {"claude": "claude-haiku-5-5"})
    assert brain.key.text() == "sk-ant-b" and brain.model.currentData() == "claude-haiku-5-5"
    brain.cards.set_value("gemini")
    assert brain.key.text() == "" and "Gemini" in brain.problem()
    brain.key.setText("AIza_c")
    brain._key_edited()
    brain.cards.set_value("groq")
    assert brain.key.text() == "gsk_a"
    values = brain.values()
    assert values["llm_provider"] == "groq"
    assert (values["groq_api_key"], values["anthropic_api_key"], values["gemini_api_key"]) == ("gsk_a", "sk-ant-b", "AIza_c")
    assert values["claude_model"] == "claude-haiku-5-5"
    brain.deleteLater()
