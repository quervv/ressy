from __future__ import annotations

import ast
import json
import string
from pathlib import Path

import pytest

from ressy import i18n
from ressy.i18n_en import EN

ROOT = Path(__file__).resolve().parents[1]


def _keys():
    for folder in ("ressy", "installer"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path.name == "i18n_en.py" or "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                        and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    yield node.args[0].value, f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"


def _fields(text: str) -> list[str]:
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name is not None)


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("it")


def test_every_text_has_an_english_version():
    missing = sorted({f"{where}: {key!r}" for key, where in _keys() if key not in EN})
    assert not missing, "\n".join(missing)


def test_translations_keep_the_placeholders_and_spacing():
    for key, text in EN.items():
        assert _fields(key) == _fields(text), key
        assert key.startswith(" ") == text.startswith(" "), key
        assert key.endswith((" ", "\n")) == text.endswith((" ", "\n")), key


def test_tr_follows_the_language(english):
    assert i18n.tr("Fatto.") == "Done."
    assert i18n.tr("Ho aperto {name}: è pronto.").format(name="Discord") == "I opened Discord: it's ready."
    assert i18n.tr("un testo che non c'è") == "un testo che non c'è"
    i18n.set_language("it")
    assert i18n.tr("Fatto.") == "Fatto."


def test_set_language_accepts_only_italian_and_english():
    i18n.set_language("en-GB")
    assert i18n.language() == "en"
    i18n.set_language("fr")
    assert i18n.language() == "it"


def test_saved_language_is_read_before_anything_else(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    monkeypatch.setattr("ressy.paths.config_path", lambda: config)
    assert i18n.saved_language() == ""
    config.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    assert i18n.saved_language() == "en"
    config.write_text(json.dumps({"language": "de"}), encoding="utf-8")
    assert i18n.saved_language() == ""
    config.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    try:
        assert i18n.apply_saved_language() == "en"
    finally:
        i18n.set_language("it")


def test_a_new_language_brings_its_voice_and_wake_phrases():
    from ressy.config import WAKE_DEFAULTS, Settings

    settings = Settings()
    settings.wake_phrases = [*WAKE_DEFAULTS["it"], "ehi computer"]
    settings.tts_voice = "it-IT-DiegoNeural"
    settings.use_language("en")
    assert settings.language == "en"
    assert settings.tts_voice == "en-US-AndrewMultilingualNeural"
    assert settings.wake_phrases == [*WAKE_DEFAULTS["en"], "ehi computer"]
    settings.use_language("it")
    assert settings.tts_voice == "it-IT-DiegoNeural"
    assert settings.wake_phrases == [*WAKE_DEFAULTS["it"], "ehi computer"]


def test_the_same_language_keeps_the_users_choices():
    from ressy.config import Settings

    settings = Settings()
    settings.wake_phrases = ["ressy sveglia"]
    settings.use_language("it")
    assert settings.wake_phrases == ["ressy sveglia"]
    assert settings.tts_voice == "it-IT-IsabellaNeural"


def test_english_wake_and_sleep_phrases():
    from ressy.config import WAKE_DEFAULTS
    from ressy.speech.wake import is_sleep_command, loose_wake, match_wake

    found = match_wake("Ressy, wake up! Open Spotify", WAKE_DEFAULTS["en"])
    assert found.matched and found.remainder == "Open Spotify"
    assert match_wake("Hey Ressy, what time is it?", WAKE_DEFAULTS["en"]).remainder == "what time is it"
    assert loose_wake("Ressi wake up open Discord").remainder == "open Discord"
    assert is_sleep_command("Thanks, that's all")
    assert is_sleep_command("Ressy, go back to sleep")


def test_system_prompt_in_english():
    from ressy.brain.prompts import system_prompt
    from ressy.tools.registry import Channel

    voice = system_prompt(user_name="Alex", device_name="Desk", channel=Channel("voice"), language="en")
    assert voice.startswith("You are Ressy, the personal assistant of Alex") and "read aloud" in voice
    remote = system_prompt(user_name="", device_name="Desk", channel=Channel("telegram", "1", "@alex"), language="en")
    assert "Channel: Telegram (@alex). The user is away from the PC" in remote
    assert "Sei Ressy" in system_prompt(user_name="", device_name="Desk", channel=Channel("voice"))


def test_the_ai_on_the_pc_is_told_in_english():
    from ressy.brain.local_llm import build_prompt

    prompt = build_prompt([], "Alex", "en")
    assert prompt.startswith("You are Ressy, the voice assistant on Alex's PC.") and "Examples:" in prompt
    assert build_prompt([], "Alex", "it").startswith("Sei Ressy")


def test_everyday_commands_in_english(english):
    from ressy.brain import quick

    assert quick.match("What’s the weather like?").tool == "weather"
    assert quick.match("what's the weather like in London").args == {"city": "London"}
    assert quick.match("Open time.is in the browser").args == {"url": "time.is"}
    assert quick.match("play lofi on youtube").args == {"query": "lofi"}
    assert quick.match("how much is 6 times 7").answer == "That's 42."
    assert quick.match("hey Ressy, what time is it").answer.startswith("It's ")
    reminder = quick.match("remind me in half an hour to stretch")
    assert reminder.tool == "reminder" and reminder.args["minutes"] == 30 and reminder.args["text"] == "Stretch"
    assert quick.match("how much API do I have left?").special == "usage"


def test_tool_messages_in_english(english, tmp_path, monkeypatch):
    from ressy.tools import more

    monkeypatch.setattr(more, "_known_places", lambda: [(tmp_path, i18n.tr("sul Desktop"), i18n.tr("Desktop"))])
    assert more.where(tmp_path) == "on the Desktop"
    assert more.where(tmp_path / "school") == f"in Desktop{__import__('os').sep}school"


def test_restart_hands_over_to_a_new_ressy(monkeypatch):
    from ressy import system_integration

    started = []
    monkeypatch.setattr(system_integration.subprocess, "Popen", lambda command, **kw: started.append(command))
    assert system_integration.relaunch()
    command = started[0]
    assert command[-2] == "--after" and command[-1].isdigit()
