from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..storage import LinkRecord


@dataclass(frozen=True)
class Identity:

    platform: str
    user_id: str
    chat_id: str
    display: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.platform, self.user_id)


@dataclass
class Attachment:
    data: bytes
    filename: str
    mime: str


@dataclass
class OutgoingReply:
    text: str = ""
    transcript: str | None = None
    voice: Attachment | None = None
    images: list[Attachment] = field(default_factory=list)

    def compose_text(self) -> str:
        parts: list[str] = []
        if self.transcript:
            parts.append(f"🎙️ «{self.transcript}»")
        if self.text:
            parts.append(self.text)
        return "\n\n".join(parts)


class Frontend(Protocol):
    platform: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def notify(self, link: LinkRecord, reply: OutgoingReply) -> None: ...

    def bot_info(self) -> dict: ...

    def pair_hint(self, code: str) -> dict: ...


def split_text(text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
