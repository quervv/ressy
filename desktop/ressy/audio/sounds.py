from __future__ import annotations

import functools

import numpy as np

RATE = 24000


def _env(n: int, attack_s: float, decay_s: float) -> np.ndarray:
    t = np.arange(n) / RATE
    attack = np.clip(t / max(attack_s, 1e-4), 0.0, 1.0)
    return attack * np.exp(-t / max(decay_s, 1e-4))


def _note(freq: float, dur: float, *, vol: float = 0.18, decay: float = 0.09) -> np.ndarray:
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    wave = np.sin(2 * np.pi * freq * t) + 0.22 * np.sin(2 * np.pi * 2 * freq * t)
    return vol * wave * _env(n, 0.004, decay)


def _silence(dur: float) -> np.ndarray:
    return np.zeros(int(RATE * dur))


def _to_pcm(x: np.ndarray) -> np.ndarray:
    fade = min(240, x.size)
    if fade:
        x = x.copy()
        x[-fade:] *= np.linspace(1.0, 0.0, fade)
    return np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16)


@functools.lru_cache(maxsize=None)
def thock() -> np.ndarray:
    n = int(RATE * 0.07)
    t = np.arange(n) / RATE
    body = 0.22 * np.sin(2 * np.pi * 165 * t) * _env(n, 0.001, 0.018)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    kernel = np.ones(6) / 6.0
    click = 0.10 * np.convolve(noise, kernel, mode="same") * _env(n, 0.0005, 0.004)
    return _to_pcm(body + click)


@functools.lru_cache(maxsize=None)
def wake() -> np.ndarray:
    return _to_pcm(np.concatenate([_note(659.25, 0.09, decay=0.05), _note(987.77, 0.22, decay=0.1)]))


@functools.lru_cache(maxsize=None)
def sleep() -> np.ndarray:
    return _to_pcm(np.concatenate([_note(987.77, 0.09, decay=0.05), _note(659.25, 0.24, decay=0.11)]))


@functools.lru_cache(maxsize=None)
def done() -> np.ndarray:
    return _to_pcm(_note(880.0, 0.16, vol=0.12, decay=0.06))


@functools.lru_cache(maxsize=None)
def error() -> np.ndarray:
    return _to_pcm(
        np.concatenate([_note(392.0, 0.11, vol=0.16, decay=0.06), _silence(0.02), _note(311.13, 0.2, vol=0.16)])
    )


@functools.lru_cache(maxsize=None)
def remote() -> np.ndarray:
    return _to_pcm(np.concatenate([_note(1174.66, 0.07, vol=0.1, decay=0.03), _note(1174.66, 0.14, vol=0.1)]))


CUES = {"thock": thock, "wake": wake, "sleep": sleep, "done": done, "error": error, "remote": remote}


def cue(name: str) -> np.ndarray:
    return CUES[name]()
