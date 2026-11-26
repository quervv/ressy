from __future__ import annotations

import asyncio
import base64

import numpy as np
import pytest

from ressy.audio.mic import FRAME, RATE
from ressy.brain.agent import TurnResult
from ressy.core import controller as ctl
from ressy.speech.stt import Transcript
from ressy.tools.registry import Attachment


class RecordingUi:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, *args))

        return record

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def last(self, name):
        return next((c for c in reversed(self.calls) if c[0] == name), None)


class FakeSTT:
    def __init__(self) -> None:
        self.next_text = ""
        self.files: list[tuple[bytes, str]] = []

    def preload(self) -> None:
        pass

    async def transcribe_pcm(self, pcm, rate, *, lenient=False):
        self.lenient = lenient
        return Transcript(self.next_text) if self.next_text else Transcript("", "empty")

    async def transcribe_file(self, data, mime):
        self.files.append((data, mime))
        return Transcript(self.next_text)


class FakeSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text, on_chunk=None):
        self.spoken.append(text)
        return True

    async def voice_note(self, text):
        return b"ID3fake", "audio/mpeg"

    def interrupt(self):
        pass


class FakeBrain:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    async def respond(self, text, channel, on_tool=None, on_step=None):
        self.requests.append((text, channel.kind))
        if "screenshot" in text:
            return TurnResult(text="Ecco lo schermo.", images=[Attachment(b"\xff\xd8jpeg", "s.jpg", "image/jpeg")])
        return TurnResult(text=f"Risposta a: {text}")


class FakeMic:
    def __init__(self) -> None:
        self.running = False
        self.starts = 0

    def start(self, on_frame=None):
        self.running = True
        self.starts += 1

    def stop(self):
        self.running = False


class FakePlayer:
    playing = False

    def play(self, *args, **kwargs):
        return True

    def stop(self):
        pass


@pytest.fixture()
def make(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(ctl, "app_dir", lambda: tmp_path)
    settings.remote_enabled = False
    settings.sounds_enabled = True

    def build():
        ui = RecordingUi()
        c = ctl.Controller(settings, ui=ui)
        c.stt, c.speaker, c.brain = FakeSTT(), FakeSpeaker(), FakeBrain()
        c.mic, c.cue_player, c.player = FakeMic(), FakePlayer(), FakePlayer()
        c.apps.ensure_fresh = lambda *a: None
        return c, ui

    return build


def speech(seconds=1.0):
    return (np.random.default_rng(1).standard_normal(int(RATE * seconds)) * 3000).astype(np.int16)


async def drain(c):
    await asyncio.wait_for(c._queue.join(), timeout=5)
    await asyncio.sleep(0)


def run(c, scenario):
    async def main():
        await c._start_async()
        try:
            await scenario()
        finally:
            for task in c._tasks:
                task.cancel()
            c.reminders.stop()

    asyncio.run(main())


def test_hold_k_and_wake_phrase_wakes_and_greets(make):
    c, ui = make()

    async def scenario():
        c.stt.next_text = "Ressy, sveglia!"
        c._on_hold()
        assert c.mic.running and c._mode == "ptt" and c.state == ctl.HEARING
        for i in range(0, RATE, FRAME):
            c._on_frame(speech()[i : i + FRAME], -20.0)
        c._on_release()
        await drain(c)
        assert c.awake and c.state == ctl.LISTENING
        assert "show_hud" in ui.names()
        assert len(c.speaker.spoken) == 1 and c.brain.requests == []
        assert c._mode == "vad"

    run(c, scenario)


def test_without_wake_phrase_ressy_keeps_sleeping(make):
    c, ui = make()

    async def scenario():
        c.stt.next_text = "passami il sale"
        c._enqueue(ctl.VoiceJob(speech(), c._gen, was_asleep=True, push_to_talk=True))
        await drain(c)
        assert not c.awake and c.state == ctl.ASLEEP
        assert c.speaker.spoken == [] and "show_hud" not in ui.names()

    run(c, scenario)


def test_wake_phrase_with_command_runs_it(make):
    c, ui = make()

    async def scenario():
        c.stt.next_text = "Ressy sveglia, apri Spotify"
        c._enqueue(ctl.VoiceJob(speech(), c._gen, was_asleep=True, push_to_talk=True))
        await drain(c)
        assert c.awake
        assert c.brain.requests == [("apri Spotify", "voice")]
        assert c.speaker.spoken == ["Risposta a: apri Spotify"]

    run(c, scenario)


def test_conversation_then_sleep_command(make):
    c, ui = make()

    async def scenario():
        c._enqueue(ctl.WakeJob())
        await drain(c)
        c.stt.next_text = "che ore sono?"
        c._on_vad_utterance(speech())
        assert c._mode == "off" and c.state == ctl.THINKING
        await drain(c)
        assert c.brain.requests[-1] == ("che ore sono?", "voice")
        assert ("user_line", "che ore sono?", True) in ui.calls
        c.stt.next_text = "Ressy, vai a dormire"
        c._on_vad_utterance(speech())
        await drain(c)
        assert not c.awake and c.state == ctl.ASLEEP
        assert "hide_hud" in ui.names()
        assert len(c.brain.requests) == 1

    run(c, scenario)


def test_stale_voice_turn_is_dropped(make):
    c, ui = make()

    async def scenario():
        c._enqueue(ctl.WakeJob())
        await drain(c)
        c.stt.next_text = "apri chrome"
        old_gen = c._gen
        c._sleep_now()
        c._enqueue(ctl.VoiceJob(speech(), old_gen, was_asleep=False, push_to_talk=False))
        await drain(c)
        assert c.brain.requests == []

    run(c, scenario)


def test_remote_text_command_with_voice_and_images(make):
    c, ui = make()

    async def scenario():
        reply = await c._on_remote_command(
            {"id": "r1", "source": {"platform": "telegram", "user_id": "7", "display": "@mario"},
             "text": "fammi uno screenshot", "want_voice": True}
        )
        assert reply["ok"] is True and reply["text"] == "Ecco lo schermo."
        assert base64.b64decode(reply["voice"]["data"]) == b"ID3fake" and reply["voice"]["mime"] == "audio/mpeg"
        assert reply["images"][0]["mime"] == "image/jpeg"
        assert c.brain.requests == [("fammi uno screenshot", "telegram")]
        assert ui.last("toast")[1].startswith("Comando da Telegram")

    run(c, scenario)


def test_remote_voice_note_is_transcribed(make):
    c, ui = make()

    async def scenario():
        c.stt.next_text = "apri discord"
        audio = {"mime": "audio/ogg", "data": base64.b64encode(b"OggS....").decode()}
        reply = await c._on_remote_command(
            {"id": "r2", "source": {"platform": "discord", "user_id": "9"}, "audio": audio, "want_voice": False}
        )
        assert reply["ok"] and reply["transcript"] == "apri discord" and "voice" not in reply
        assert c.stt.files == [(b"OggS....", "audio/ogg")]

    run(c, scenario)


def test_remote_command_without_groq_key(make, settings):
    settings.groq_api_key = ""
    c, ui = make()

    async def scenario():
        reply = await c._on_remote_command({"id": "r3", "source": {"platform": "telegram", "user_id": "1"},
                                            "text": "ciao"})
        assert reply["ok"] is False and "chiave API" in reply["text"]
        assert c.brain.requests == []

    run(c, scenario)


def test_hold_without_key_opens_settings(make, settings):
    settings.groq_api_key = ""
    c, ui = make()

    async def scenario():
        c._on_hold()
        assert ui.last("open_settings") is not None and c._mode == "off" and not c.mic.running

    run(c, scenario)


def test_short_hold_is_ignored(make):
    c, ui = make()

    async def scenario():
        c._on_hold()
        c._on_frame(speech(0.03)[:FRAME], -20.0)
        c._on_release()
        await asyncio.sleep(0.05)
        assert c._queue.empty() and c.state == ctl.ASLEEP

    run(c, scenario)
