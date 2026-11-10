"""Health endpoint (spec deployment "Health endpoint", release-pipeline "Image carries its version")."""

from __future__ import annotations

import logging

import psycopg
import pytest

from novel_translator.storage.db import ping


@pytest.mark.parametrize("path", ["/api/health", "/health"])
def test_anonymous_health_has_no_version(anon_client, path):
    r = anon_client.get(path)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/health", "/health"])
def test_logged_in_health_has_version(api_client, container, path):
    container.settings.__dict__["version"] = "v1.4.0"
    r = api_client.get(path)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "v1.4.0"}


def test_database_unreachable_returns_503_without_details(api_client, container, monkeypatch):
    monkeypatch.setattr(type(container), "database_ok", lambda self: False)
    r = api_client.get("/api/health")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


def test_ping_false_when_pool_broken():
    class BrokenPool:
        def connection(self, timeout=None):
            raise psycopg.OperationalError("password authentication failed for user x")

    assert ping(BrokenPool()) is False


def test_ping_true_on_real_database(db):
    assert ping(db) is True


def test_version_logged_at_startup(container, caplog):
    from fastapi.testclient import TestClient

    from novel_translator.container import get_container
    from novel_translator.interfaces.api.app import app

    container.settings.__dict__["version"] = "v9.9.9"
    app.dependency_overrides[get_container] = lambda: container
    try:
        with caplog.at_level(logging.INFO, logger="uvicorn.error"), TestClient(app):
            pass
    finally:
        app.dependency_overrides.clear()
    assert "Novel Translator v9.9.9" in caplog.text


def test_version_read_from_env(monkeypatch):
    from novel_translator.config import Settings

    monkeypatch.setenv("NT_VERSION", "sha-a1b2c3d")
    assert Settings(_env_file=None).version == "sha-a1b2c3d"
    monkeypatch.delenv("NT_VERSION")
    assert Settings(_env_file=None).version == "dev"
