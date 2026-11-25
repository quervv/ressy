from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def settings(tmp_path):
    from ressy.config import Settings

    s = Settings()
    s._path = tmp_path / "config.json"
    s.groq_api_key = "gsk_test_key"
    s.ensure_identity()
    return s


@pytest.fixture(autouse=True)
def _isolated_app_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
