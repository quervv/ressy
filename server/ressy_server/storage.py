from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from .protocol import PAIR_ALPHABET, PAIR_CODE_LEN

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id         TEXT PRIMARY KEY,
    secret_hash      TEXT NOT NULL,
    name             TEXT NOT NULL DEFAULT '',
    version          TEXT NOT NULL DEFAULT '',
    created_at       REAL NOT NULL,
    last_seen        REAL,
    offline_notified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS links (
    platform         TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    chat_id          TEXT NOT NULL,
    display          TEXT NOT NULL DEFAULT '',
    agent_id         TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    presence_alerts  INTEGER NOT NULL DEFAULT 1,
    voice_mode       INTEGER NOT NULL DEFAULT 0,
    linked_at        REAL NOT NULL,
    PRIMARY KEY (platform, user_id)
);

CREATE INDEX IF NOT EXISTS links_by_agent ON links(agent_id);

CREATE TABLE IF NOT EXISTS pair_codes (
    code        TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    expires_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS pair_codes_by_agent ON pair_codes(agent_id);

CREATE TABLE IF NOT EXISTS blocked (
    platform    TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    display     TEXT NOT NULL DEFAULT '',
    blocked_at  REAL NOT NULL,
    PRIMARY KEY (platform, user_id)
);
"""

VOICE_AUTO = 0
VOICE_ALWAYS = 1
VOICE_NEVER = 2


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    secret_hash: str
    name: str
    version: str
    created_at: float
    last_seen: float | None
    offline_notified: bool


@dataclass(frozen=True)
class LinkRecord:
    platform: str
    user_id: str
    chat_id: str
    display: str
    agent_id: str
    presence_alerts: bool = True
    voice_mode: int = VOICE_AUTO
    linked_at: float = 0.0

    def public(self) -> dict:
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "display": self.display,
            "linked_at": self.linked_at,
        }


def _agent(row: aiosqlite.Row | None) -> AgentRecord | None:
    if row is None:
        return None
    return AgentRecord(
        agent_id=row["agent_id"],
        secret_hash=row["secret_hash"],
        name=row["name"],
        version=row["version"],
        created_at=row["created_at"],
        last_seen=row["last_seen"],
        offline_notified=bool(row["offline_notified"]),
    )


def _link(row: aiosqlite.Row | None) -> LinkRecord | None:
    if row is None:
        return None
    return LinkRecord(
        platform=row["platform"],
        user_id=row["user_id"],
        chat_id=row["chat_id"],
        display=row["display"],
        agent_id=row["agent_id"],
        presence_alerts=bool(row["presence_alerts"]),
        voice_mode=int(row["voice_mode"]),
        linked_at=row["linked_at"],
    )


class Store:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._write_lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: str) -> "Store":
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(path)
        db.row_factory = aiosqlite.Row
        if path != ":memory:":
            await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA)
        await db.commit()
        return cls(db)

    async def close(self) -> None:
        await self._db.close()

    async def get_agent(self, agent_id: str) -> AgentRecord | None:
        async with self._db.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)) as cur:
            return _agent(await cur.fetchone())

    async def create_agent(self, agent_id: str, secret_hash: str, name: str, version: str) -> AgentRecord:
        now = time.time()
        async with self._write_lock:
            await self._db.execute(
                "INSERT INTO agents (agent_id, secret_hash, name, version, created_at, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (agent_id, secret_hash, name, version, now, now),
            )
            await self._db.commit()
        record = await self.get_agent(agent_id)
        assert record is not None
        return record

    async def touch_agent(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        version: str | None = None,
        seen: float | None = None,
    ) -> None:
        sets: list[str] = ["last_seen = ?"]
        params: list[object] = [time.time() if seen is None else seen]
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if version is not None:
            sets.append("version = ?")
            params.append(version)
        params.append(agent_id)
        async with self._write_lock:
            await self._db.execute(f"UPDATE agents SET {', '.join(sets)} WHERE agent_id = ?", params)
            await self._db.commit()

    async def set_offline_notified(self, agent_id: str, value: bool) -> None:
        async with self._write_lock:
            await self._db.execute(
                "UPDATE agents SET offline_notified = ? WHERE agent_id = ?", (1 if value else 0, agent_id)
            )
            await self._db.commit()

    async def agents_with_links_not_notified(self) -> list[AgentRecord]:
        sql = (
            "SELECT * FROM agents WHERE offline_notified = 0 "
            "AND agent_id IN (SELECT DISTINCT agent_id FROM links)"
        )
        async with self._db.execute(sql) as cur:
            return [a for a in (_agent(r) for r in await cur.fetchall()) if a is not None]

    async def count_agents(self) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM agents") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def get_link(self, platform: str, user_id: str) -> LinkRecord | None:
        async with self._db.execute(
            "SELECT * FROM links WHERE platform = ? AND user_id = ?", (platform, user_id)
        ) as cur:
            return _link(await cur.fetchone())

    async def upsert_link(self, link: LinkRecord) -> None:
        async with self._write_lock:
            await self._db.execute(
                "INSERT INTO links (platform, user_id, chat_id, display, agent_id, presence_alerts, voice_mode, linked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, user_id) DO UPDATE SET "
                "chat_id = excluded.chat_id, display = excluded.display, agent_id = excluded.agent_id, "
                "presence_alerts = excluded.presence_alerts, voice_mode = excluded.voice_mode, "
                "linked_at = excluded.linked_at",
                (
                    link.platform,
                    link.user_id,
                    link.chat_id,
                    link.display,
                    link.agent_id,
                    1 if link.presence_alerts else 0,
                    int(link.voice_mode),
                    link.linked_at,
                ),
            )
            await self._db.commit()

    async def update_link_contact(self, platform: str, user_id: str, chat_id: str, display: str) -> None:
        async with self._write_lock:
            await self._db.execute(
                "UPDATE links SET chat_id = ?, display = ? WHERE platform = ? AND user_id = ?",
                (chat_id, display, platform, user_id),
            )
            await self._db.commit()

    async def set_link_prefs(
        self,
        platform: str,
        user_id: str,
        *,
        presence_alerts: bool | None = None,
        voice_mode: int | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[object] = []
        if presence_alerts is not None:
            sets.append("presence_alerts = ?")
            params.append(1 if presence_alerts else 0)
        if voice_mode is not None:
            sets.append("voice_mode = ?")
            params.append(int(voice_mode))
        if not sets:
            return
        params.extend([platform, user_id])
        async with self._write_lock:
            await self._db.execute(
                f"UPDATE links SET {', '.join(sets)} WHERE platform = ? AND user_id = ?", params
            )
            await self._db.commit()

    async def delete_link(self, platform: str, user_id: str) -> LinkRecord | None:
        existing = await self.get_link(platform, user_id)
        if existing is None:
            return None
        async with self._write_lock:
            await self._db.execute("DELETE FROM links WHERE platform = ? AND user_id = ?", (platform, user_id))
            await self._db.commit()
        return existing

    async def links_for_agent(self, agent_id: str) -> list[LinkRecord]:
        async with self._db.execute(
            "SELECT * FROM links WHERE agent_id = ? ORDER BY linked_at", (agent_id,)
        ) as cur:
            return [link for link in (_link(r) for r in await cur.fetchall()) if link is not None]

    async def owner(self, platform: str) -> LinkRecord | None:
        async with self._db.execute(
            "SELECT * FROM links WHERE platform = ? ORDER BY linked_at LIMIT 1", (platform,)
        ) as cur:
            return _link(await cur.fetchone())

    async def is_blocked(self, platform: str, user_id: str) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM blocked WHERE platform = ? AND user_id = ?", (platform, user_id)
        ) as cur:
            return await cur.fetchone() is not None

    async def block(self, platform: str, user_id: str, display: str) -> bool:
        async with self._write_lock:
            cur = await self._db.execute(
                "INSERT OR IGNORE INTO blocked (platform, user_id, display, blocked_at) VALUES (?, ?, ?, ?)",
                (platform, user_id, display, time.time()),
            )
            await self._db.commit()
            return (cur.rowcount or 0) > 0

    async def unblock_all(self, platform: str) -> None:
        async with self._write_lock:
            await self._db.execute("DELETE FROM blocked WHERE platform = ?", (platform,))
            await self._db.commit()

    async def create_pair_code(self, agent_id: str, ttl_s: int) -> tuple[str, float]:
        expires_at = time.time() + ttl_s
        async with self._write_lock:
            await self._db.execute("DELETE FROM pair_codes WHERE agent_id = ? OR expires_at <= ?", (agent_id, time.time()))
            for _ in range(20):
                code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(PAIR_CODE_LEN))
                try:
                    await self._db.execute(
                        "INSERT INTO pair_codes (code, agent_id, expires_at) VALUES (?, ?, ?)",
                        (code, agent_id, expires_at),
                    )
                except aiosqlite.IntegrityError:
                    continue
                await self._db.commit()
                return code, expires_at
            await self._db.rollback()
        raise RuntimeError("could not allocate a unique pairing code")

    async def consume_pair_code(self, code: str) -> str | None:
        now = time.time()
        async with self._write_lock:
            async with self._db.execute(
                "SELECT agent_id, expires_at FROM pair_codes WHERE code = ?", (code,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            await self._db.execute("DELETE FROM pair_codes WHERE code = ?", (code,))
            await self._db.commit()
        if row["expires_at"] <= now:
            return None
        return str(row["agent_id"])

    async def purge_expired_codes(self) -> int:
        async with self._write_lock:
            cur = await self._db.execute("DELETE FROM pair_codes WHERE expires_at <= ?", (time.time(),))
            await self._db.commit()
            return cur.rowcount or 0
