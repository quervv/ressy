from __future__ import annotations

import pytest

from ressy.speech.stt import Transcript, clean_transcription, extension_for
from ressy.speech.textnorm import normalize, token_spans
from ressy.speech.tts import clean_for_speech, split_for_speech
from ressy.speech.wake import is_sleep_command, match_wake

PHRASES = ["ressy sveglia", "sveglia ressy", "ressy svegliati"]


@pytest.mark.parametrize(
    ("heard", "remainder"),
    [
        ("Ressy, sveglia!", ""),
        ("Ressi sveglia.", ""),
        ("Ressie, svegliati!", ""),
        ("Sveglia, Ressy!", ""),
        ("Rexy sveglia, apri Spotify per favore.", "apri Spotify per favore"),
        ("Ehi Ressy sveglia: scrivi a Marco che arrivo alle 10:30", "scrivi a Marco che arrivo alle 10:30"),
    ],
)
def test_wake_phrases_match_with_whisper_spellings(heard, remainder):
    match = match_wake(heard, PHRASES)
    assert match.matched
    assert match.remainder == remainder


@pytest.mark.parametrize("heard", ["apri discord", "Ressy", "Jessica sveglia", "sveglia", "", "che ore sono"])
def test_other_speech_does_not_wake(heard):
    assert not match_wake(heard, PHRASES).matched


def test_custom_wake_phrase():
    assert match_wake("Ok computer, accenditi", ["computer accenditi"]).matched


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ressy, vai a dormire.", True),
        ("Grazie, è tutto!", True),
        ("basta così", True),
        ("dormi ressy", True),
        ("apri chrome", False),
        ("vai a dormire tra un'ora e ricordami di chiamare", False),
    ],
)
def test_sleep_commands(text, expected):
    assert is_sleep_command(text) is expected


def test_normalize_and_spans_keep_offsets():
    text = "Perché l'app è 10:30?"
    assert normalize(text) == "perche l app e 10 30"
    spans = token_spans(text)
    assert [text[s:e] for _, s, e in spans] == ["Perché", "l", "app", "è", "10", "30"]


def _seg(text, no_speech=0.05, logprob=-0.2, compression=1.2):
    return {"text": text, "no_speech_prob": no_speech, "avg_logprob": logprob, "compression_ratio": compression}


def test_transcript_keeps_confident_speech():
    result = clean_transcription({"text": "apri spotify", "segments": [_seg(" Apri Spotify.")]})
    assert result == Transcript("Apri Spotify.")
    assert result.ok


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "Sottotitoli creati dalla comunità Amara.org", "segments": [_seg("Sottotitoli creati dalla comunità Amara.org")]},
        {"text": "Grazie per la visione!", "segments": [_seg("Grazie per la visione!")]},
        {"text": "Grazie.", "segments": [_seg("Grazie.", no_speech=0.5, logprob=-0.5)]},
        {"text": "ciao", "segments": [_seg("ciao", no_speech=0.9, logprob=-1.0)]},
        {"text": "la la la", "segments": [_seg("la la la la la la", compression=3.1)]},
        {"text": "   ", "segments": []},
    ],
)
def test_transcript_rejects_hallucinations(payload):
    assert not clean_transcription(payload).ok


def test_confident_thanks_is_kept():
    assert clean_transcription({"segments": [_seg("Grazie!", no_speech=0.01, logprob=-0.1)]}).ok


def test_extension_for_voice_notes():
    assert extension_for("audio/ogg; codecs=opus") == "ogg"
    assert extension_for("audio/mpeg") == "mp3"
    assert extension_for("") == "ogg"


def test_clean_for_speech_strips_markdown_links_and_emoji():
    text = "**Fatto!** 🎉\n- apri [questo link](https://example.com)\n- poi `npm run`\nVedi https://ressy.top"
    spoken = clean_for_speech(text)
    assert "*" not in spoken and "🎉" not in spoken and "https" not in spoken and "`" not in spoken
    assert "Fatto!" in spoken and "questo link" in spoken


def test_clean_for_speech_cuts_at_a_sentence():
    text = "Prima frase completa. " * 80
    spoken = clean_for_speech(text, max_chars=300)
    assert len(spoken) <= 300
    assert spoken.endswith(".")


def test_split_for_speech_starts_short():
    text = ". ".join(f"Questa è la frase numero {i}" for i in range(12)) + "."
    chunks = split_for_speech(text)
    assert len(chunks) > 2
    assert len(chunks[0]) <= 120
    assert " ".join(chunks).replace("  ", " ") == text
