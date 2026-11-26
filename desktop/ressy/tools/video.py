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


def _transcribe_clip_phrases(ctx: ToolContext, clip: ClipInfo) -> list[str]:
    ffmpeg = find_ffmpeg()
    stt = getattr(ctx.services, "stt", None)
    if not ffmpeg or stt is None or not clip.has_audio or clip.duration_s > 180:
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
        if hasattr(stt, "transcribe_pcm"):
            res = asyncio.run(stt.transcribe_pcm(pcm, 16000, lenient=True))
            text = str(getattr(res, "text", "") or "")
        elif hasattr(stt, "transcribe_sync"):
            text = stt.transcribe_sync(pcm, 16000)
        else:
            text = ""
        words = [w.strip() for w in (text or "").split() if w.strip()]
        if not words:
            return []
        out: list[str] = []
        for i in range(0, len(words), 4):
            chunk = " ".join(words[i:i + 4]).upper()
            if chunk:
                out.append(chunk)
        return out[:10]
    except Exception:
        log.debug("video STT phrase extraction skipped", exc_info=True)
        return []
    finally:
        if wav_file is not None:
            wav_file.unlink(missing_ok=True)


def _plan_impact_phrases(
    ctx: ToolContext,
    clips: list[ClipInfo],
    total_s: float,
    *,
    title: str,
    explicit_phrases: list[str],
    style: str,
    use_stt: bool = True,
) -> list[dict[str, Any]]:
    palette = _STYLE_PALETTES.get(style, _STYLE_PALETTES["viral"])
    colors = palette["text_colors"]
    phrases: list[str] = [p.strip().upper() for p in explicit_phrases if p.strip()]
    if not phrases and use_stt:
        for clip in clips[:2]:
            phrases.extend(_transcribe_clip_phrases(ctx, clip))
            if len(phrases) >= 6:
                break
    if not phrases:
        settings = getattr(ctx.services, "settings", None)
        lang = getattr(settings, "language", "it") if settings else "it"
        defaults = palette["phrases_en"] if lang == "en" else palette["phrases_it"]
        phrases = list(defaults)
    if title.strip():
        hook = title.strip().upper()
        if not phrases or phrases[0] != hook:
            phrases.insert(0, hook)
    count = min(max(1, len(phrases)), max(2, int(total_s / 2.2)))
    phrases = phrases[:count]
    slot = total_s / max(1, len(phrases))
    timeline: list[dict[str, Any]] = []
    for idx, text in enumerate(phrases):
        start = round(idx * slot + (0.08 if idx == 0 else 0.15), 2)
        dur = round(max(1.2, slot - 0.22), 2)
        if start + dur > total_s:
            dur = max(0.8, round(total_s - start, 2))
        timeline.append({
            "index": idx,
            "text": text,
            "start_s": start,
            "duration_s": dur,
            "color": colors[idx % len(colors)],
            "pill": palette["pill_bg"],
            "is_hook": idx == 0,
        })
    return timeline


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
) -> None:
    try:
        pw, ph = 540, max(304, int(round(540 * (size[1] / max(1, size[0])))))
        if bg_path.is_file():
            canvas = Image.open(bg_path).convert("RGBA").resize((pw, ph), Image.Resampling.LANCZOS)
        else:
            canvas = Image.new("RGBA", (pw, ph), (16, 17, 24, 255))

        if raw_frame is not None and raw_frame.is_file():
            fg = _grade_pil_image(Image.open(raw_frame), color_grade)
            fg_w, fg_h = int(pw * 0.90), int(ph * 0.90)
            scale = min(fg_w / max(1, fg.width), fg_h / max(1, fg.height))
            nw, nh = max(2, int(fg.width * scale)), max(2, int(fg.height * scale))
            fg_rs = fg.resize((nw, nh), Image.Resampling.LANCZOS).convert("RGBA")
            x = (pw - nw) // 2
            y = (ph - nh) // 2
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
    draw = ImageDraw.Draw(img)
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
            base_scale = 0.92
            alt_punch = (beat_idx + c_idx) % 2 == 1
            seg_scale = 1.01 if (use_zoom and alt_punch) else base_scale
            end_scale = 0.96 if (use_zoom and not alt_punch) else (1.06 if use_zoom else seg_scale)
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
    if text_segments:
        tracks.append({"id": _cap_uid(), "type": "text", "segments": text_segments, "flag": 1, "attribute": 0, "name": "", "is_default_name": True})

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
    "vivid": "eq=contrast=1.10:brightness=0.02:saturation=1.22,unsharp=5:5:0.65:5:5:0.0",
    "teal_orange": "colorbalance=rs=.06:gs=-.02:bs=-.07:rh=.05:gh=-.01:bh=-.06,eq=contrast=1.12:saturation=1.15,unsharp=5:5:0.60:5:5:0.0",
    "cinematic_film": "eq=contrast=1.14:brightness=-0.02:saturation=0.92,colorbalance=rs=.03:bs=-.04,unsharp=3:3:0.45:3:3:0.0",
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
        grade = "eq=contrast=1.08:saturation=1.18"
    parts = [grade] if grade else []
    if "vignette" in effects:
        parts.append("vignette=angle=0.35")
    return ("," + ",".join(parts)) if parts else ""


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
) -> list[str]:
    w, h = size
    total_s = sum(c.duration_s for c in clips)
    xf_name = _TRANSITION_XFADE.get(transition, "fade")
    use_xfade = bool(xf_name and len(clips) > 1 and all(c.duration_s >= 1.2 for c in clips))
    xf_dur = 0.35
    eff_total_s = max(0.5, total_s - (xf_dur * (len(clips) - 1) if use_xfade else 0.0))

    cmd = [ffmpeg, "-y", "-loop", "1", "-t", f"{eff_total_s:.2f}", "-i", str(bg_path)]
    for clip in clips:
        cmd += ["-i", str(clip.path)]
    for _ph, png in phrase_pngs:
        cmd += ["-loop", "1", "-t", f"{eff_total_s:.2f}", "-i", str(png)]
    bgm_idx = None
    if music_path and music_path.is_file():
        bgm_idx = 1 + len(clips) + len(phrase_pngs)
        cmd += ["-i", str(music_path)]

    filters: list[str] = [f"[0:v]scale={w}:{h},setsar=1[bg]"]
    vid_labels: list[str] = []
    aud_labels: list[str] = []
    fg_w, fg_h = int(w * 0.92), int(h * 0.92)
    grade_fx = _color_filter_expr(color_grade, effects)
    for idx, clip in enumerate(clips):
        vi = f"[vclip{idx}]"
        filters.append(
            f"[{idx + 1}:v]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease,"
            f"pad={fg_w}:{fg_h}:(ow-iw)/2:(oh-ih)/2:color=black@0{grade_fx},"
            f"fps=30,settb=AVTB,setsar=1{vi}"
        )
        vid_labels.append(vi)
        if clip.has_audio:
            aud_labels.append(f"[{idx + 1}:a]")

    if len(vid_labels) == 1:
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

    filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[comp0]")
    prev = "[comp0]"
    base_txt_idx = 1 + len(clips)
    for idx, (ph, _png) in enumerate(phrase_pngs):
        nxt = f"[comp{idx + 1}]"
        s_t = min(ph["start_s"], max(0.0, eff_total_s - 0.3))
        e_t = min(eff_total_s, ph["start_s"] + ph["duration_s"])
        filters.append(f"{prev}[{base_txt_idx + idx}:v]overlay=0:0:enable='between(t,{s_t:.2f},{e_t:.2f})'{nxt}")
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
    if bgm_idx is not None and has_clip_aud:
        filters.append(f"[{bgm_idx}:a]atrim=0:{eff_total_s:.2f},volume=0.20,afade=t=in:st=0:d=0.35,afade=t=out:st={a_fade_out:.2f}:d=0.55[abgm]")
        filters.append("[aclip][abgm]amix=inputs=2:duration=first:dropout_transition=2,afade=t=in:st=0:d=0.20[aout]")
        maps += ["-map", "[aout]"]
    elif bgm_idx is not None:
        filters.append(f"[{bgm_idx}:a]atrim=0:{eff_total_s:.2f},volume=0.32,afade=t=in:st=0:d=0.35,afade=t=out:st={a_fade_out:.2f}:d=0.55[aout]")
        maps += ["-map", "[aout]"]
    elif has_clip_aud:
        filters.append(f"[aclip]afade=t=in:st=0:d=0.20,afade=t=out:st={a_fade_out:.2f}:d=0.50[aout]")
        maps += ["-map", "[aout]"]

    cmd += ["-filter_complex", ";".join(filters), *maps, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest", str(out_mp4)]
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
    )
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=180, creationflags=CREATE_NO_WINDOW)
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
            a1_items.append({"start": cursor, "end": end, "text": tr("Audio")})
        if idx > 0:
            transitions.append(cursor)
        cursor = end
    total_s = max(1.0, cursor)
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
    bg_items = [{"start": 0.0, "end": total_s, "text": tr("Sfondo dinamico")}] if has_bg else []
    tracks = [
        {"id": "V3", "label": "V3 TITOLI", "items": v3_items},
        {"id": "V2", "label": "V2 SUBS", "items": v2_items},
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
    auto_captions = bool(args.get("auto_captions", True))
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
                "title": title,
                "phrases": phrases_raw,
                "auto_captions": auto_captions,
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
        title = str(uploaded.get("title") or title)
        phrases_raw = list(uploaded.get("phrases") or phrases_raw)
        music_arg = str(uploaded.get("music") or music_arg)
        if "auto_captions" in uploaded:
            auto_captions = bool(uploaded["auto_captions"])
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
            "message": tr("Creazione sfondo dinamico & preparazione color grading ({grade})…").format(grade=color_grade),
            "status_text": tr("Creo sfondo & look…"),
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
    )
    tracks, transitions, dur_all = _timeline_tracks_payload(clips, [], music_path=music_path, has_bg=True, has_fx=False)
    done_stages.append("assets")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "captions",
            "done_stages": list(done_stages),
            "progress": 38,
            "playhead": dur_all * 0.25,
            "tracks": tracks,
            "preview_path": str(stage_grade),
            "preview_label": tr("Sfondo & color grading ({grade})").format(grade=color_grade),
            "message": tr("Trascrizione audio & generazione titoli / sottotitoli sincronizzati…"),
            "status_text": tr("Genero sottotitoli…"),
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
    )
    phrase_pngs: list[tuple[dict[str, Any], Path]] = []
    for idx, ph in enumerate(phrases):
        p_img = bundle_dir / f"phrase_{idx + 1:02d}.png"
        _render_phrase_card(p_img, ph, size)
        phrase_pngs.append((ph, p_img))
    srt_path = bundle_dir / "captions.srt"
    _write_srt(srt_path, phrases)

    stage_caps = bundle_dir / "preview_captions.png"
    _render_composite_preview(
        stage_caps,
        bg_path,
        raw_preview if has_raw else None,
        phrase_pngs[0][1] if phrase_pngs else None,
        size,
        color_grade=color_grade,
        show_progress_bar=progress_bar,
        progress_frac=0.52,
    )
    tracks, transitions, dur_all = _timeline_tracks_payload(clips, phrases, music_path=music_path, has_bg=True, has_fx=False)
    done_stages.append("captions")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "effects",
            "done_stages": list(done_stages),
            "progress": 56,
            "playhead": dur_all * 0.5,
            "tracks": tracks,
            "preview_path": str(stage_caps),
            "preview_label": tr("Compositing titoli ({n} card)").format(n=len(phrase_pngs)),
            "message": tr("Applico keyframe zoom, transizioni ({tr}) e auto-ducking audio…").format(tr=transition),
            "status_text": tr("Applico transizioni & FX…"),
        },
    )

    tracks, transitions, dur_all = _timeline_tracks_payload(clips, phrases, music_path=music_path, has_bg=True, has_fx=True)
    done_stages.append("effects")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "timeline",
            "done_stages": list(done_stages),
            "progress": 70,
            "playhead": dur_all * 0.7,
            "tracks": tracks,
            "transitions": transitions,
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
        )
        done_stages.append("timeline")
        _studio_emit(
            ctx,
            {
                "type": "stage",
                "stage": "render",
                "done_stages": list(done_stages),
                "progress": 84,
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
    media_all = [bg_path, *[c.path for c in clips], *[p for _, p in phrase_pngs]]
    if music_path:
        media_all.append(music_path)
    done_stages.append("timeline")
    _studio_emit(
        ctx,
        {
            "type": "stage",
            "stage": "render",
            "done_stages": list(done_stages),
            "progress": 84,
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
        "Edita video live con Studio su CapCut o DaVinci (sfondi, grading, transizioni, keyframe, testi, MP4). "
        "Vuoto apre upload: mai inventare file.",
        params(
            {
                "editor": {"type": "string", "enum": ["auto", "capcut", "davinci"]},
                "files": {"type": "array", "items": {"type": "string"}, "description": "percorsi/nomi reali; vuoto per upload"},
                "style": {"type": "string", "enum": ["viral", "cinematic", "gaming", "vlog", "minimal"]},
                "aspect_ratio": {"type": "string", "enum": ["9:16", "16:9", "1:1"]},
                "transition": {"type": "string", "enum": ["smooth", "dissolve", "zoom_whip", "flash", "cut"]},
                "color_grade": {"type": "string", "enum": ["vivid", "teal_orange", "cinematic_film", "neutral"]},
                "title": {"type": "string"},
                "phrases": {"type": "array", "items": {"type": "string"}},
                "background": {"type": "string", "enum": ["auto", "blur", "neon_grid", "dark_gradient", "none"]},
                "effects": {"type": "array", "items": {"type": "string"}},
                "music": {"type": "string"},
                "auto_captions": {"type": "boolean"},
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
