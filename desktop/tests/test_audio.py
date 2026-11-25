from __future__ import annotations

import numpy as np

from ressy.audio import sounds
from ressy.audio.meter import Meter
from ressy.audio.mic import FRAME, RATE
from ressy.audio.pcm import StreamResampler, from_wav, resample, to_wav
from ressy.audio.vad import PushToTalkBuffer, UtteranceDetector


def tone(freq: float, seconds: float, amp: float = 0.3, rate: int = RATE) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (amp * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def test_wav_roundtrip():
    pcm = tone(440, 0.1)
    out, rate = from_wav(to_wav(pcm, RATE))
    assert rate == RATE and np.array_equal(out, pcm)


def test_stream_resampler_matches_batch_length():
    src = tone(300, 1.0, rate=48000)
    stream = StreamResampler(48000, 16000)
    chunks = [stream.process(src[i : i + 1440]) for i in range(0, src.size, 1440)]
    out = np.concatenate(chunks)
    assert abs(out.size - 16000) <= 2
    assert abs(resample(src, 48000, 16000).size - 16000) <= 1


def test_meter_bands_follow_the_pitch():
    meter = Meter()
    level_low, bands_low = meter.analyse(tone(150, 0.03), RATE)
    level_high, bands_high = meter.analyse(tone(3000, 0.03), RATE)
    assert level_low > 0.5 and level_high > 0.5
    assert int(np.argmax(bands_low)) < int(np.argmax(bands_high))
    silent_level, silent_bands = meter.analyse(np.zeros(FRAME, dtype=np.int16), RATE)
    assert silent_level == 0.0 and float(silent_bands.max()) == 0.0


def test_meter_read_respects_delay_and_goes_quiet():
    meter = Meter()
    meter.push(tone(440, 0.03), RATE, delay=10.0)
    level, _ = meter.read()
    assert level == 0.0
    meter.clear()
    meter.push(tone(440, 0.03), RATE)
    assert meter.read()[0] > 0.5


def _frames(pcm: np.ndarray):
    for i in range(0, pcm.size - FRAME + 1, FRAME):
        frame = pcm[i : i + FRAME]
        x = frame.astype(np.float32) / 32768
        rms = float(np.sqrt(np.mean(x * x)))
        yield frame, 20 * np.log10(rms) if rms > 1e-6 else -120.0


def test_utterance_detector_energy_path():
    events = []
    det = UtteranceDetector(lambda: events.append("start"), lambda pcm: events.append(pcm.size),
                            on_discard=lambda: events.append("discard"))
    det._vad = None
    quiet = np.zeros(RATE, dtype=np.int16)
    speech = tone(220, 1.0, amp=0.2)
    for frame, db in _frames(np.concatenate([quiet, speech, quiet])):
        det.process(frame, db)
    assert events[0] == "start"
    assert isinstance(events[1], int) and RATE * 0.9 < events[1] < RATE * 1.8

    events.clear()
    blip = tone(220, 0.2, amp=0.2)
    for frame, db in _frames(np.concatenate([quiet, blip, quiet])):
        det.process(frame, db)
    assert events == ["start", "discard"]


def test_push_to_talk_buffer():
    buf = PushToTalkBuffer(max_seconds=1)
    buf.add(np.ones(FRAME, dtype=np.int16))
    buf.begin()
    for _ in range(100):
        buf.add(np.ones(FRAME, dtype=np.int16))
    out = buf.end()
    assert out.size == (1000 // 30) * FRAME
    assert buf.end().size == 0


def test_cues_are_short_and_quiet():
    for name in sounds.CUES:
        pcm = sounds.cue(name)
        assert pcm.dtype == np.int16 and 0 < pcm.size < sounds.RATE
        assert np.abs(pcm).max() < 0.5 * 32767
