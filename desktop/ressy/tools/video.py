from __future__ import annotations

import asyncio
import datetime as dt
import difflib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from ..i18n import tr
from ..paths import user_folder, videos_dir
from . import platform_os
from .apps import launch
from .registry import Tool, ToolContext, ToolError, params

log = logging.getLogger("ressy.video")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
_AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")

_RATIOS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

_STYLE_PALETTES: dict[str, dict[str, Any]] = {
    "viral": {
        "bg": (16, 17, 24),
        "glow": (157, 107, 255),
        "accent": (77, 240, 181),
        "text_colors": ["#FFD447", "#FFFFFF", "#4DF0B5", "#FF5C8A", "#9D6BFF"],
        "pill_bg": "#15161EFF",
        "cut_s": 3.2,
        "phrases_it": ["GUARDA FINO ALLA FINE", "ECCO IL SEGRETO", "DETTAGLIO CHIAVE", "RISULTATO PAZZESCO", "SALVA QUESTO VIDEO"],
        "phrases_en": ["WATCH TILL THE END", "HERE IS THE SECRET", "GAME CHANGER", "INSANE RESULT", "SAVE THIS VIDEO"],
    },
    "cinematic": {
        "bg": (14, 15, 19),
        "glow": (220, 165, 90),
        "accent": (235, 225, 205),
        "text_colors": ["#F7F3EA", "#F3C878", "#FFFFFF", "#E2D5B8"],
        "pill_bg": "#111216CC",
        "cut_s": 4.8,
        "phrases_it": ["INIZIO DEL VIAGGIO", "OGNI DETTAGLIO CONTA", "L'ATMOSFERA GIUSTA", "FINALE"],
        "phrases_en": ["THE BEGINNING", "EVERY DETAIL MATTERS", "PURE ATMOSPHERE", "FINALE"],
    },
    "gaming": {
        "bg": (15, 12, 26),
        "glow": (130, 80, 255),
        "accent": (0, 245, 200),
        "text_colors": ["#00F5C8", "#FFD447", "#FF4D6D", "#FFFFFF"],
        "pill_bg": "#120E24EE",
        "cut_s": 2.6,
        "phrases_it": ["NON PUÒ ESSERE", "CLUTCH TOTALE", "GUARDA QUI", "GG ASSOLUTO"],
        "phrases_en": ["NO WAY", "INSANE CLUTCH", "LOOK AT THIS", "PURE GG"],
    },
    "vlog": {
        "bg": (22, 23, 28),
        "glow": (110, 150, 255),
        "accent": (255, 210, 120),
        "text_colors": ["#FFFFFF", "#FFE08A", "#A8C5FF"],
        "pill_bg": "#1C1D24E6",
        "cut_s": 4.0,
        "phrases_it": ["OGGI FACCIAMO COSÌ", "MOMENTO TOP", "COSA NE PENSI?"],
        "phrases_en": ["TODAY'S PLAN", "BEST MOMENT", "WHAT DO YOU THINK?"],
    },
    "minimal": {
        "bg": (20, 20, 22),
        "glow": (90, 95, 110),
        "accent": (235, 235, 235),
        "text_colors": ["#FFFFFF", "#E5E5E5"],
        "pill_bg": "#18181BE0",
        "cut_s": 5.0,
        "phrases_it": ["FOCUS", "PUNTO CHIAVE", "FATTO"],
        "phrases_en": ["FOCUS", "KEY POINT", "DONE"],
    },
}


@dataclass
class ClipInfo:
    path: Path
    duration_s: float
    width: int
    height: int
    fps: float
    has_audio: bool


def _find_capcut_exe() -> Path | None:
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "CapCut/Apps/CapCut.exe"
        if local.is_file():
            return local
    elif sys.platform == "darwin":
        mac = Path("/Applications/CapCut.app")
        if mac.exists():
            return mac
    return None


def capcut_drafts_dir() -> Path | None:
    env_dir = os.environ.get("RESSY_CAPCUT_DRAFTS")
    if env_dir:
        return Path(env_dir)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        return base / "CapCut/User Data/Projects/com.lveditor.draft"
    if sys.platform == "darwin":
        return Path.home() / "Movies/CapCut/User Data/Projects/com.lveditor.draft"
    return None


def _capcut_cache_dir() -> Path | None:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        p = base / "CapCut/User Data/Cache/effect"
        return p if p.is_dir() else None
    if sys.platform == "darwin":
        p = Path.home() / "Movies/CapCut/User Data/Cache/effect"
        return p if p.is_dir() else None
    return None


def _find_davinci_exe() -> Path | None:
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files (x86)"):
            exe = Path(root) / "Blackmagic Design/DaVinci Resolve/Resolve.exe"
            if exe.is_file():
                return exe
    elif sys.platform == "darwin":
        mac = Path("/Applications/DaVinci Resolve/DaVinci Resolve.app")
        if mac.exists():
            return mac
    else:
        linux = Path("/opt/resolve/bin/resolve")
        if linux.is_file():
            return linux
    return None


def _davinci_script_paths() -> tuple[str | None, str | None]:
    if sys.platform == "win32":
        mod = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting", "Modules")
        lib = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
        return (mod if os.path.isdir(mod) else None, lib if os.path.isfile(lib) else None)
    if sys.platform == "darwin":
        mod = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
        return (mod if os.path.isdir(mod) else None, lib if os.path.isfile(lib) else None)
    mod = "/opt/resolve/Developer/Scripting/Modules"
    lib = "/opt/resolve/libs/Fusion/fusionscript.so"
    return (mod if os.path.isdir(mod) else None, lib if os.path.isfile(lib) else None)


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    if sys.platform == "win32":
        cap_apps = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "CapCut/Apps"
        if cap_apps.is_dir():
            for match in sorted(cap_apps.glob("*/ffmpeg.exe"), reverse=True):
                if match.is_file():
                    return str(match)
    elif sys.platform == "darwin":
        cap_bin = Path("/Applications/CapCut.app/Contents/MacOS/ffmpeg")
        if cap_bin.is_file():
            return str(cap_bin)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def find_ffprobe() -> str | None:
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ff = find_ffmpeg()
    if ff:
        cand = Path(ff).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if cand.is_file():
            return str(cand)
    return None


def available_editors() -> dict[str, bool]:
    cap_exe = _find_capcut_exe()
    drafts = capcut_drafts_dir()
    return {
        "capcut": bool(cap_exe or (drafts and drafts.parent.exists())),
        "davinci": _find_davinci_exe() is not None,
    }


def _choose_editor(wanted: str) -> str:
    w = (wanted or "auto").strip().lower()
    if any(k in w for k in ("davinci", "resolve")):
        return "davinci"
    if "capcut" in w:
        return "capcut"
    avail = available_editors()
    if avail["capcut"]:
        return "capcut"
    if avail["davinci"]:
        return "davinci"
    return "davinci" if platform_os.IS_LINUX else "capcut"


_EXT_TYPOS = {
    ".mpp4": ".mp4",
    ".mpeg4": ".mp4",
    ".mp44": ".mp4",
    ".moov": ".mov",
    ".mkw": ".mkv",
    ".wbm": ".webm",
    ".m4vv": ".m4v",
}


def _iter_media_candidates(roots: list[Path], max_depth: int = 3) -> list[Path]:
    found: list[Path] = []
    exts = set(_VIDEO_EXTS + _AUDIO_EXTS)
    for root in roots:
        if not root.is_dir():
            continue
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            cur, depth = stack.pop()
            try:
                entries = list(cur.iterdir())
            except OSError:
                continue
            for entry in entries:
                name_low = entry.name.lower()
                if entry.is_file() and entry.suffix.lower() in exts:
                    found.append(entry)
                elif entry.is_dir() and depth < max_depth and not name_low.startswith((".", "$", "ressy edits")):
                    stack.append((entry, depth + 1))
    return found


def _recent_media_hint(limit: int = 5) -> str:
    roots = [
        user_folder("videos"),
        user_folder("downloads"),
        user_folder("desktop"),
        user_folder("documents"),
    ]
    vids = [p for p in _iter_media_candidates(roots, max_depth=2) if p.suffix.lower() in _VIDEO_EXTS]
    if not vids:
        return ""
    vids.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
    names = ", ".join(str(p) for p in vids[:limit])
    return tr("Video disponibili trovati: {names}.").format(names=names)


def _resolve_media_file(raw: str) -> Path | None:
    text = raw.strip().strip('"').strip("'")
    if not text:
        return None
    expanded = Path(os.path.expandvars(os.path.expanduser(text)))
    if expanded.is_file():
        return expanded.resolve()

    suf_low = expanded.suffix.lower()
    if suf_low in _EXT_TYPOS:
        fixed = expanded.with_suffix(_EXT_TYPOS[suf_low])
        if fixed.is_file():
            return fixed.resolve()

    roots = [
        user_folder("videos"),
        user_folder("downloads"),
        user_folder("desktop"),
        user_folder("documents"),
    ]
    base_name = Path(text).name
    cand_names = [text, base_name]
    b_suf = Path(base_name).suffix.lower()
    if b_suf in _EXT_TYPOS:
        fixed_name = str(Path(base_name).with_suffix(_EXT_TYPOS[b_suf]))
        cand_names.append(fixed_name)
    else:
        fixed_name = base_name

    for root in roots:
        if not root.is_dir():
            continue
        for cname in cand_names:
            direct = root / cname
            if direct.is_file():
                return direct.resolve()

    candidates = _iter_media_candidates(roots, max_depth=3)
    q_stem = Path(fixed_name).stem.lower()
    q_full = fixed_name.lower()
    best_path: Path | None = None
    best_score = 0.0
    for entry in candidates:
        e_full = entry.name.lower()
        e_stem = entry.stem.lower()
        if e_full == q_full:
            return entry.resolve()
        if q_stem and q_stem == e_stem:
            score = 0.96
        elif q_stem and len(q_stem) >= 3 and q_stem in e_stem:
            score = 0.86
        else:
            score = difflib.SequenceMatcher(None, q_stem or q_full, e_stem).ratio()
        if score > best_score:
            best_score = score
            best_path = entry
    if best_path is not None and best_score >= 0.72:
        return best_path.resolve()
    return None


def _probe_mp4_duration_fallback(path: Path) -> float | None:
    try:
        data = path.read_bytes()[:262_144]
        idx = data.find(b"mvhd")
        if idx == -1 or idx + 28 > len(data):
            return None
        version = data[idx + 4]
        if version == 0 and idx + 24 <= len(data):
            scale, dur = struct.unpack(">II", data[idx + 16:idx + 24])
            return (dur / scale) if scale else None
        if version == 1 and idx + 36 <= len(data):
            scale, dur = struct.unpack(">IQ", data[idx + 24:idx + 36])
            return (dur / scale) if scale else None
    except Exception:
        return None
    return None


def probe_clip(path: Path) -> ClipInfo:
    ffprobe = find_ffprobe()
    if ffprobe:
        try:
            res = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                capture_output=True, timeout=15, creationflags=CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                meta = json.loads(res.stdout.decode("utf-8", errors="replace"))
                v_stream = next((s for s in meta.get("streams") or [] if s.get("codec_type") == "video"), None)
                a_stream = next((s for s in meta.get("streams") or [] if s.get("codec_type") == "audio"), None)
                dur = float((meta.get("format") or {}).get("duration") or (v_stream or {}).get("duration") or 8.0)
                w = int((v_stream or {}).get("width") or 1080)
                h = int((v_stream or {}).get("height") or 1920)
                rate_s = str((v_stream or {}).get("r_frame_rate") or "30/1")
                if "/" in rate_s:
                    num, den = rate_s.split("/", 1)
                    fps = float(num) / max(1.0, float(den))
                else:
                    fps = float(rate_s)
                return ClipInfo(path=path, duration_s=max(0.5, dur), width=w, height=h, fps=max(24.0, min(60.0, fps)), has_audio=a_stream is not None)
        except Exception:
            pass

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        try:
            res = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, timeout=12, creationflags=CREATE_NO_WINDOW)
            info = res.stderr.decode("utf-8", errors="replace")
            dur = 8.0
            m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info)
            if m_dur:
                dur = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))
            w, h = 1080, 1920
            m_dim = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", info)
            if m_dim:
                w, h = int(m_dim.group(1)), int(m_dim.group(2))
            fps = 30.0
            m_fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", info)
            if m_fps:
                fps = float(m_fps.group(1))
            has_audio = "Audio:" in info
            return ClipInfo(path=path, duration_s=max(0.5, dur), width=w, height=h, fps=max(24.0, min(60.0, fps)), has_audio=has_audio)
        except Exception:
            pass

    dur = _probe_mp4_duration_fallback(path) or 8.0
    return ClipInfo(path=path, duration_s=max(1.0, dur), width=1080, height=1920, fps=30.0, has_audio=True)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[Path] = []
    if sys.platform == "win32":
        fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates += [fonts_dir / "impact.ttf", fonts_dir / "arialbd.ttf", fonts_dir / "segoeui.ttf"]
    elif sys.platform == "darwin":
        candidates += [
            Path("/System/Library/Fonts/Supplemental/Impact.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/System/Library/Fonts/Helvetica.ttc"),
        ]
    else:
        candidates += [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        ]
    for cand in candidates:
        if cand.is_file():
            try:
                return ImageFont.truetype(str(cand), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _aspect_matches(clip: ClipInfo, size: tuple[int, int]) -> bool:
    c_ratio = clip.width / max(1, clip.height)
    t_ratio = size[0] / max(1, size[1])
    return ((clip.width >= clip.height) == (size[0] >= size[1])) and abs(c_ratio - t_ratio) <= 0.45


def _voiced_span(pcm: Any, rate: int = 16000) -> tuple[float, float]:
    import numpy as np

    dur = len(pcm) / max(1, rate)
    if len(pcm) < rate * 0.5:
        return 0.0, dur
    win = max(1, int(rate * 0.1))
    n = len(pcm) // win
    if n <= 0:
        return 0.0, dur
    rms = np.sqrt(np.mean(pcm[: n * win].reshape(n, win) ** 2, axis=1))
    thresh = max(0.012, float(np.percentile(rms, 35)) * 1.8)
    active = np.where(rms >= thresh)[0]
    if active.size == 0:
        return 0.0, dur
    return round(float(active[0]) * 0.1, 2), round(min(dur, (float(active[-1]) + 1.0) * 0.1), 2)


def _chunk_words_into_timeline(
    segments: list[dict[str, Any]],
    *,
    uppercase: bool,
    max_words_per_chunk: int = 2,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for seg in segments:
        raw = str(seg.get("text") or "").strip()
        words = [w for w in raw.split() if w]
        if not words:
            continue
        s0 = float(seg.get("start", 0.0))
        s1 = max(s0 + 0.35, float(seg.get("end", s0 + max(0.8, len(words) * 0.34))))
        span = s1 - s0
        groups = [words[i : i + max_words_per_chunk] for i in range(0, len(words), max_words_per_chunk)]
        weights = [sum(len(w) + 1 for w in g) for g in groups]
        total_w = max(1, sum(weights))
        cur = s0
        for g, wt in zip(groups, weights, strict=True):
            dur = max(0.28, span * (wt / total_w))
            label = " ".join(g)
            chunks.append({
                "text": label.upper() if uppercase else label,
                "start_s": round(cur, 2),
                "duration_s": round(dur, 2),
            })
            cur += dur
    return chunks


def _transcribe_clip_segments(ctx: ToolContext, clip: ClipInfo, *, uppercase: bool = False) -> list[dict[str, Any]]:
    ffmpeg = find_ffmpeg()
    stt = getattr(ctx.services, "stt", None)
    if not ffmpeg or not clip.has_audio or clip.duration_s > 180:
        return []
    wav_file = None
    try:
        import numpy as np

        fd, tmp_name = tempfile.mkstemp(prefix="ressy-vid-", suffix=".wav")
        os.close(fd)
        wav_file = Path(tmp_name)
        subprocess.run(
            [ffmpeg, "-y", "-i", str(clip.path), "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(wav_file)],
            capture_output=True, timeout=30, check=True, creationflags=CREATE_NO_WINDOW,
        )
        with wave.open(str(wav_file), "rb") as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if len(pcm) < 8000:
            return []

        segments: list[dict[str, Any]] = []
        plain_text = ""

        local_whisper = getattr(stt, "local", None) if stt is not None else None
        if local_whisper is None and stt is not None and hasattr(stt, "transcribe"):
            local_whisper = stt
        if local_whisper is not None and hasattr(local_whisper, "transcribe") and stt is not None:
            from ..speech import local_stt

            settings = getattr(ctx.services, "settings", None)
            mname = getattr(settings, "local_stt_model", "base-q5_1") if settings else "base-q5_1"
            lang = getattr(settings, "language", "it") if settings else "it"
            if not local_stt.is_downloaded(mname):
                for cand in ("small-q5_1", "base-q5_1", "tiny-q5_1"):
                    if local_stt.is_downloaded(cand):
                        mname = cand
                        break
            if local_stt.is_downloaded(mname):
                payload = local_whisper.transcribe(pcm, name=mname, language=lang, prompt="")
                segments = [s for s in (payload.get("segments") or []) if str(s.get("text") or "").strip()]
                plain_text = str(payload.get("text") or "")

        if not segments and stt is not None:
            if hasattr(stt, "transcribe_pcm"):
                res = asyncio.run(stt.transcribe_pcm(pcm, 16000, lenient=True))
                plain_text = str(getattr(res, "text", "") or "")
            elif hasattr(stt, "transcribe_sync"):
                plain_text = stt.transcribe_sync(pcm, 16000)

        if not segments and plain_text.strip():
            v0, v1 = _voiced_span(pcm, 16000)
            segments = [{"text": plain_text.strip(), "start": v0, "end": max(v0 + 1.0, v1)}]

        return _chunk_words_into_timeline(segments, uppercase=uppercase, max_words_per_chunk=2)[:42]
    except Exception:
        log.debug("video STT phrase extraction skipped", exc_info=True)
        return []
    finally:
        if wav_file is not None:
            wav_file.unlink(missing_ok=True)


def _transcribe_clip_phrases(ctx: ToolContext, clip: ClipInfo) -> list[str]:
    return [c["text"] for c in _transcribe_clip_segments(ctx, clip, uppercase=True)[:10]]


def _plan_impact_phrases(
    ctx: ToolContext,
    clips: list[ClipInfo],
    total_s: float,
    *,
    title: str,
    explicit_phrases: list[str],
    style: str,
    use_stt: bool = True,
    caption_mode: str = "word",
) -> list[dict[str, Any]]:
    palette = _STYLE_PALETTES.get(style, _STYLE_PALETTES["viral"])
    colors = palette["text_colors"]
    kinetic_word = caption_mode == "word" and style in ("viral", "gaming", "vlog")
    hook_style = "hook_pov" if (title.strip().upper().startswith("POV:") or style == "vlog") else "hook_neon"

    timed_chunks: list[dict[str, Any]] = []
    cleaned_explicit = [p.strip() for p in explicit_phrases if p.strip()]
    if cleaned_explicit:
        if kinetic_word and any(len(p.split()) > 4 for p in cleaned_explicit):
            joined = " ".join(cleaned_explicit)
            timed_chunks = _chunk_words_into_timeline(
                [{"text": joined, "start": 0.15, "end": max(1.2, total_s - 0.15)}],
                uppercase=(style == "gaming"),
                max_words_per_chunk=2,
            )
        else:
            slot = total_s / max(1, len(cleaned_explicit) + (1 if title.strip() else 0))
            offset = slot if title.strip() else 0.0
            for idx, text in enumerate(cleaned_explicit):
                timed_chunks.append({
                    "text": text.upper() if len(text.split()) <= 4 else text,
                    "start_s": round(offset + idx * slot + 0.1, 2),
                    "duration_s": round(max(1.0, slot - 0.18), 2),
                    "mode": "pill" if caption_mode == "phrase" else "word",
                })
    elif use_stt:
        cursor = 0.0
        for clip in clips[:3]:
            segs = _transcribe_clip_segments(ctx, clip, uppercase=(style == "gaming"))
            for s in segs:
                s["start_s"] = round(s["start_s"] + cursor, 2)
                timed_chunks.append(s)
            cursor += clip.duration_s

    if not timed_chunks:
        settings = getattr(ctx.services, "settings", None)
        lang = getattr(settings, "language", "it") if settings else "it"
        defaults = palette["phrases_en"] if lang == "en" else palette["phrases_it"]
        slot = total_s / max(1, len(defaults))
        for idx, text in enumerate(defaults):
            timed_chunks.append({
                "text": text,
                "start_s": round(idx * slot + 0.12, 2),
                "duration_s": round(max(1.1, slot - 0.2), 2),
                "mode": "word" if kinetic_word else "pill",
            })

    timeline: list[dict[str, Any]] = []
    if title.strip():
        hook_dur = min(2.8, max(1.6, total_s * 0.28))
        timeline.append({
            "index": 0,
            "text": title.strip().upper(),
            "start_s": 0.08,
            "duration_s": round(hook_dur, 2),
            "color": "#3CEBFF" if style in ("viral", "gaming") else colors[0],
            "pill": palette["pill_bg"],
            "is_hook": True,
            "mode": hook_style,
        })

    base_idx = len(timeline)
    for k, ch in enumerate(timed_chunks):
        st = max(0.05, float(ch["start_s"]))
        if st >= total_s - 0.15:
            continue
        dur = min(float(ch["duration_s"]), max(0.25, total_s - st))
        word_clean = re.sub(r"[^\w]+", "", ch["text"])
        accent = (k % 5 == 2) or len(word_clean) >= 9
        timeline.append({
            "index": base_idx + k,
            "text": ch["text"],
            "start_s": round(st, 2),
            "duration_s": round(dur, 2),
            "color": colors[k % len(colors)] if accent else "#FFFFFF",
            "pill": palette["pill_bg"],
            "is_hook": (k == 0 and not title.strip()),
            "mode": ch.get("mode") or ("word" if kinetic_word else "pill"),
        })
    return timeline


_BROLL_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:browser|gologin|chrome|web|sito|link|pagina|proxy)\b", re.I), "browser"),
    (re.compile(r"\b(?:telefon\w*|account|app|vinted|social|tiktok|instagram|discord)\b", re.I), "phone"),
    (re.compile(r"\b(?:crea\w*|ai|bot|smart|veloce|subito|adesso|segret\w*)\b", re.I), "spark"),
    (re.compile(r"\b(?:sicur\w*|blocc\w*|confond\w*|prote\w*|privacy)\b", re.I), "shield"),
    (re.compile(r"\b(?:video|youtube|edita\w*|monta\w*|studio|capcut)\b", re.I), "play"),
]


def _pick_icon_kind(text: str, idx: int) -> str:
    for pat, icon in _BROLL_KEYWORDS:
        if pat.search(text):
            return icon
    return ("spark", "browser", "phone", "play", "shield")[idx % 5]


def _plan_broll_elements(
    phrases: list[dict[str, Any]],
    total_s: float,
    *,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not enabled or total_s < 4.5:
        return [], []
    body = [ph for ph in phrases if not ph.get("is_hook") and ph["start_s"] >= 2.0 and ph["start_s"] <= total_s - 1.1]
    if not body:
        return [], []

    slides: list[dict[str, Any]] = []
    badges: list[dict[str, Any]] = []
    last_fx_t = 1.4
    max_slides = min(3, max(1, int(total_s // 5.5)))
    max_badges = min(3, max(1, int(total_s // 5.0)))
    step = max(1, len(body) // (max_slides + max_badges + 1))

    for idx in range(0, len(body), step):
        ph = body[idx]
        st = float(ph["start_s"])
        if st - last_fx_t < 1.9:
            continue
        word = ph["text"].strip().split()[0][:18]
        icon = _pick_icon_kind(ph["text"], len(slides) + len(badges))
        want_slide = len(slides) < max_slides and (len(slides) <= len(badges) or len(badges) >= max_badges)
        if want_slide:
            variant = "warp_grid" if len(slides) % 2 == 0 else "radial_glow"
            dur = round(min(0.88, max(0.60, total_s - st - 0.3)), 2)
            slides.append({
                "text": word,
                "subtitle": ph["text"],
                "icon": icon,
                "variant": variant,
                "start_s": round(st, 2),
                "duration_s": dur,
            })
            last_fx_t = st + dur
        elif len(badges) < max_badges:
            dur = round(min(1.20, max(0.80, total_s - st - 0.3)), 2)
            badges.append({
                "text": word,
                "icon": icon,
                "start_s": round(st, 2),
                "duration_s": dur,
            })
            last_fx_t = st + dur
    return slides, badges


def _extract_frame(clip: Path, at_s: float, dst: Path) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    try:
        subprocess.run(
            [ffmpeg, "-y", "-ss", f"{max(0.1, at_s):.2f}", "-i", str(clip), "-frames:v", "1", "-q:v", "2", str(dst)],
            capture_output=True, timeout=20, check=True, creationflags=CREATE_NO_WINDOW,
        )
        return dst.is_file()
    except Exception:
        return False


def _grade_pil_image(img: Image.Image, color_grade: str) -> Image.Image:
    out = img.convert("RGB")
    if color_grade == "vivid":
        out = ImageEnhance.Contrast(out).enhance(1.12)
        out = ImageEnhance.Color(out).enhance(1.22)
        out = ImageEnhance.Brightness(out).enhance(1.02)
    elif color_grade == "teal_orange":
        out = ImageEnhance.Contrast(out).enhance(1.14)
        out = ImageEnhance.Color(out).enhance(1.15)
        r, g, b = out.split()
        r = r.point(lambda v: min(255, int(v * 1.05)))
        b = b.point(lambda v: max(0, int(v * 0.94)))
        out = Image.merge("RGB", (r, g, b))
    elif color_grade == "cinematic_film":
        out = ImageEnhance.Contrast(out).enhance(1.16)
        out = ImageEnhance.Color(out).enhance(0.90)
        out = ImageEnhance.Brightness(out).enhance(0.97)
    return out


def _draw_vector_icon(draw: ImageDraw.ImageDraw, icon: str, cx: int, cy: int, r: int, fg: tuple[int, int, int, int]) -> None:
    if icon == "phone":
        pw, ph = int(r * 0.85), int(r * 1.35)
        draw.rounded_rectangle([cx - pw // 2, cy - ph // 2, cx + pw // 2, cy + ph // 2], radius=max(8, pw // 6), fill=(26, 28, 38, 255), outline=fg, width=4)
        draw.rounded_rectangle([cx - pw // 2 + 8, cy - ph // 2 + 12, cx + pw // 2 - 8, cy + ph // 2 - 14], radius=6, fill=(242, 245, 252, 255))
    elif icon == "browser":
        bw, bh = int(r * 1.45), int(r * 1.05)
        x0, y0, x1, y1 = cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2
        draw.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=(24, 26, 36, 255), outline=fg, width=4)
        draw.line([(x0 + 4, y0 + bh // 4), (x1 - 4, y0 + bh // 4)], fill=fg, width=3)
        for k in range(3):
            dx = x0 + 18 + k * 14
            draw.ellipse([dx - 4, y0 + bh // 8 - 4, dx + 4, y0 + bh // 8 + 4], fill=fg)
        draw.line([(cx - bw // 4, cy + 4), (cx + bw // 4, cy + 4)], fill=(255, 255, 255, 210), width=4)
    elif icon == "shield":
        pts = [(cx, cy - r), (cx + int(r * 0.85), cy - int(r * 0.55)), (cx + int(r * 0.7), cy + int(r * 0.35)), (cx, cy + r), (cx - int(r * 0.7), cy + int(r * 0.35)), (cx - int(r * 0.85), cy - int(r * 0.55))]
        draw.polygon(pts, fill=(26, 30, 44, 255), outline=fg, width=4)
        draw.line([(cx - r // 3, cy), (cx - 2, cy + r // 3), (cx + r // 2, cy - r // 3)], fill=fg, width=5)
    elif icon == "play":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(24, 26, 36, 255), outline=fg, width=4)
        tri = [(cx - r // 4, cy - r // 2), (cx + r // 2, cy), (cx - r // 4, cy + r // 2)]
        draw.polygon(tri, fill=fg)
    else:
        pts = [(cx + int(r * 0.1), cy - r), (cx - int(r * 0.45), cy + 4), (cx + int(r * 0.05), cy + 4), (cx - int(r * 0.1), cy + r), (cx + int(r * 0.45), cy - 4), (cx - int(r * 0.05), cy - 4)]
        draw.polygon(pts, fill=fg, outline=(18, 20, 28, 255))


def _render_cutaway_slide(
    dst: Path,
    keyword: str,
    subtitle: str,
    icon_kind: str,
    size: tuple[int, int],
    *,
    variant: str = "warp_grid",
) -> None:
    w, h = size
    canvas = Image.new("RGBA", (w, h), (242, 244, 249, 255))
    draw = ImageDraw.Draw(canvas)

    vignette = Image.new("RGBA", (w, h), (150, 156, 172, 130))
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-int(w * 0.15), int(h * 0.08), int(w * 1.15), int(h * 0.92)], fill=(250, 251, 255, 255))
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=max(45, w // 9)))
    canvas = Image.alpha_composite(canvas, vignette)
    draw = ImageDraw.Draw(canvas)

    if variant == "warp_grid":
        grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grid)
        cols = 14
        rows = 24
        cx, cy = w * 0.5, h * 0.48
        for i in range(-1, cols + 2):
            pts: list[tuple[float, float]] = []
            bx = (i / cols) * w
            for j in range(rows + 1):
                py = (j / rows) * h
                dx = (bx - cx) / max(1.0, w * 0.5)
                dy = (py - cy) / max(1.0, h * 0.5)
                bow = 1.0 + 0.14 * (1.0 - dy * dy)
                pts.append((cx + dx * (w * 0.5) * bow, py))
            gd.line(pts, fill=(182, 190, 208, 120), width=2)
        for j in range(-1, rows + 2):
            pts = []
            by = (j / rows) * h
            for i in range(cols + 1):
                px = (i / cols) * w
                dx = (px - cx) / max(1.0, w * 0.5)
                dy = (by - cy) / max(1.0, h * 0.5)
                bow = 1.0 + 0.12 * (1.0 - dx * dx)
                pts.append((px, cy + dy * (h * 0.5) * bow))
            gd.line(pts, fill=(182, 190, 208, 120), width=2)
        canvas = Image.alpha_composite(canvas, grid)
        draw = ImageDraw.Draw(canvas)

        card_sz = max(170, int(w * 0.34))
        cx_i, cy_i = w // 2, int(h * 0.44)
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle([cx_i - card_sz // 2, cy_i - card_sz // 2 + 16, cx_i + card_sz // 2, cy_i + card_sz // 2 + 16], radius=32, fill=(20, 24, 38, 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
        canvas = Image.alpha_composite(canvas, shadow)
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(
            [cx_i - card_sz // 2, cy_i - card_sz // 2, cx_i + card_sz // 2, cy_i + card_sz // 2],
            radius=32,
            fill=(24, 26, 34, 245),
            outline=(157, 107, 255, 220),
            width=4,
        )
        _draw_vector_icon(draw, icon_kind, cx_i, cy_i, card_sz // 3, (77, 240, 181, 255))
    else:
        f_big = max(62, int(w * 0.11))
        font = _load_font(f_big)
        text = keyword.strip()
        b = draw.textbbox((0, 0), text, font=font)
        tw, th = b[2] - b[0], b[3] - b[1]
        tx, ty = (w - tw) // 2, (h - th) // 2 - th // 6
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.text((tx - 4, ty), text, font=font, fill=(0, 220, 255, 190))
        gd.text((tx + 4, ty), text, font=font, fill=(255, 70, 95, 190))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=3))
        canvas = Image.alpha_composite(canvas, glow)
        draw = ImageDraw.Draw(canvas)
        draw.text((tx, ty), text, font=font, fill=(14, 16, 22, 255))

    canvas.convert("RGB").save(dst, "PNG")


def _render_floating_badge(dst: Path, label: str, icon_kind: str, size: tuple[int, int]) -> None:
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rad = max(58, int(w * 0.12))
    cx, cy = w // 2, int(h * 0.56)

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - rad - 10, cy - rad - 10, cx + rad + 10, cy + rad + 10], fill=(77, 240, 181, 140))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=18))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(18, 22, 30, 240), outline=(77, 240, 181, 255), width=5)
    _draw_vector_icon(draw, icon_kind, cx, cy, int(rad * 0.58), (77, 240, 181, 255))
    img.save(dst, "PNG")


def _synthesize_sfx_wav(dst: Path, total_s: float, events: list[tuple[str, float]]) -> bool:
    if not events or total_s <= 0.4:
        return False
    try:
        import math
        import numpy as np

        rate = 44100
        total_n = max(rate, int(round(total_s * rate)))
        buf = np.zeros(total_n, dtype=np.float32)
        rng = np.random.default_rng(7)

        for kind, when_s in events:
            start = max(0, min(total_n - 1000, int(round(when_s * rate))))
            if kind == "sub":
                n = min(int(0.45 * rate), total_n - start)
                t = np.linspace(0, n / rate, n, dtype=np.float32)
                freq = 92.0 * np.exp(-t * 3.8) + 34.0
                sig = np.sin(2.0 * math.pi * np.cumsum(freq) / rate) * np.exp(-t * 6.0) * 0.55
                buf[start : start + n] += sig
            elif kind == "pop":
                n = min(int(0.14 * rate), total_n - start)
                t = np.linspace(0, n / rate, n, dtype=np.float32)
                freq = 540.0 + 420.0 * np.exp(-t * 35.0)
                sig = np.sin(2.0 * math.pi * np.cumsum(freq) / rate) * np.exp(-t * 24.0) * 0.35
                buf[start : start + n] += sig
            else:
                n = min(int(0.28 * rate), total_n - start)
                t = np.linspace(0, 1, n, dtype=np.float32)
                env = np.maximum(0.0, np.sin(math.pi * t)) ** 1.6
                noise = rng.normal(0.0, 1.0, n).astype(np.float32)
                kernel = np.ones(18, dtype=np.float32) / 18.0
                smooth = np.convolve(noise, kernel, mode="same")
                buf[start : start + n] += smooth * env * 0.32

        peak = float(np.max(np.abs(buf)))
        if peak > 0.9:
            buf = buf * (0.85 / peak)
        pcm16 = np.clip(buf * 32767.0, -32768, 32767).astype(np.int16)
        stereo = np.column_stack([pcm16, pcm16]).tobytes()
        with wave.open(str(dst), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(stereo)
        return dst.is_file()
    except Exception:
        log.debug("SFX generation skipped", exc_info=True)
        return False


def _render_composite_preview(
    dst: Path,
    bg_path: Path,
    raw_frame: Path | None,
    card_path: Path | None,
    size: tuple[int, int],
    *,
    color_grade: str = "vivid",
    show_progress_bar: bool = True,
    progress_frac: float = 0.5,
    fullscreen_fill: bool = True,
) -> None:
    try:
        pw, ph = 540, max(304, int(round(540 * (size[1] / max(1, size[0])))))
        if bg_path.is_file() and not fullscreen_fill:
            canvas = Image.open(bg_path).convert("RGBA").resize((pw, ph), Image.Resampling.LANCZOS)
        else:
            canvas = Image.new("RGBA", (pw, ph), (16, 17, 24, 255))

        if raw_frame is not None and raw_frame.is_file():
            fg = _grade_pil_image(Image.open(raw_frame), color_grade)
            if fullscreen_fill:
                scale = max(pw / max(1, fg.width), ph / max(1, fg.height))
                nw, nh = max(2, int(fg.width * scale)), max(2, int(fg.height * scale))
                fg_rs = fg.resize((nw, nh), Image.Resampling.LANCZOS).convert("RGBA")
                lx, ly = max(0, (nw - pw) // 2), max(0, (nh - ph) // 2)
                canvas = fg_rs.crop((lx, ly, lx + pw, ly + ph))
            else:
                fg_w, fg_h = int(pw * 0.90), int(ph * 0.90)
                scale = min(fg_w / max(1, fg.width), fg_h / max(1, fg.height))
                nw, nh = max(2, int(fg.width * scale)), max(2, int(fg.height * scale))
                fg_rs = fg.resize((nw, nh), Image.Resampling.LANCZOS).convert("RGBA")
                x, y = (pw - nw) // 2, (ph - nh) // 2
                mask = Image.new("L", (nw, nh), 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, nw, nh], radius=16, fill=255)
                canvas.paste(fg_rs, (x, y), mask)

        if card_path is not None and card_path.is_file():
            card = Image.open(card_path).convert("RGBA").resize((pw, ph), Image.Resampling.LANCZOS)
            canvas = Image.alpha_composite(canvas, card)

        if show_progress_bar:
            draw = ImageDraw.Draw(canvas)
            bar_h = 6
            draw.rectangle([0, ph - bar_h, pw, ph], fill=(30, 32, 42, 220))
            fill_w = max(8, int(pw * max(0.05, min(1.0, progress_frac))))
            draw.rectangle([0, ph - bar_h, fill_w, ph], fill=(157, 107, 255, 255))

        canvas.convert("RGB").save(dst, "PNG")
    except Exception:
        log.debug("composite preview skipped", exc_info=True)


def _generate_background_image(dst: Path, size: tuple[int, int], first_clip: ClipInfo, style: str, bg_mode: str) -> None:
    w, h = size
    palette = _STYLE_PALETTES.get(style, _STYLE_PALETTES["viral"])
    base_rgb = palette["bg"]
    glow_rgb = palette["glow"]
    accent_rgb = palette["accent"]

    frame_tmp = dst.with_suffix(".frame.jpg")
    canvas: Image.Image | None = None
    if bg_mode in ("auto", "blur") and _extract_frame(first_clip.path, min(1.5, first_clip.duration_s * 0.35), frame_tmp):
        try:
            src = Image.open(frame_tmp).convert("RGB")
            scale = max(w / max(1, src.width), h / max(1, src.height)) * 1.15
            rw, rh = int(src.width * scale), int(src.height * scale)
            blurred = src.resize((rw, rh), Image.Resampling.LANCZOS)
            left = max(0, (rw - w) // 2)
            top = max(0, (rh - h) // 2)
            canvas = blurred.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(radius=38))
            scrim = Image.new("RGBA", (w, h), (*base_rgb, 138))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim)
        except Exception:
            canvas = None
        finally:
            frame_tmp.unlink(missing_ok=True)

    if canvas is None:
        canvas = Image.new("RGBA", (w, h), (*base_rgb, 255))
        glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.ellipse((w * -0.15, h * -0.1, w * 0.85, h * 0.55), fill=(*glow_rgb, 90))
        gd.ellipse((w * 0.2, h * 0.5, w * 1.15, h * 1.1), fill=(*accent_rgb, 75))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(60, w // 7)))
        canvas = Image.alpha_composite(canvas, glow_layer)
        if bg_mode in ("auto", "neon_grid"):
            grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(grid)
            step = max(54, w // 16)
            for gx in range(0, w, step):
                draw.line([(gx, 0), (gx, h)], fill=(255, 255, 255, 16), width=1)
            for gy in range(0, h, step):
                draw.line([(0, gy), (w, gy)], fill=(255, 255, 255, 16), width=1)
            canvas = Image.alpha_composite(canvas, grid)

    canvas.convert("RGB").save(dst, "PNG")


def _hex_to_rgba(hex_color: str, default_alpha: int = 255) -> tuple[int, int, int, int]:
    s = hex_color.lstrip("#")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = int(s[6:8], 16) if len(s) >= 8 else default_alpha
    return r, g, b, a


def _wrap_text(text: str, font: Any, draw: ImageDraw.ImageDraw, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        trial = " ".join([*cur, word])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if cur and (bbox[2] - bbox[0]) > max_w:
            lines.append(" ".join(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        lines.append(" ".join(cur))
    return lines or [text]


def _render_phrase_card(dst: Path, phrase: dict[str, Any], size: tuple[int, int]) -> None:
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mode = str(phrase.get("mode") or ("hook_neon" if phrase.get("is_hook") else "word"))
    draw = ImageDraw.Draw(img)

    if mode == "hook_pov":
        fsize = max(40, int(w * 0.058))
        font = _load_font(fsize)
        raw_parts = [p.strip() for p in phrase["text"].replace("|", "\n").replace("/", "\n").splitlines() if p.strip()]
        lines = [ln for p in raw_parts for ln in _wrap_text(p, font, draw, int(w * 0.80))] or _wrap_text(phrase["text"], font, draw, int(w * 0.80))
        cur_y = max(48, int(h * 0.14))
        for ln in lines[:3]:
            b = draw.textbbox((0, 0), ln, font=font)
            tw, th = b[2] - b[0], max(fsize, b[3] - b[1])
            px, py = int(w * 0.045), int(fsize * 0.25)
            bx = (w - tw - px * 2) // 2
            bw, bh = tw + px * 2, th + py * 2
            sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle([bx, cur_y + 6, bx + bw, cur_y + bh + 6], radius=20, fill=(0, 0, 0, 130))
            img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(radius=8)))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([bx, cur_y, bx + bw, cur_y + bh], radius=20, fill=(255, 255, 255, 245))
            draw.text((bx + px, cur_y + py - 2), ln, font=font, fill=(16, 18, 24, 255))
            cur_y += bh + int(fsize * 0.18)
        img.save(dst, "PNG")
        return

    if mode == "hook_neon":
        fsize = max(48, int(w * 0.072))
        font = _load_font(fsize)
        raw_parts = [p.strip() for p in phrase["text"].replace("|", "\n").replace("/", "\n").splitlines() if p.strip()]
        lines = [ln for p in raw_parts for ln in _wrap_text(p, font, draw, int(w * 0.86))] or _wrap_text(phrase["text"], font, draw, int(w * 0.86))
        fg_rgba = _hex_to_rgba(phrase["color"])
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cur_y = max(44, int(h * 0.13))
        coords: list[tuple[str, int, int]] = []
        for idx, ln in enumerate(lines[:3]):
            cur_font = font if idx == 0 else _load_font(max(34, int(fsize * 0.72)))
            b = draw.textbbox((0, 0), ln, font=cur_font)
            tw, th = b[2] - b[0], max(fsize, b[3] - b[1])
            tx = (w - tw) // 2
            gd.text((tx, cur_y), ln, font=cur_font, fill=(*fg_rgba[:3], 180))
            coords.append((ln, tx, cur_y))
            cur_y += th + int(fsize * 0.16)
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(radius=14)))
        draw = ImageDraw.Draw(img)
        for idx, (ln, tx, cy_line) in enumerate(coords):
            cur_font = font if idx == 0 else _load_font(max(34, int(fsize * 0.72)))
            col = fg_rgba if idx == 0 else (255, 255, 255, 255)
            draw.text((tx, cy_line), ln, font=cur_font, fill=col, stroke_width=5, stroke_fill=(10, 12, 18, 245))
        img.save(dst, "PNG")
        return

    if mode == "word":
        fsize = max(48, int(w * 0.068))
        font = _load_font(fsize)
        lines = _wrap_text(phrase["text"], font, draw, int(w * 0.84))
        fg_rgba = _hex_to_rgba(phrase["color"])
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cur_y = int(h * 0.73) - (len(lines) * fsize) // 2
        positions: list[tuple[str, int, int]] = []
        for ln in lines[:2]:
            b = draw.textbbox((0, 0), ln, font=font)
            tw = b[2] - b[0]
            tx = (w - tw) // 2
            gd.text((tx, cur_y + 5), ln, font=font, fill=(0, 0, 0, 210))
            positions.append((ln, tx, cur_y))
            cur_y += int(fsize * 1.18)
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(radius=10)))
        draw = ImageDraw.Draw(img)
        for ln, tx, ty in positions:
            draw.text((tx, ty), ln, font=font, fill=fg_rgba, stroke_width=6, stroke_fill=(10, 11, 15, 250))
        img.save(dst, "PNG")
        return

    fsize = max(44, int(w * (0.068 if phrase.get("is_hook") else 0.056)))
    font = _load_font(fsize)
    lines = _wrap_text(phrase["text"], font, draw, int(w * 0.84))
    line_heights: list[int] = []
    line_widths: list[int] = []
    for ln in lines:
        b = draw.textbbox((0, 0), ln, font=font)
        line_widths.append(b[2] - b[0])
        line_heights.append(max(fsize, b[3] - b[1]))
    pad_x, pad_y = int(w * 0.048), int(fsize * 0.36)
    box_w = min(int(w * 0.92), max(line_widths) + pad_x * 2)
    box_h = sum(line_heights) + max(0, len(lines) - 1) * int(fsize * 0.25) + pad_y * 2
    box_x = (w - box_w) // 2
    y_ratio = 0.20 if phrase.get("is_hook") else 0.74
    box_y = max(40, min(h - box_h - 40, int(h * y_ratio) - box_h // 2))

    pill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    radius = max(18, int(fsize * 0.42))
    pd.rounded_rectangle([box_x, box_y + 10, box_x + box_w, box_y + box_h + 10], radius=radius, fill=(0, 0, 0, 160))
    pill = pill.filter(ImageFilter.GaussianBlur(radius=12))
    img = Image.alpha_composite(img, pill)
    draw = ImageDraw.Draw(img)

    fg_rgba = _hex_to_rgba(phrase["color"])
    pill_rgba = _hex_to_rgba(phrase["pill"], 235)
    draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=radius, fill=pill_rgba, outline=(*fg_rgba[:3], 185), width=3)
    if phrase.get("is_hook"):
        bar_w = max(8, w // 120)
        draw.rounded_rectangle([box_x + 10, box_y + 12, box_x + 10 + bar_w, box_y + box_h - 12], radius=4, fill=fg_rgba)

    cur_y = box_y + pad_y
    for idx, ln in enumerate(lines):
        lw = line_widths[idx]
        tx = (w - lw) // 2
        draw.text((tx, cur_y), ln, font=font, fill=fg_rgba, stroke_width=4, stroke_fill=(12, 12, 16, 240))
        cur_y += line_heights[idx] + int(fsize * 0.25)
    img.save(dst, "PNG")


def _write_srt(dst: Path, phrases: list[dict[str, Any]]) -> None:
    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks: list[str] = []
    for i, ph in enumerate(phrases, start=1):
        blocks.append(f"{i}\n{fmt_ts(ph['start_s'])} --> {fmt_ts(ph['start_s'] + ph['duration_s'])}\n{ph['text']}\n")
    dst.write_text("\n".join(blocks), encoding="utf-8")


def _cap_uid() -> str:
    return str(uuid.uuid4()).upper()


def _capcut_cached_anim() -> dict[str, Any] | None:
    cache = _capcut_cache_dir()
    if cache is None:
        return None
    for sub in sorted(cache.iterdir())[:40]:
        if not sub.is_dir():
            continue
        for inner in sub.iterdir():
            if inner.is_dir() and (inner / "config.json").is_file():
                try:
                    cfg = json.loads((inner / "config.json").read_text(encoding="utf-8"))
                    title = str(cfg.get("name") or cfg.get("title") or "")
                    if title and len(title) < 40:
                        return {
                            "id": sub.name,
                            "type": "in",
                            "start": 0,
                            "duration": 500000,
                            "path": inner.as_posix(),
                            "platform": "all",
                            "resource_id": sub.name,
                            "third_resource_id": "0",
                            "source_platform": 1,
                            "name": title,
                            "category_id": "ruchang",
                            "category_name": "In entrata",
                        }
                except Exception:
                    continue
    return None


def _build_capcut_draft(
    drafts_root: Path,
    project_name: str,
    clips: list[ClipInfo],
    bg_path: Path,
    phrases: list[dict[str, Any]],
    music_path: Path | None,
    size: tuple[int, int],
    cut_interval_s: float,
    effects: list[str],
    *,
    color_grade: str = "vivid",
    transition: str = "smooth",
    broll_pngs: list[tuple[dict[str, Any], Path]] = (),
    badge_pngs: list[tuple[dict[str, Any], Path]] = (),
    sfx_path: Path | None = None,
    fullscreen_fill: bool = False,
) -> Path:
    draft_folder = drafts_root / project_name
    draft_folder.mkdir(parents=True, exist_ok=True)
    draft_id = _cap_uid()
    now_s = int(time.time())
    now_us = int(time.time() * 1_000_000)
    w, h = size

    cover_path = draft_folder / "draft_cover.jpg"
    try:
        Image.open(bg_path).convert("RGB").resize((min(720, w), min(1280, h))).save(cover_path, "JPEG", quality=85)
    except Exception:
        pass

    mats: dict[str, list[dict[str, Any]]] = {
        "videos": [],
        "audios": [],
        "texts": [],
        "effects": [],
        "transitions": [],
        "canvases": [],
        "material_animations": [],
        "placeholder_infos": [],
        "speeds": [],
        "text_templates": [],
        "sound_channel_mappings": [],
        "material_colors": [],
        "loudnesses": [],
        "vocal_separations": [],
        "audio_fades": [],
        "color_curves": [],
    }
    meta_videos: list[dict[str, Any]] = []
    meta_music: list[dict[str, Any]] = []

    def _aux_refs() -> list[str]:
        spd_id, ph_id, canvas_id = _cap_uid(), _cap_uid(), _cap_uid()
        scm_id, col_id, loud_id, voc_id = _cap_uid(), _cap_uid(), _cap_uid(), _cap_uid()
        mats["speeds"].append({"id": spd_id, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        mats["placeholder_infos"].append({"id": ph_id, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        mats["canvases"].append({"id": canvas_id, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        mats["sound_channel_mappings"].append({"id": scm_id, "type": "none", "audio_channel_mapping": 0, "is_config_open": False})
        mats["material_colors"].append({"id": col_id, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        mats["loudnesses"].append({"id": loud_id, "enable": False, "time_range": None, "file_id": "", "target_loudness": 0.0, "loudness_param": None})
        mats["vocal_separations"].append({"id": voc_id, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})
        return [spd_id, ph_id, canvas_id, scm_id, col_id, loud_id, voc_id]

    def _video_mat(path: Path, mw: int, mh: int, dur_us: int, mtype: str = "video", has_audio: bool = True) -> str:
        mid = _cap_uid()
        mats["videos"].append({
            "id": mid,
            "unique_id": uuid.uuid4().hex,
            "type": mtype,
            "duration": dur_us,
            "path": path.as_posix(),
            "media_path": "",
            "local_id": "",
            "has_audio": has_audio,
            "width": mw,
            "height": mh,
            "material_name": path.name,
            "source_platform": 0,
        })
        meta_videos.append({
            "create_time": now_s,
            "duration": dur_us,
            "enter_from": 0,
            "extra_info": path.name,
            "file_Path": path.as_posix(),
            "height": mh,
            "id": str(uuid.uuid4()),
            "import_time": now_s,
            "import_time_ms": now_us,
            "metetype": "photo" if mtype == "photo" else "video",
            "type": 0,
            "width": mw,
        })
        return mid

    def _scale_keyframes(start_scale: float, end_scale: float, dur_us: int) -> list[dict[str, Any]]:
        if dur_us <= 400_000 or abs(end_scale - start_scale) < 0.005:
            return []
        kf_list = [
            {"id": _cap_uid(), "time_offset": 0, "values": [round(start_scale, 3)], "curveType": "Line", "graphID": ""},
            {"id": _cap_uid(), "time_offset": dur_us, "values": [round(end_scale, 3)], "curveType": "Line", "graphID": ""},
        ]
        return [
            {"id": _cap_uid(), "property_type": "KFTypeScaleX", "material_id": "", "keyframe_list": kf_list},
            {"id": _cap_uid(), "property_type": "KFTypeScaleY", "material_id": "", "keyframe_list": [dict(k, id=_cap_uid()) for k in kf_list]},
        ]

    def _make_seg(
        mat_id: str,
        refs: list[str],
        src_start: int,
        src_dur: int,
        tgt_start: int,
        tgt_dur: int,
        *,
        scale: float = 1.0,
        tx: float = 0.0,
        ty: float = 0.0,
        volume: float = 1.0,
        render_idx: int = 0,
        keyframes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": _cap_uid(),
            "material_id": mat_id,
            "source_timerange": {"start": src_start, "duration": src_dur} if src_dur > 0 else None,
            "target_timerange": {"start": tgt_start, "duration": tgt_dur},
            "render_timerange": {"start": 0, "duration": 0},
            "desc": "",
            "state": 0,
            "speed": 1.0,
            "volume": volume,
            "last_nonzero_volume": volume,
            "visible": True,
            "render_index": render_idx,
            "extra_material_refs": refs,
            "common_keyframes": keyframes or [],
            "keyframe_refs": [],
            "uniform_scale": {"on": True, "value": scale},
            "clip": {
                "scale": {"x": scale, "y": scale},
                "rotation": 0.0,
                "rotation3d": [],
                "transform": {"x": tx, "y": ty},
                "flip": {"vertical": False, "horizontal": False},
                "alpha": 1.0,
            },
        }

    main_segments: list[dict[str, Any]] = []
    cursor_us = 0
    beat_us = max(1_800_000, int(cut_interval_s * 1_000_000))
    use_zoom = "zoom_punch" in effects or "ken_burns" in effects or not effects
    any_clip_audio = any(c.has_audio for c in clips)

    for c_idx, clip in enumerate(clips):
        clip_us = max(1_000_000, int(round(clip.duration_s * 1_000_000)))
        mat_id = _video_mat(clip.path, clip.width, clip.height, clip_us, mtype="video", has_audio=clip.has_audio)
        pos = 0
        beat_idx = 0
        while pos < clip_us:
            seg_dur = min(beat_us, clip_us - pos)
            if clip_us - (pos + seg_dur) < 900_000:
                seg_dur = clip_us - pos
            base_scale = 1.0 if fullscreen_fill else 0.92
            alt_punch = (beat_idx + c_idx) % 2 == 1
            seg_scale = (1.08 if fullscreen_fill else 1.01) if (use_zoom and alt_punch) else base_scale
            end_scale = (1.04 if fullscreen_fill else 0.96) if (use_zoom and not alt_punch) else (
                (1.12 if fullscreen_fill else 1.06) if use_zoom else seg_scale
            )
            refs = _aux_refs()
            anim_id = _cap_uid()
            mats["material_animations"].append({"id": anim_id, "type": "sticker_animation", "animations": [], "multi_language_current": "none"})
            refs.append(anim_id)
            if clip.has_audio:
                fade_c = _cap_uid()
                mats["audio_fades"].append({"id": fade_c, "type": "audio_fade", "fade_in_duration": 150_000, "fade_out_duration": 180_000})
                refs.append(fade_c)
            if transition != "cut" and main_segments:
                tr_id = _cap_uid()
                mats["transitions"].append({
                    "id": tr_id,
                    "type": "transition",
                    "name": transition,
                    "duration": 350_000,
                    "is_overlap": True,
                })
                refs.append(tr_id)
            kfs = _scale_keyframes(seg_scale, end_scale, seg_dur) if use_zoom else []
            main_segments.append(
                _make_seg(
                    mat_id,
                    refs,
                    pos,
                    seg_dur,
                    cursor_us,
                    seg_dur,
                    scale=seg_scale,
                    render_idx=c_idx + 1,
                    keyframes=kfs,
                )
            )
            pos += seg_dur
            cursor_us += seg_dur
            beat_idx += 1

    total_us = max(1_000_000, cursor_us)

    bg_mid = _video_mat(bg_path, w, h, total_us, mtype="photo", has_audio=False)
    bg_refs = _aux_refs()
    bg_seg = _make_seg(bg_mid, bg_refs, 0, total_us, 0, total_us, scale=1.0, volume=0.0, render_idx=0)
    bg_track = {"id": _cap_uid(), "type": "video", "segments": [bg_seg], "flag": 0, "attribute": 0, "name": "", "is_default_name": True}
    fg_track = {"id": _cap_uid(), "type": "video", "segments": main_segments, "flag": 2, "attribute": 0, "name": "", "is_default_name": True}

    cached_anim = _capcut_cached_anim()
    text_segments: list[dict[str, Any]] = []
    for ph in phrases:
        t_start_us = int(round(ph["start_s"] * 1_000_000))
        t_dur_us = max(500_000, int(round(ph["duration_s"] * 1_000_000)))
        if t_start_us >= total_us:
            continue
        t_dur_us = min(t_dur_us, total_us - t_start_us)
        txt_id = _cap_uid()
        fg_rgb = _hex_to_rgba(ph["color"])
        fill_norm = [round(fg_rgb[0] / 255.0, 3), round(fg_rgb[1] / 255.0, 3), round(fg_rgb[2] / 255.0, 3)]
        style_obj = {
            "fill": {"content": {"render_type": "solid", "solid": {"color": fill_norm}}},
            "bold": True,
            "size": 19 if ph.get("is_hook") else 16,
            "range": [0, len(ph["text"])],
        }
        mats["texts"].append({
            "id": txt_id,
            "name": txt_id,
            "type": "text",
            "content": json.dumps({"text": ph["text"], "styles": [style_obj]}, ensure_ascii=False),
            "recognize_text": ph["text"],
            "font_size": 19.0 if ph.get("is_hook") else 16.0,
            "text_color": ph["color"],
            "text_alpha": 1.0,
            "background_color": ph["pill"][:7] + "FF",
            "background_alpha": 0.9,
            "background_round_radius": 0.35,
            "has_shadow": True,
            "shadow_color": "#000000",
            "shadow_alpha": 0.75,
            "border_color": "#0B0C10FF",
            "border_width": 0.08,
            "alignment": 1,
            "typesetting": 0,
        })
        anim_id = _cap_uid()
        mats["material_animations"].append({
            "id": anim_id,
            "type": "sticker_animation",
            "animations": [cached_anim] if cached_anim else [],
            "multi_language_current": "none",
        })
        spd_id = _cap_uid()
        mats["speeds"].append({"id": spd_id, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        ty = 0.48 if ph.get("is_hook") else -0.52
        text_segments.append(
            _make_seg(txt_id, [anim_id, spd_id], 0, 0, t_start_us, t_dur_us, scale=1.0, ty=ty, volume=1.0, render_idx=20)
        )

    tracks = [bg_track, fg_track]

    fx_segments: list[dict[str, Any]] = []
    for item, png in [*broll_pngs, *badge_pngs]:
        if not png.is_file():
            continue
        f_st = int(round(float(item["start_s"]) * 1_000_000))
        f_dur = max(300_000, int(round(float(item["duration_s"]) * 1_000_000)))
        if f_st >= total_us:
            continue
        f_dur = min(f_dur, total_us - f_st)
        f_mid = _video_mat(png, w, h, f_dur, mtype="photo", has_audio=False)
        fx_segments.append(_make_seg(f_mid, _aux_refs(), 0, f_dur, f_st, f_dur, scale=1.0, volume=0.0, render_idx=12))
    if fx_segments:
        tracks.append({"id": _cap_uid(), "type": "video", "segments": fx_segments, "flag": 0, "attribute": 0, "name": "", "is_default_name": True})

    if text_segments:
        tracks.append({"id": _cap_uid(), "type": "text", "segments": text_segments, "flag": 1, "attribute": 0, "name": "", "is_default_name": True})

    if sfx_path and sfx_path.is_file():
        s_mid = _cap_uid()
        mats["audios"].append({"id": s_mid, "type": "sound", "path": sfx_path.as_posix(), "name": sfx_path.name, "duration": total_us})
        s_seg = _make_seg(s_mid, _aux_refs()[:4], 0, total_us, 0, total_us, volume=0.35, render_idx=0)
        tracks.append({"id": _cap_uid(), "type": "audio", "segments": [s_seg], "flag": 0, "attribute": 0, "name": "", "is_default_name": True})
        meta_music.append({"create_time": now_s, "duration": total_us, "extra_info": sfx_path.name, "file_Path": sfx_path.as_posix(), "height": 0, "id": str(uuid.uuid4()), "import_time": now_s, "import_time_ms": now_us, "metetype": "music", "type": 0, "width": 0})

    if music_path and music_path.is_file():
        a_mid = _cap_uid()
        mats["audios"].append({"id": a_mid, "type": "music", "path": music_path.as_posix(), "name": music_path.name, "duration": total_us})
        fade_id = _cap_uid()
        mats["audio_fades"].append({"id": fade_id, "type": "audio_fade", "fade_in_duration": 400_000, "fade_out_duration": 900_000})
        a_refs = _aux_refs()[:4] + [fade_id]
        bgm_vol = 0.20 if any_clip_audio else 0.32
        a_seg = _make_seg(a_mid, a_refs, 0, total_us, 0, total_us, volume=bgm_vol, render_idx=0)
        tracks.append({"id": _cap_uid(), "type": "audio", "segments": [a_seg], "flag": 0, "attribute": 0, "name": "", "is_default_name": True})
        meta_music.append({"create_time": now_s, "duration": total_us, "extra_info": music_path.name, "file_Path": music_path.as_posix(), "height": 0, "id": str(uuid.uuid4()), "import_time": now_s, "import_time_ms": now_us, "metetype": "music", "type": 0, "width": 0})

    content = {
        "id": draft_id,
        "version": 360000,
        "new_version": "116.0.0",
        "name": project_name,
        "duration": total_us,
        "create_time": now_s,
        "update_time": now_s,
        "fps": 30.0,
        "is_drop_frame_timecode": False,
        "color_space": 0,
        "ressy_profile": {"color_grade": color_grade, "transition": transition},
        "canvas_config": {"ratio": "original", "width": w, "height": h, "background": None},
        "config": {"adjust_max_index": 1, "extract_audio_last_index": 1, "lyrics_sync": True, "maintrack_adsorb": True, "material_save_mode": 0},
        "tracks": tracks,
        "materials": mats,
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [], "stickers": [], "texts": [], "videos": []},
        "keyframe_graph_list": [],
        "platform": {"app_id": 359289, "app_source": "cc", "os": "mac" if sys.platform == "darwin" else "windows"},
        "last_modified_platform": {"app_id": 359289, "app_source": "cc", "os": "mac" if sys.platform == "darwin" else "windows"},
    }
    dc_path = draft_folder / "draft_content.json"
    dc_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    meta_info = {
        "draft_cover": "draft_cover.jpg",
        "draft_fold_path": draft_folder.as_posix(),
        "draft_id": draft_id,
        "draft_materials": [{"type": 0, "value": meta_videos + meta_music}],
        "draft_name": project_name,
        "draft_root_path": drafts_root.as_posix(),
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": total_us,
    }
    (draft_folder / "draft_meta_info.json").write_text(json.dumps(meta_info, ensure_ascii=False, indent=2), encoding="utf-8")

    root_meta = drafts_root / "root_meta_info.json"
    try:
        if root_meta.is_file():
            rm = json.loads(root_meta.read_text(encoding="utf-8"))
        else:
            rm = {"all_draft_store": [], "draft_ids": 0, "root_path": drafts_root.as_posix()}
        store = [entry for entry in (rm.get("all_draft_store") or []) if entry.get("draft_name") != project_name]
        store.insert(0, {
            "draft_cover": (draft_folder / "draft_cover.jpg").as_posix(),
            "draft_fold_path": draft_folder.as_posix(),
            "draft_id": draft_id,
            "draft_json_file": dc_path.as_posix(),
            "draft_name": project_name,
            "draft_root_path": drafts_root.as_posix(),
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "tm_duration": total_us,
        })
        rm["all_draft_store"] = store
        rm["draft_ids"] = len(store)
        tmp = root_meta.with_suffix(".tmp")
        tmp.write_text(json.dumps(rm, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, root_meta)
    except Exception:
        log.debug("could not update CapCut root_meta_info.json", exc_info=True)

    return draft_folder


def _write_fcpxml(
    dst: Path,
    project_name: str,
    clips: list[ClipInfo],
    bg_path: Path,
    phrase_pngs: list[tuple[dict[str, Any], Path]],
    music_path: Path | None,
    size: tuple[int, int],
    fps: int = 30,
) -> Path:
    w, h = size
    total_s = sum(c.duration_s for c in clips)

    def fc_time(sec: float) -> str:
        frames = max(1, int(round(sec * fps)))
        return f"{frames}/{fps}s"

    res_lines = [
        f'        <format id="r1" name="FFVideoFormat{h}p{fps}" frameDuration="1/{fps}s" width="{w}" height="{h}"/>',
        f'        <asset id="r_bg" name="{xml_escape(bg_path.name)}" src="{xml_escape(bg_path.as_uri())}" start="0s" duration="{fc_time(total_s)}" hasVideo="1" format="r1"/>',
    ]
    for i, clip in enumerate(clips):
        res_lines.append(
            f'        <asset id="r_clip_{i}" name="{xml_escape(clip.path.name)}" src="{xml_escape(clip.path.as_uri())}" '
            f'start="0s" duration="{fc_time(clip.duration_s)}" hasVideo="1" hasAudio="{1 if clip.has_audio else 0}" format="r1"/>'
        )
    for idx, (_ph, png) in enumerate(phrase_pngs):
        res_lines.append(
            f'        <asset id="r_txt_{idx}" name="{xml_escape(png.name)}" src="{xml_escape(png.as_uri())}" start="0s" duration="{fc_time(total_s)}" hasVideo="1" format="r1"/>'
        )
    if music_path and music_path.is_file():
        res_lines.append(
            f'        <asset id="r_bgm" name="{xml_escape(music_path.name)}" src="{xml_escape(music_path.as_uri())}" start="0s" duration="{fc_time(total_s)}" hasAudio="1"/>'
        )

    spine_lines: list[str] = [
        f'                    <asset-clip name="{xml_escape(bg_path.name)}" ref="r_bg" offset="0s" duration="{fc_time(total_s)}" lane="-1"/>'
    ]
    cursor = 0.0
    for i, clip in enumerate(clips):
        offset_str = "0s" if cursor == 0.0 else fc_time(cursor)
        scale_val = "1.02 1.02" if i % 2 else "0.94 0.94"
        extra = f'                        <adjust-transform scale="{scale_val}"/>\n'
        if i == 0:
            for idx, (ph, png) in enumerate(phrase_pngs):
                p_off = "0s" if ph["start_s"] <= 0.0 else fc_time(ph["start_s"])
                extra += f'                        <asset-clip name="{xml_escape(png.name)}" ref="r_txt_{idx}" offset="{p_off}" duration="{fc_time(ph["duration_s"])}" lane="1"/>\n'
            if music_path and music_path.is_file():
                extra += f'                        <asset-clip name="{xml_escape(music_path.name)}" ref="r_bgm" offset="0s" duration="{fc_time(total_s)}" lane="-2"/>\n'
        spine_lines.append(
            f'                    <asset-clip name="{xml_escape(clip.path.name)}" ref="r_clip_{i}" offset="{offset_str}" duration="{fc_time(clip.duration_s)}">\n'
            f'{extra}'
            f'                    </asset-clip>'
        )
        cursor += clip.duration_s

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE fcpxml>\n'
        '<fcpxml version="1.9">\n'
        '    <resources>\n'
        + "\n".join(res_lines) + "\n"
        '    </resources>\n'
        '    <library>\n'
        f'        <event name="{xml_escape(project_name)}">\n'
        f'            <project name="{xml_escape(project_name)}">\n'
        f'                <sequence format="r1" duration="{fc_time(total_s)}">\n'
        '                    <spine>\n'
        + "\n".join(spine_lines) + "\n"
        '                    </spine>\n'
        '                </sequence>\n'
        '            </project>\n'
        '        </event>\n'
        '    </library>\n'
        '</fcpxml>\n'
    )
    dst.write_text(xml, encoding="utf-8")
    return dst


def _connect_davinci_resolve(launch_if_closed: bool = True) -> Any | None:
    mod_dir, lib_path = _davinci_script_paths()
    if mod_dir and mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    if mod_dir:
        os.environ["RESOLVE_SCRIPT_API"] = str(Path(mod_dir).parent)
    if lib_path:
        os.environ["RESOLVE_SCRIPT_LIB"] = lib_path
    try:
        import DaVinciResolveScript as bmd
    except Exception:
        return None

    resolve = None
    try:
        resolve = bmd.scriptapp("Resolve")
    except Exception:
        resolve = None

    if resolve is None and launch_if_closed:
        exe = _find_davinci_exe()
        if exe is not None:
            platform_os.open_path(exe)
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline and resolve is None:
                time.sleep(1.5)
                try:
                    resolve = bmd.scriptapp("Resolve")
                except Exception:
                    resolve = None
    return resolve


def _apply_davinci_project(
    resolve: Any,
    project_name: str,
    fcpxml_path: Path,
    media_paths: list[Path],
    srt_path: Path,
) -> bool:
    try:
        pm = resolve.GetProjectManager()
        project = pm.CreateProject(project_name) or pm.GetCurrentProject()
        if project is None:
            return False
        mp = project.GetMediaPool()
        mp.ImportMedia([str(p) for p in media_paths if p.exists()])
        timeline = mp.ImportTimelineFromFile(str(fcpxml_path))
        if timeline is None:
            clips = mp.GetRootFolder().GetClipList()
            if clips:
                timeline = mp.CreateTimelineFromClips(project_name, clips)
        if srt_path.is_file():
            mp.ImportMedia([str(srt_path)])
        resolve.OpenPage("edit")
        return timeline is not None or project is not None
    except Exception:
        log.debug("DaVinci Resolve scripting step failed", exc_info=True)
        return False


_COLOR_GRADES: dict[str, str] = {
    "vivid": "vibrance=intensity=0.24,curves=preset=medium_contrast,unsharp=5:5:0.65:5:5:0.0",
    "teal_orange": "colorbalance=rs=.06:gs=-.02:bs=-.07:rh=.05:gh=-.01:bh=-.06,vibrance=intensity=0.16,curves=preset=medium_contrast,unsharp=5:5:0.60:5:5:0.0",
    "cinematic_film": "colorbalance=rs=.03:bs=-.04,curves=preset=increase_contrast,hue=s=0.92,unsharp=3:3:0.45:3:3:0.0",
    "neutral": "",
}

_TRANSITION_XFADE: dict[str, str | None] = {
    "smooth": "fade",
    "dissolve": "dissolve",
    "zoom_whip": "slideleft",
    "flash": "fadewhite",
    "cut": None,
}


def _color_filter_expr(color_grade: str, effects: list[str]) -> str:
    grade = _COLOR_GRADES.get(color_grade, "")
    if not grade and ("color_pop" in effects or not effects):
        grade = "vibrance=intensity=0.18,unsharp=5:5:0.50:5:5:0.0"
    parts = [grade] if grade else []
    if "vignette" in effects:
        parts.append("vignette=angle=0.35")
    return ("," + ",".join(parts)) if parts else ""


_CODEC_CACHE: dict[str, tuple[str, list[str], str, list[str]]] = {}


def _detect_codecs(ffmpeg: str) -> tuple[str, list[str], str, list[str]]:
    cached = _CODEC_CACHE.get(ffmpeg)
    if cached is not None:
        return cached
    if not Path(ffmpeg).is_file():
        res = ("libx264", ["-preset", "veryfast", "-crf", "20"], "aac", [])
        _CODEC_CACHE[ffmpeg] = res
        return res
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=8, creationflags=CREATE_NO_WINDOW).stdout
    except Exception:
        out = ""

    if " libx264 " in out:
        v_enc, v_opts = "libx264", ["-preset", "veryfast", "-crf", "20"]
    elif " h264_nvenc " in out:
        v_enc, v_opts = "h264_nvenc", ["-b:v", "6M"]
    elif " h264_mf " in out:
        v_enc, v_opts = "h264_mf", ["-b:v", "6M"]
    elif " h264_qsv " in out:
        v_enc, v_opts = "h264_qsv", ["-b:v", "6M"]
    elif " h264_amf " in out:
        v_enc, v_opts = "h264_amf", ["-b:v", "6M"]
    elif " libopenh264 " in out:
        v_enc, v_opts = "libopenh264", ["-b:v", "6M"]
    else:
        v_enc, v_opts = "mpeg4", ["-q:v", "4"]

    if " aac " in out:
        a_enc, a_opts = "aac", []
    elif " aac_mf " in out:
        a_enc, a_opts = "aac_mf", ["-b:a", "192k"]
    elif " libmp3lame " in out:
        a_enc, a_opts = "libmp3lame", ["-b:a", "192k"]
    else:
        a_enc, a_opts = "mp3_mf", ["-b:a", "192k"]

    res = (v_enc, v_opts, a_enc, a_opts)
    _CODEC_CACHE[ffmpeg] = res
    return res


def _build_ffmpeg_cmd(
    ffmpeg: str,
    out_mp4: Path,
    clips: list[ClipInfo],
    bg_path: Path,
    phrase_pngs: list[tuple[dict[str, Any], Path]],
    music_path: Path | None,
    size: tuple[int, int],
    effects: list[str],
    *,
    color_grade: str = "vivid",
    transition: str = "smooth",
    broll_pngs: list[tuple[dict[str, Any], Path]] = (),
    badge_pngs: list[tuple[dict[str, Any], Path]] = (),
    sfx_path: Path | None = None,
    bg_mode: str = "auto",
) -> list[str]:
    w, h = size
    total_s = sum(c.duration_s for c in clips)
    xf_name = _TRANSITION_XFADE.get(transition, "fade")
    use_xfade = bool(xf_name and len(clips) > 1 and all(c.duration_s >= 1.2 for c in clips))
    xf_dur = 0.35
    eff_total_s = max(0.5, total_s - (xf_dur * (len(clips) - 1) if use_xfade else 0.0))

    fullscreen_fill = bg_mode in ("auto", "none") and all(_aspect_matches(c, size) for c in clips)
    clip_base_idx = 0 if fullscreen_fill else 1

    cmd = [ffmpeg, "-y"]
    if not fullscreen_fill:
        cmd += ["-loop", "1", "-t", f"{eff_total_s:.2f}", "-i", str(bg_path)]
    for clip in clips:
        cmd += ["-i", str(clip.path)]

    overlay_items: list[tuple[dict[str, Any], Path, bool]] = [
        *[(item, p, True) for item, p in broll_pngs if p.is_file()],
        *[(item, p, False) for item, p in badge_pngs if p.is_file()],
        *[(ph, p, False) for ph, p in phrase_pngs[:28] if p.is_file()],
    ]
    overlay_start_idx = clip_base_idx + len(clips)
    for _item, png, _is_slide in overlay_items:
        cmd += ["-i", str(png)]

    next_idx = overlay_start_idx + len(overlay_items)
    bgm_idx = None
    if music_path and music_path.is_file():
        bgm_idx = next_idx
        cmd += ["-i", str(music_path)]
        next_idx += 1
    sfx_idx = None
    if sfx_path and sfx_path.is_file():
        sfx_idx = next_idx
        cmd += ["-i", str(sfx_path)]

    filters: list[str] = [] if fullscreen_fill else [f"[0:v]scale={w}:{h},setsar=1[bg]"]
    vid_labels: list[str] = []
    aud_labels: list[str] = []
    fg_w, fg_h = (w, h) if fullscreen_fill else (int(w * 0.92), int(h * 0.92))
    grade_fx = _color_filter_expr(color_grade, effects)
    use_zoom = "zoom_punch" in effects or "ken_burns" in effects or not effects

    for idx, clip in enumerate(clips):
        vi = f"[vclip{idx}]"
        ci = clip_base_idx + idx
        if fullscreen_fill:
            filters.append(
                f"[{ci}:v]scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,"
                f"crop={fg_w}:{fg_h}{grade_fx},fps=30,settb=AVTB,setsar=1{vi}"
            )
        else:
            filters.append(
                f"[{ci}:v]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease,"
                f"pad={fg_w}:{fg_h}:(ow-iw)/2:(oh-ih)/2:color=black@0{grade_fx},"
                f"fps=30,settb=AVTB,setsar=1{vi}"
            )
        vid_labels.append(vi)
        if clip.has_audio:
            aud_labels.append(f"[{ci}:a]")

    if len(vid_labels) == 1:
        dur0 = clips[0].duration_s
        if use_zoom and dur0 >= 4.2:
            n_cuts = min(7, max(2, int(round(dur0 / 3.2))))
            seg_len = dur0 / n_cuts
            split_tags = [f"[sp{i}]" for i in range(n_cuts)]
            filters.append(f"{vid_labels[0]}split={n_cuts}{''.join(split_tags)}")
            cut_tags: list[str] = []
            for i in range(n_cuts):
                t0 = round(i * seg_len, 2)
                t1 = round(dur0 if i == n_cuts - 1 else (i + 1) * seg_len, 2)
                tag = f"[vz{i}]"
                if i % 2 == 1:
                    filters.append(
                        f"{split_tags[i]}trim=start={t0:.2f}:end={t1:.2f},setpts=PTS-STARTPTS,"
                        f"crop=iw/1.09:ih/1.09,scale={fg_w}:{fg_h},setsar=1{tag}"
                    )
                else:
                    filters.append(f"{split_tags[i]}trim=start={t0:.2f}:end={t1:.2f},setpts=PTS-STARTPTS,setsar=1{tag}")
                cut_tags.append(tag)
            filters.append(f"{''.join(cut_tags)}concat=n={n_cuts}:v=1:a=0[fg]")
        else:
            filters.append(f"{vid_labels[0]}null[fg]")
    elif use_xfade and xf_name:
        cur_v = vid_labels[0]
        cum = clips[0].duration_s
        for idx in range(1, len(vid_labels)):
            nxt_v = "[fg]" if idx == len(vid_labels) - 1 else f"[vx{idx}]"
            offset = max(0.1, cum - xf_dur * idx)
            filters.append(f"{cur_v}{vid_labels[idx]}xfade=transition={xf_name}:duration={xf_dur:.2f}:offset={offset:.2f}{nxt_v}")
            cur_v = nxt_v
            cum += clips[idx].duration_s
    else:
        filters.append(f"{''.join(vid_labels)}concat=n={len(vid_labels)}:v=1:a=0[fg]")

    if fullscreen_fill:
        filters.append("[fg]setsar=1[comp0]")
    else:
        filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[comp0]")

    prev = "[comp0]"
    for idx, (item, _png, _is_slide) in enumerate(overlay_items):
        nxt = f"[comp{idx + 1}]"
        s_t = max(0.0, min(float(item["start_s"]), max(0.0, eff_total_s - 0.15)))
        e_t = min(eff_total_s, s_t + max(0.20, float(item["duration_s"])))
        filters.append(
            f"{prev}[{overlay_start_idx + idx}:v]overlay=0:0:repeatlast=1:enable='between(t,{s_t:.2f},{e_t:.2f})'{nxt}"
        )
        prev = nxt
    fade_out_st = max(0.0, eff_total_s - 0.35)
    filters.append(f"{prev}fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out_st:.2f}:d=0.35,format=yuv420p[vout]")

    maps = ["-map", "[vout]"]
    has_clip_aud = bool(aud_labels and len(aud_labels) == len(clips))
    if has_clip_aud:
        if len(aud_labels) == 1:
            filters.append(f"{aud_labels[0]}anull[aclip]")
        elif use_xfade:
            cur_a = aud_labels[0]
            for idx in range(1, len(aud_labels)):
                nxt_a = "[aclip]" if idx == len(aud_labels) - 1 else f"[ax{idx}]"
                filters.append(f"{cur_a}{aud_labels[idx]}acrossfade=d={xf_dur:.2f}{nxt_a}")
                cur_a = nxt_a
        else:
            filters.append(f"{''.join(aud_labels)}concat=n={len(aud_labels)}:v=0:a=1[aclip]")

    a_fade_out = max(0.0, eff_total_s - 0.6)
    mix_inputs: list[str] = []
    if has_clip_aud:
        mix_inputs.append("[aclip]")
    if sfx_idx is not None:
        filters.append(f"[{sfx_idx}:a]atrim=0:{eff_total_s:.2f},volume=0.26[asfx]")
        mix_inputs.append("[asfx]")
    if bgm_idx is not None:
        bgm_vol = 0.18 if has_clip_aud else 0.32
        filters.append(
            f"[{bgm_idx}:a]atrim=0:{eff_total_s:.2f},volume={bgm_vol:.2f},afade=t=in:st=0:d=0.35,afade=t=out:st={a_fade_out:.2f}:d=0.55[abgm]"
        )
        mix_inputs.append("[abgm]")

    if len(mix_inputs) >= 2:
        filters.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=2,"
            f"afade=t=in:st=0:d=0.20,afade=t=out:st={a_fade_out:.2f}:d=0.45[aout]"
        )
        maps += ["-map", "[aout]"]
    elif len(mix_inputs) == 1:
        filters.append(f"{mix_inputs[0]}afade=t=in:st=0:d=0.20,afade=t=out:st={a_fade_out:.2f}:d=0.45[aout]")
        maps += ["-map", "[aout]"]

    v_enc, v_opts, a_enc, a_opts = _detect_codecs(ffmpeg)
    cmd += ["-filter_complex", ";".join(filters), *maps, "-c:v", v_enc, *v_opts]
    if "-map" in maps and "[aout]" in maps:
        cmd += ["-c:a", a_enc, *a_opts]
    cmd += ["-shortest", str(out_mp4)]
    return cmd


def _render_ffmpeg_preview(
    out_mp4: Path,
    clips: list[ClipInfo],
    bg_path: Path,
    phrase_pngs: list[tuple[dict[str, Any], Path]],
    music_path: Path | None,
    size: tuple[int, int],
    effects: list[str],
    *,
    color_grade: str = "vivid",
    transition: str = "smooth",
    broll_pngs: list[tuple[dict[str, Any], Path]] = (),
    badge_pngs: list[tuple[dict[str, Any], Path]] = (),
    sfx_path: Path | None = None,
    bg_mode: str = "auto",
) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False
    cmd = _build_ffmpeg_cmd(
        ffmpeg,
        out_mp4,
        clips,
        bg_path,
        phrase_pngs,
        music_path,
        size,
        effects,
        color_grade=color_grade,
        transition=transition,
        broll_pngs=broll_pngs,
        badge_pngs=badge_pngs,
        sfx_path=sfx_path,
        bg_mode=bg_mode,
    )
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=240, creationflags=CREATE_NO_WINDOW)
        if res.returncode != 0:
            log.warning("ffmpeg preview render exit=%s: %s", res.returncode, res.stderr.decode("utf-8", errors="replace")[-400:])
        return res.returncode == 0 and out_mp4.is_file()
    except Exception:
        log.debug("ffmpeg preview render failed", exc_info=True)
        return False


def _studio_emit(ctx: ToolContext, payload: dict[str, Any]) -> None:
    ui = getattr(ctx.services, "ui", None)
    if ui is None:
        return
    status_text = payload.get("status_text")
    if status_text and hasattr(ui, "status"):
        try:
            ui.status(str(status_text))
        except Exception:
            pass
    if hasattr(ui, "update_video_studio"):
        try:
            ui.update_video_studio(payload)
        except Exception:
            log.debug("video studio emit failed", exc_info=True)


def _timeline_tracks_payload(
    clips: list[ClipInfo],
    phrases: list[dict[str, Any]],
    *,
    music_path: Path | None,
    has_bg: bool,
    has_fx: bool,
    broll_items: list[dict[str, Any]] = (),
    badge_items: list[dict[str, Any]] = (),
    has_sfx: bool = False,
) -> tuple[list[dict[str, Any]], list[float], float]:
    v1_items: list[dict[str, Any]] = []
    a1_items: list[dict[str, Any]] = []
    transitions: list[float] = []
    cursor = 0.0
    for idx, clip in enumerate(clips):
        end = cursor + clip.duration_s
        v1_items.append({
            "start": cursor,
            "end": end,
            "text": clip.path.stem[:20],
            "keyframes": has_fx,
        })
        if clip.has_audio:
            a1_items.append({"start": cursor, "end": end, "text": tr("Voce + Audio")})
        if idx > 0:
            transitions.append(cursor)
        cursor = end
    total_s = max(1.0, cursor)
    if has_sfx:
        a1_items.append({"start": 0.0, "end": total_s, "text": "SFX · Whoosh & Pop", "color": "#EC4899"})
    if music_path and music_path.is_file():
        a1_items.append({"start": 0.0, "end": total_s, "text": f"♪ {music_path.stem[:18]}", "color": "#2DD4BF"})

    v3_items = [
        {"start": ph["start_s"], "end": ph["start_s"] + ph["duration_s"], "text": ph["text"], "keyframes": has_fx}
        for ph in phrases if ph.get("is_hook")
    ]
    v2_items = [
        {"start": ph["start_s"], "end": ph["start_s"] + ph["duration_s"], "text": ph["text"]}
        for ph in phrases if not ph.get("is_hook")
    ]
    fx_items = [
        {"start": float(it["start_s"]), "end": float(it["start_s"]) + float(it["duration_s"]), "text": f"3D {it['text']}", "keyframes": True}
        for it in broll_items
    ] + [
        {"start": float(it["start_s"]), "end": float(it["start_s"]) + float(it["duration_s"]), "text": f"★ {it['text']}"}
        for it in badge_items
    ]
    bg_items = [{"start": 0.0, "end": total_s, "text": tr("Sfondo dinamico")}] if has_bg else []
    tracks = [
        {"id": "V3", "label": "V3 TITOLI", "items": v3_items},
        {"id": "V2", "label": "V2 PAROLE", "items": v2_items},
        {"id": "FX", "label": "FX B-ROLL", "items": fx_items},
        {"id": "V1", "label": "V1 VIDEO", "items": v1_items},
        {"id": "BG", "label": "BG STUDIO", "items": bg_items},
        {"id": "A1", "label": "A1 AUDIO", "items": a1_items},
    ]
    return tracks, transitions, total_s


def _request_upload_from_ui(ctx: ToolContext, defaults: dict[str, Any]) -> dict[str, Any] | None:
    ui = getattr(ctx.services, "ui", None)
    if ui is None or not hasattr(ui, "request_video_upload"):
        return None
    done = threading.Event()
    box: dict[str, Any] = {}
    ui.request_video_upload({"event": done, "result": box, "defaults": defaults})
    if not done.wait(timeout=180):
        return None
    payload = box.get("payload")
    return payload if isinstance(payload, dict) else None


def _open_project_in_capcut(ctx: ToolContext, project_name: str) -> bool:
    ui = getattr(ctx.services, "ui", None)
    if ui is None or not hasattr(ui, "update_video_studio"):
        return False
    if sys.platform != "win32":
        return False
    try:
        from ..vision import ocr
        from . import winapi

        win = ctx.services.apps.wait_until_ready("CapCut", timeout=9.0)
        if win is None:
            return False
        winapi.focus_window(win.hwnd)
        time.sleep(2.2)
        screen = ocr.capture_and_ocr(win.hwnd)
        match = None
        for token in (project_name, project_name[:14], "Ressy_"):
            match = ocr.find_text(screen, token)
            if match is not None:
                break
        if match is not None:
            winapi.click_at(match.cx, match.cy, double=True)
            return True
    except Exception:
        log.debug("could not auto-enter CapCut draft card", exc_info=True)
    return False


def _open_editor_app(ctx: ToolContext, editor: str, draft_or_bundle: Path) -> bool:
    if editor == "capcut":
        exe = _find_capcut_exe()
        if exe is not None:
            platform_os.open_path(exe)
            _open_project_in_capcut(ctx, draft_or_bundle.name)
            return True
        entry, _ = ctx.services.apps.find("CapCut")
        if entry is not None:
            launch(entry)
            _open_project_in_capcut(ctx, draft_or_bundle.name)
            return True
        return False
    exe = _find_davinci_exe()
    if exe is not None:
        platform_os.open_path(exe)
        return True
    entry, _ = ctx.services.apps.find("DaVinci Resolve")
    if entry is not None:
        launch(entry)
        return True
    return False


def edit_video(ctx: ToolContext, args: dict) -> str:
    editor = _choose_editor(str(args.get("editor") or "auto"))
    style = str(args.get("style") or "viral")
    if style not in _STYLE_PALETTES:
        style = "viral"
    aspect_ratio = str(args.get("aspect_ratio") or "9:16")
    size = _RATIOS.get(aspect_ratio, (1080, 1920))
    title = str(args.get("title") or "").strip()
    phrases_raw = [str(p).strip() for p in (args.get("phrases") or []) if str(p).strip()]
    bg_mode = str(args.get("background") or "auto")
    effects = [str(e) for e in (args.get("effects") or ["zoom_punch", "color_pop", "vignette"])]
    transition = str(args.get("transition") or "smooth")
    color_grade = str(args.get("color_grade") or ("teal_orange" if style == "cinematic" else "vivid"))
    caption_mode = str(args.get("caption_mode") or "word")
    auto_captions = bool(args.get("auto_captions", True))
    kinetic_broll = bool(args.get("kinetic_broll", True))
    sfx_enabled = bool(args.get("sfx", kinetic_broll))
    progress_bar = bool(args.get("progress_bar", True))
    render_preview = bool(args.get("render_preview", True))
    music_arg = str(args.get("music") or "").strip()
    raw_files = [str(f).strip() for f in (args.get("files") or []) if str(f).strip()]

    if not raw_files:
        uploaded = _request_upload_from_ui(
            ctx,
            {
                "editor": editor,
                "style": style,
                "aspect_ratio": aspect_ratio,
                "transition": transition,
                "color_grade": color_grade,
                "caption_mode": caption_mode,
                "title": title,
                "phrases": phrases_raw,
                "auto_captions": auto_captions,
                "kinetic_broll": kinetic_broll,
                "progress_bar": progress_bar,
                "render_preview": render_preview,
            },
        )
        if not uploaded or not uploaded.get("files"):
            _open_editor_app(ctx, editor, videos_dir())
            ed_label = "CapCut" if editor == "capcut" else "DaVinci Resolve"
            return tr(
                "Ho aperto {editor} ed è tutto pronto! Carica o dimmi i video da editare (percorso o nome file in Download/Video): poi aggiungerò sfondo, effetti e frasi ad impatto."
            ).format(editor=ed_label)
        raw_files = [str(f) for f in uploaded.get("files") or []]
        editor = _choose_editor(str(uploaded.get("editor") or editor))
        style = str(uploaded.get("style") or style)
        aspect_ratio = str(uploaded.get("aspect_ratio") or aspect_ratio)
        size = _RATIOS.get(aspect_ratio, (1080, 1920))
        transition = str(uploaded.get("transition") or transition)
        color_grade = str(uploaded.get("color_grade") or color_grade)
        caption_mode = str(uploaded.get("caption_mode") or caption_mode)
        title = str(uploaded.get("title") or title)
        phrases_raw = list(uploaded.get("phrases") or phrases_raw)
        music_arg = str(uploaded.get("music") or music_arg)
        if "auto_captions" in uploaded:
            auto_captions = bool(uploaded["auto_captions"])
        if "kinetic_broll" in uploaded:
            kinetic_broll = bool(uploaded["kinetic_broll"])
            sfx_enabled = kinetic_broll
        if "progress_bar" in uploaded:
            progress_bar = bool(uploaded["progress_bar"])
        if "render_preview" in uploaded:
            render_preview = bool(uploaded["render_preview"])

    resolved_videos: list[Path] = []
    missing: list[str] = []
    for raw in raw_files:
        found = _resolve_media_file(raw)
        if found is None:
            missing.append(raw)
        elif found.suffix.lower() in _AUDIO_EXTS and not music_arg:
            music_arg = str(found)
        else:
            resolved_videos.append(found)
    if missing:
        hint = _recent_media_hint()
        hint_suffix = f" {hint}" if hint else ""
        raise ToolError(
            tr("Non trovo questi file video: {files}. Controlla il nome o il percorso.{hint}").format(
                files=", ".join(missing),
                hint=hint_suffix,
            )
        )
    if not resolved_videos:
        raise ToolError(tr("Carica almeno un file video per iniziare l'editing."))

    music_path = _resolve_media_file(music_arg) if music_arg else None
    clips = [probe_clip(p) for p in resolved_videos]
    total_s = sum(c.duration_s for c in clips)
    palette = _STYLE_PALETTES.get(style, _STYLE_PALETTES["viral"])
    fullscreen_fill = bg_mode in ("auto", "none") and all(_aspect_matches(c, size) for c in clips)

    project_slug = re.sub(r"[^\w-]+", "_", (args.get("project_name") or title or resolved_videos[0].stem))[:28].strip("_") or "edit"
    project_name = f"Ressy_{project_slug}_{dt.datetime.now():%H%M%S}"
    bundle_dir = videos_dir() / "Ressy Edits" / project_name
    bundle_dir.mkdir(parents=True, exist_ok=True)

    ed_label = "CapCut" if editor == "capcut" else "DaVinci Resolve"
    done_stages: list[str] = []
    _studio_emit(
        ctx,
        {
            "type": "init",
            "project_name": project_name,
            "project_dir": str(bundle_dir),
            "editor": ed_label,
            "style": style,
            "aspect_ratio": aspect_ratio,
            "duration": max(2.0, total_s),
            "stage": "analyze",
            "progress": 6,
            "message": tr("Studio avviato · analisi di {n} clip ({dur:.1f}s)…").format(n=len(clips), dur=total_s),
            "status_text": tr("Analisi clip video…"),
        },
    )

    raw_preview = bundle_dir / "preview_raw.jpg"
    has_raw = _extract_frame(clips[0].path, min(1.0, clips[0].duration_s * 0.3), raw_preview)
    tracks, transitions, dur_all = _timeline_tracks_payload(clips, [], music_path=music_path, has_bg=False, has_fx=False)
    done_stages.append("analyze")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "assets",
            "done_stages": list(done_stages),
            "progress": 20,
            "duration": dur_all,
            "playhead": 0.4,
            "tracks": tracks,
            "preview_path": str(raw_preview) if has_raw else "",
            "preview_label": tr("Sorgente ({w}×{h})").format(w=clips[0].width, h=clips[0].height),
            "message": tr("Impostazione inquadratura & preparazione color grading ({grade})…").format(grade=color_grade),
            "status_text": tr("Creo inquadratura & look…"),
        },
    )

    bg_path = bundle_dir / "background.png"
    _generate_background_image(bg_path, size, clips[0], style, bg_mode)
    stage_grade = bundle_dir / "preview_graded.png"
    _render_composite_preview(
        stage_grade,
        bg_path,
        raw_preview if has_raw else None,
        None,
        size,
        color_grade=color_grade,
        show_progress_bar=False,
        progress_frac=0.25,
        fullscreen_fill=fullscreen_fill,
    )
    tracks, transitions, dur_all = _timeline_tracks_payload(clips, [], music_path=music_path, has_bg=True, has_fx=False)
    done_stages.append("assets")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "captions",
            "done_stages": list(done_stages),
            "progress": 36,
            "playhead": dur_all * 0.25,
            "tracks": tracks,
            "preview_path": str(stage_grade),
            "preview_label": tr("Look & Color grading ({grade})").format(grade=color_grade),
            "message": tr("Trascrizione audio & sincronizzazione sottotitoli parola per parola…"),
            "status_text": tr("Sincronizzo parole…"),
        },
    )

    phrases = _plan_impact_phrases(
        ctx,
        clips,
        total_s,
        title=title,
        explicit_phrases=phrases_raw,
        style=style,
        use_stt=auto_captions,
        caption_mode=caption_mode,
    )
    phrase_pngs: list[tuple[dict[str, Any], Path]] = []
    for idx, ph in enumerate(phrases):
        p_img = bundle_dir / f"phrase_{idx + 1:02d}.png"
        _render_phrase_card(p_img, ph, size)
        phrase_pngs.append((ph, p_img))
    srt_path = bundle_dir / "captions.srt"
    _write_srt(srt_path, phrases)

    stage_caps = bundle_dir / "preview_captions.png"
    sample_card = next((p for ph, p in phrase_pngs if not ph.get("is_hook")), phrase_pngs[0][1] if phrase_pngs else None)
    _render_composite_preview(
        stage_caps,
        bg_path,
        raw_preview if has_raw else None,
        sample_card,
        size,
        color_grade=color_grade,
        show_progress_bar=progress_bar,
        progress_frac=0.50,
        fullscreen_fill=fullscreen_fill,
    )
    tracks, transitions, dur_all = _timeline_tracks_payload(clips, phrases, music_path=music_path, has_bg=True, has_fx=False)
    done_stages.append("captions")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "effects",
            "done_stages": list(done_stages),
            "progress": 52,
            "playhead": dur_all * 0.48,
            "tracks": tracks,
            "preview_path": str(stage_caps),
            "preview_label": tr("Sottotitoli dinamici ({n} card)").format(n=len(phrase_pngs)),
            "message": tr("Creazione slide 3D Grid B-Roll, badge animati, punch zoom & SFX ({tr})…").format(tr=transition),
            "status_text": tr("Creo B-Roll 3D & SFX…"),
        },
    )

    broll_items, badge_items = _plan_broll_elements(phrases, total_s, enabled=kinetic_broll)
    broll_pngs: list[tuple[dict[str, Any], Path]] = []
    for idx, sl in enumerate(broll_items):
        s_img = bundle_dir / f"broll_{idx + 1:02d}.png"
        _render_cutaway_slide(s_img, sl["text"], sl["subtitle"], sl["icon"], size, variant=sl["variant"])
        broll_pngs.append((sl, s_img))
    badge_pngs: list[tuple[dict[str, Any], Path]] = []
    for idx, bg_it in enumerate(badge_items):
        b_img = bundle_dir / f"badge_{idx + 1:02d}.png"
        _render_floating_badge(b_img, bg_it["text"], bg_it["icon"], size)
        badge_pngs.append((bg_it, b_img))

    sfx_path: Path | None = None
    if sfx_enabled:
        sfx_events: list[tuple[str, float]] = [("sub", 0.05)]
        for sl in broll_items:
            sfx_events.append(("whoosh", max(0.05, float(sl["start_s"]) - 0.14)))
        for bg_it in badge_items:
            sfx_events.append(("pop", float(bg_it["start_s"])))
        sfx_cand = bundle_dir / "sfx_hits.wav"
        if _synthesize_sfx_wav(sfx_cand, total_s, sfx_events):
            sfx_path = sfx_cand

    tracks, transitions, dur_all = _timeline_tracks_payload(
        clips,
        phrases,
        music_path=music_path,
        has_bg=True,
        has_fx=True,
        broll_items=broll_items,
        badge_items=badge_items,
        has_sfx=sfx_path is not None,
    )
    done_stages.append("effects")
    broll_preview = str(broll_pngs[-1][1]) if broll_pngs else str(stage_caps)
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "timeline",
            "done_stages": list(done_stages),
            "progress": 68,
            "playhead": dur_all * 0.68,
            "tracks": tracks,
            "transitions": transitions,
            "preview_path": broll_preview,
            "preview_label": tr("B-Roll 3D & grafiche") if broll_pngs else tr("Timeline FX"),
            "message": tr("Costruisco la timeline completa su {editor}…").format(editor=ed_label),
            "status_text": tr("Esporto timeline {editor}…").format(editor=ed_label),
        },
    )

    rendered_mp4: Path | None = None
    if editor == "capcut":
        drafts = capcut_drafts_dir()
        if drafts is None:
            _studio_emit(ctx, {"type": "error", "stage": "timeline", "message": tr("CapCut non supportato su Linux.")})
            raise ToolError(tr("CapCut su Linux non ha un client desktop nativo: scegli DaVinci Resolve oppure attiva render_preview."))
        draft_dir = _build_capcut_draft(
            drafts,
            project_name,
            clips,
            bg_path,
            phrases,
            music_path,
            size,
            palette["cut_s"],
            effects,
            color_grade=color_grade,
            transition=transition,
            broll_pngs=broll_pngs,
            badge_pngs=badge_pngs,
            sfx_path=sfx_path,
            fullscreen_fill=fullscreen_fill,
        )
        done_stages.append("timeline")
        _studio_emit(
            ctx,
            {
                "type": "stage",
                "stage": "render",
                "done_stages": list(done_stages),
                "progress": 82,
                "playhead": dur_all * 0.88,
                "message": tr("Esportazione MP4 finale & apertura automatica di CapCut…") if render_preview else tr("Apertura progetto in CapCut…"),
                "status_text": tr("Render video finale…") if render_preview else tr("Apro CapCut…"),
            },
        )
        if render_preview:
            candidate_mp4 = bundle_dir / f"{project_name}_edited.mp4"
            if _render_ffmpeg_preview(
                candidate_mp4,
                clips,
                bg_path,
                phrase_pngs,
                music_path,
                size,
                effects,
                color_grade=color_grade,
                transition=transition,
                broll_pngs=broll_pngs,
                badge_pngs=badge_pngs,
                sfx_path=sfx_path,
                bg_mode=bg_mode,
            ):
                rendered_mp4 = candidate_mp4
                final_frame = bundle_dir / "preview_final.jpg"
                if _extract_frame(rendered_mp4, min(1.2, dur_all * 0.35), final_frame):
                    _studio_emit(
                        ctx,
                        {
                            "type": "preview",
                            "progress": 95,
                            "preview_path": str(final_frame),
                            "preview_label": tr("Render finale MP4"),
                        },
                    )
        opened = _open_editor_app(ctx, "capcut", draft_dir)
        done_stages.append("render")
        _studio_emit(
            ctx,
            {
                "type": "done",
                "done_stages": list(done_stages),
                "progress": 100,
                "playhead": dur_all,
                "output_mp4": str(rendered_mp4) if rendered_mp4 else "",
                "project_dir": str(draft_dir if not rendered_mp4 else bundle_dir),
                "message": tr("Editing completato su CapCut!"),
                "status_text": tr("Video pronto!"),
            },
        )
        preview_note = tr(" Anteprima esportata: {path}.").format(path=rendered_mp4.name) if rendered_mp4 else ""
        if opened:
            return tr(
                "Editing completato su CapCut! Ho creato il progetto «{project}» con {clips} clip, sfondo personalizzato, {phrases} frasi ad impatto, effetti e ritmo ({ratio}).{preview} CapCut è aperto con il progetto pronto."
            ).format(project=project_name, clips=len(clips), phrases=len(phrases), ratio=aspect_ratio, preview=preview_note)
        return tr(
            "Progetto CapCut «{project}» creato con successo ({clips} clip, sfondo, {phrases} frasi ad impatto, effetti) in {path}.{preview}"
        ).format(project=project_name, clips=len(clips), phrases=len(phrases), path=str(draft_dir), preview=preview_note)

    fcpxml_path = _write_fcpxml(bundle_dir / "timeline.fcpxml", project_name, clips, bg_path, phrase_pngs, music_path, size)
    media_all = [bg_path, *[c.path for c in clips], *[p for _, p in phrase_pngs], *[p for _, p in broll_pngs], *[p for _, p in badge_pngs]]
    if sfx_path:
        media_all.append(sfx_path)
    if music_path:
        media_all.append(music_path)
    done_stages.append("timeline")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "render",
            "done_stages": list(done_stages),
            "progress": 82,
            "playhead": dur_all * 0.88,
            "message": tr("Invio timeline a DaVinci Resolve & render anteprima…"),
            "status_text": tr("Apro DaVinci Resolve…"),
        },
    )
    if render_preview:
        candidate_mp4 = bundle_dir / f"{project_name}_edited.mp4"
        if _render_ffmpeg_preview(
            candidate_mp4,
            clips,
            bg_path,
            phrase_pngs,
            music_path,
            size,
            effects,
            color_grade=color_grade,
            transition=transition,
            broll_pngs=broll_pngs,
            badge_pngs=badge_pngs,
            sfx_path=sfx_path,
            bg_mode=bg_mode,
        ):
            rendered_mp4 = candidate_mp4
            final_frame = bundle_dir / "preview_final.jpg"
            if _extract_frame(rendered_mp4, min(1.2, dur_all * 0.35), final_frame):
                _studio_emit(
                    ctx,
                    {
                        "type": "preview",
                        "progress": 95,
                        "preview_path": str(final_frame),
                        "preview_label": tr("Render finale MP4"),
                    },
                )
    resolve = _connect_davinci_resolve(launch_if_closed=True)
    connected = False
    if resolve is not None:
        connected = _apply_davinci_project(resolve, project_name, fcpxml_path, media_all, srt_path)
    if not connected:
        _open_editor_app(ctx, "davinci", bundle_dir)
    done_stages.append("render")
    _studio_emit(
        ctx,
        {
            "type": "done",
            "done_stages": list(done_stages),
            "progress": 100,
            "playhead": dur_all,
            "output_mp4": str(rendered_mp4) if rendered_mp4 else "",
            "project_dir": str(bundle_dir),
            "message": tr("Editing completato!"),
            "status_text": tr("Video pronto!"),
        },
    )
    preview_note = tr(" Anteprima MP4 esportata: {path}.").format(path=rendered_mp4.name) if rendered_mp4 else ""
    if connected:
        return tr(
            "Editing completato su DaVinci Resolve! Progetto «{project}» aperto nella pagina Edit con {clips} clip, sfondo, {phrases} frasi ad impatto e sottotitoli ({ratio}).{preview}"
        ).format(project=project_name, clips=len(clips), phrases=len(phrases), ratio=aspect_ratio, preview=preview_note)
    installed = _find_davinci_exe() is not None
    if installed:
        return tr(
            "Ho preparato il progetto DaVinci Resolve «{project}» ({clips} clip, sfondo, {phrases} frasi ad impatto ed effetti) e ho aperto DaVinci Resolve: importa {xml} da File > Import > Timeline per caricare la timeline completa.{preview}"
        ).format(project=project_name, clips=len(clips), phrases=len(phrases), xml=str(fcpxml_path), preview=preview_note)
    return tr(
        "DaVinci Resolve non sembra installato su questo PC, ma ho preparato tutto il pacchetto timeline (.fcpxml, sfondo, frasi PNG ed .srt) in {folder}.{preview}"
    ).format(folder=str(bundle_dir), preview=preview_note)


TOOLS = [
    Tool(
        "edit_video",
        "Edita video live stile TikTok/Reels con Studio (CapCut/DaVinci, sottotitoli sync, B-Roll 3D, SFX, MP4). "
        "Vuoto apre upload: mai inventare file.",
        params(
            {
                "editor": {"type": "string", "enum": ["auto", "capcut", "davinci"]},
                "files": {"type": "array", "items": {"type": "string"}, "description": "percorsi/nomi reali; vuoto per upload"},
                "style": {"type": "string", "enum": ["viral", "cinematic", "gaming", "vlog", "minimal"]},
                "aspect_ratio": {"type": "string", "enum": ["9:16", "16:9", "1:1"]},
                "transition": {"type": "string", "enum": ["smooth", "dissolve", "zoom_whip", "flash", "cut"]},
                "color_grade": {"type": "string", "enum": ["vivid", "teal_orange", "cinematic_film", "neutral"]},
                "caption_mode": {"type": "string", "enum": ["word", "phrase"]},
                "title": {"type": "string"},
                "phrases": {"type": "array", "items": {"type": "string"}},
                "background": {"type": "string", "enum": ["auto", "blur", "neon_grid", "dark_gradient", "none"]},
                "effects": {"type": "array", "items": {"type": "string"}},
                "music": {"type": "string"},
                "auto_captions": {"type": "boolean"},
                "kinetic_broll": {"type": "boolean"},
                "progress_bar": {"type": "boolean"},
                "render_preview": {"type": "boolean"},
                "project_name": {"type": "string"},
            },
        ),
        edit_video,
        timeout=240,
        uses_screen=True,
    ),
]
