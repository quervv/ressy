import hashlib

import httpx
import pytest

from ressy import updater

SETUP = b"MZ fake setup bytes" * 100


def release_json(tag="v9.0.0", digest=None, url=None, **extra):
    return {
        "tag_name": tag,
        "body": "- **Discord** migliore\n- Giochi Epic",
        "assets": [{
            "name": "Ressy-Setup.exe",
            "size": len(SETUP),
            "digest": digest if digest is not None else "sha256:" + hashlib.sha256(SETUP).hexdigest(),
            "browser_download_url": url or "https://github.com/quervv/ressy/releases/download/v9.0.0/Ressy-Setup.exe",
        }],
        **extra,
    }


def test_versions_compare_as_numbers():
    assert updater.is_newer("1.1.10", "1.1.9")
    assert updater.is_newer("v1.2", "1.1.1")
    assert not updater.is_newer("1.1.1", "1.1.1")
    assert not updater.is_newer("1.1.0", "1.1.1")
    assert not updater.is_newer("garbage", "1.1.1")


def test_release_needs_a_digest_and_the_official_url():
    assert updater.release_from(release_json()).sha256 == hashlib.sha256(SETUP).hexdigest()
    assert updater.release_from(release_json(digest="")) is None
    assert updater.release_from(release_json(url="https://evil.example/Ressy-Setup.exe")) is None
    assert updater.release_from(release_json(prerelease=True)) is None


def _serve(monkeypatch, body: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.github.com" in str(request.url):
            return httpx.Response(200, json=release_json())
        return httpx.Response(200, content=body, headers={"content-length": str(len(body))})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "get", lambda url, **kw: client.get(url, headers=kw.get("headers")))
    monkeypatch.setattr(httpx, "stream", lambda method, url, **kw: client.stream(method, url, headers=kw.get("headers")))


def test_check_and_download_verify_the_file(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    _serve(monkeypatch, SETUP)
    release = updater.check()
    assert release is not None and release.version == "9.0.0"
    seen = []
    path = updater.download(release, lambda done, total: seen.append(done))
    assert path.read_bytes() == SETUP and seen[-1] == len(SETUP)


def test_a_tampered_download_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    _serve(monkeypatch, SETUP[:-1] + b"X")
    release = updater.check()
    with pytest.raises(OSError):
        updater.download(release)
    assert not list((tmp_path / "Ressy-Update").glob("*.exe"))


def test_no_update_when_already_latest(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "9.0.0")
    monkeypatch.setattr(updater, "is_newer", lambda v, current="9.0.0": updater.parse_version(v) > (9, 0, 0))
    _serve(monkeypatch, SETUP)
    assert updater.check() is None


def test_notes_become_plain_lines():
    from ressy.ui.update_dialog import short_notes

    assert short_notes("Titolo\n\n- **Discord**: meglio\n* `x`") == "• Titolo\n• Discord: meglio\n• x"
