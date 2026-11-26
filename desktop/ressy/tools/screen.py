from __future__ import annotations

import asyncio
import datetime as dt
import io
import logging
import threading
from dataclasses import dataclass

from ..paths import pictures_dir
from ..speech.textnorm import normalize, similarity
from .registry import Attachment

log = logging.getLogger("ressy.screen")

MAX_SIDE = 2560


@dataclass(frozen=True)
class Word:
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


@dataclass(frozen=True)
class Line:
    text: str
    words: tuple[Word, ...]

    @property
    def box(self) -> tuple[int, int, int, int]:
        xs = [w.x for w in self.words] + [w.x + w.w for w in self.words]
        ys = [w.y for w in self.words] + [w.y + w.h for w in self.words]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def center(self) -> tuple[int, int]:
        x0, y0, x1, y1 = self.box
        return (x0 + x1) // 2, (y0 + y1) // 2


def grab(region: tuple[int, int, int, int] | None = None):
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=region, all_screens=True)


def virtual_origin() -> tuple[int, int]:
    import sys

    if sys.platform == "win32":
        from .winapi import user32

        return int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77))
    try:
        import mss

        with mss.mss() as sct:
            mon = sct.monitors[0]
            return int(mon.get("left", 0)), int(mon.get("top", 0))
    except Exception:
        return 0, 0


def save_screenshot(image, prefix: str = "screenshot"):
    folder = pictures_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{prefix}-{dt.datetime.now():%Y%m%d-%H%M%S}.png"
    image.save(path, "PNG")
    return path


def as_attachment(image, name: str) -> Attachment:
    preview = image.convert("RGB")
    if preview.width > MAX_SIDE:
        ratio = MAX_SIDE / preview.width
        preview = preview.resize((MAX_SIDE, max(1, int(preview.height * ratio))))
    buffer = io.BytesIO()
    preview.save(buffer, "JPEG", quality=80, optimize=True)
    return Attachment(buffer.getvalue(), name, "image/jpeg")


def ocr_available() -> bool:
    import sys

    if sys.platform != "win32":
        from .platform_os import tesseract_available

        return tesseract_available()
    try:
        from winrt.windows.media.ocr import OcrEngine
    except Exception:
        return False
    return True


async def _recognize(image) -> list[Line]:
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("nessuna lingua OCR installata in Windows")
    rgba = image.convert("RGBA")
    scale = 2 if rgba.width * 2 <= OcrEngine.max_image_dimension and rgba.height * 2 <= OcrEngine.max_image_dimension else 1
    if scale != 1:
        rgba = rgba.resize((rgba.width * scale, rgba.height * scale))
    b, g, r, a = (rgba.getchannel(c) for c in "BGRA")
    from PIL import Image

    bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()
    writer = DataWriter()
    writer.write_bytes(bgra)
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, rgba.width, rgba.height, BitmapAlphaMode.PREMULTIPLIED
    )
    result = await engine.recognize_async(bitmap)
    lines: list[Line] = []
    for line in result.lines:
        words = tuple(
            Word(
                w.text,
                int(w.bounding_rect.x / scale),
                int(w.bounding_rect.y / scale),
                int(w.bounding_rect.width / scale),
                int(w.bounding_rect.height / scale),
            )
            for w in line.words
        )
        if words:
            lines.append(Line(line.text, words))
    return lines


def read_text(region: tuple[int, int, int, int] | None = None) -> list[Line]:
    import sys

    image = grab(region)
    if region is not None:
        dx, dy = region[0], region[1]
    else:
        dx, dy = virtual_origin()
    if sys.platform != "win32":
        from .platform_os import ocr_with_tesseract

        return [
            Line(text, tuple(Word(w, x + dx, y + dy, ww, hh) for w, x, y, ww, hh in words))
            for text, words in ocr_with_tesseract(image)
        ]
    lines = _run(_recognize(image))
    return [
        Line(line.text, tuple(Word(w.text, w.x + dx, w.y + dy, w.w, w.h) for w in line.words)) for line in lines
    ]


def _run(coro):
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=target, name="ocr", daemon=True)
    thread.start()
    thread.join(30)
    if "error" in box:
        raise box["error"]
    if "value" not in box:
        raise TimeoutError("OCR troppo lento")
    return box["value"]


def find_text(lines: list[Line], wanted: str, threshold: float = 0.78) -> tuple[float, Line, tuple[int, int]] | None:
    target = normalize(wanted).replace(" ", "")
    if not target:
        return None
    best: tuple[float, Line, tuple[int, int]] | None = None
    for line in lines:
        words = line.words
        for start in range(len(words)):
            joined = ""
            for end in range(start, min(len(words), start + 8)):
                joined += normalize(words[end].text).replace(" ", "")
                if not joined:
                    continue
                score = 1.0 if joined == target else similarity(joined, target)
                if score >= threshold and (best is None or score > best[0]):
                    x0 = words[start].x
                    y0 = min(w.y for w in words[start : end + 1])
                    x1 = words[end].x + words[end].w
                    y1 = max(w.y + w.h for w in words[start : end + 1])
                    best = (score, line, ((x0 + x1) // 2, (y0 + y1) // 2))
                if len(joined) > len(target) + 4:
                    break
    return best
