from __future__ import annotations

import time
from datetime import timezone

import pytest

from ressy_server.frontends.base import split_text
from ressy_server.protocol import b64decode, b64encode, normalize_pair_code
from ressy_server.ratelimit import SlidingWindow
from ressy_server.settings import Settings
from ressy_server.storage import LinkRecord, Store
from ressy_server.timefmt import format_last_seen


def test_normalize_pair_code():
    assert normalize_pair_code("k7p-2qx") == "K7P2QX"
    assert normalize_pair_code(" K7P 2QX ") == "K7P2QX"
    assert normalize_pair_code("K7P2Q0") is None
    assert normalize_pair_code("TOOLONG1") is None
    assert normalize_pair_code(None) is None


def test_b64_limits():
    assert b64decode(b64encode(b"hello"), 10) == b"hello"
    with pytest.raises(ValueError):
        b64decode(b64encode(b"x" * 100), 10)
    with pytest.raises(ValueError):
        b64decode("not base64!!", 100)


def test_split_text():
    assert split_text("", 10) == []
    chunks = split_text("riga uno\nriga due\nriga tre", 12)
    assert all(len(c) <= 12 for c in chunks)
    assert " ".join(chunks).replace("\n", " ").split() == "riga uno riga due riga tre".split()


def test_sliding_window():
    now = [0.0]
    limiter = SlidingWindow(2, 10, clock=lambda: now[0])
    assert limiter.hit("a") and limiter.hit("a")
    assert not limiter.hit("a")
    now[0] = 11
    assert limiter.hit("a")


def test_last_seen():
    now = time.time()
    assert format_last_seen(None, now, timezone.utc) == "mai"
    assert format_last_seen(now - 5, now, timezone.utc) == "pochi secondi fa"
    assert format_last_seen(now - 120, now, timezone.utc) == "2 minuti fa"


def test_settings_from_env():
    s = Settings.from_env({"TELEGRAM_BOT_TOKEN": "t", "RESSY_PORT": "9000", "RESSY_TRUST_PROXY": "1"})
    assert s.port == 9000 and s.trust_proxy and s.validate() == []
    assert Settings.from_env({}).validate()


async def test_store_codes_and_links():
    store = await Store.open(":memory:")
    try:
        await store.create_agent("a" * 32, "h", "PC", "1")
        code, expires = await store.create_pair_code("a" * 32, 600)
        assert expires > time.time()
        assert await store.consume_pair_code(code) == "a" * 32
        assert await store.consume_pair_code(code) is None

        first, _ = await store.create_pair_code("a" * 32, 600)
        second, _ = await store.create_pair_code("a" * 32, 600)
        assert await store.consume_pair_code(first) is None
        assert await store.consume_pair_code(second) == "a" * 32

        link = LinkRecord("telegram", "1", "1", "@u", "a" * 32, linked_at=time.time())
        await store.upsert_link(link)
        assert (await store.get_link("telegram", "1")).display == "@u"
        assert [l.user_id for l in await store.links_for_agent("a" * 32)] == ["1"]
        assert await store.delete_link("telegram", "1") is not None
        assert await store.get_link("telegram", "1") is None
    finally:
        await store.close()
