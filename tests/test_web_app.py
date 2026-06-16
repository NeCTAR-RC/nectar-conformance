"""The FastAPI app factory: SPA serving, no-SPA fallback, and the console entry point."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient
import uvicorn

from nectar_conformance.config import Config
from nectar_conformance.web import app as app_mod
from nectar_conformance.web.app import create_app
from nectar_conformance.web.settings import WebSettings


def _client(static_dir, reports_dir):
    settings = WebSettings(
        config=Config(),
        tier="prod",
        reports_dir=reports_dir,
        static_dir=static_dir,
    )
    return TestClient(create_app(settings))


@pytest.fixture
def spa_dir(tmp_path) -> Path:
    static = tmp_path / "spa"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>INDEX</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    return static


def test_spa_serves_index_assets_and_fallback(spa_dir, tmp_path):
    client = _client(spa_dir, tmp_path / "reports")
    assert "INDEX" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    # An unknown client-side route falls back to the SPA shell.
    assert "INDEX" in client.get("/sites/site1").text
    # An unmatched API path is a real 404, not the SPA shell.
    assert client.get("/api/does-not-exist").status_code == 404


def test_no_spa_when_static_absent(tmp_path):
    client = _client(None, tmp_path / "reports")
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 404


def test_web_main_invokes_uvicorn(monkeypatch, tmp_path):
    # Isolate env mutations and stub uvicorn so nothing actually serves.
    monkeypatch.setattr(os, "environ", os.environ.copy())
    calls = {}

    def fake_run(app_str, **kwargs):
        calls["app"] = app_str
        calls["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)
    rc = app_mod.main(
        [
            "--reports-dir",
            str(tmp_path),
            "--tier",
            "test",
            "--port",
            "8123",
            "--static-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert calls["app"] == "nectar_conformance.web.app:create_app"
    assert calls["kwargs"]["factory"] is True
    assert calls["kwargs"]["port"] == 8123
    assert os.environ["NECTAR_CONFORMANCE_TIER"] == "test"
