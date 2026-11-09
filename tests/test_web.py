"""Phục vụ web app ở `/` (spec interfaces "Web application delivery", design D8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_translator.config import Settings
from novel_translator.container import build_container, get_container
from novel_translator.interfaces.api.app import app

INDEX = "<!doctype html><html><body>SPA shell</body></html>"


@pytest.fixture
def web_client(db, password_hash, tmp_path):
    root = tmp_path / "build"
    (root / "_app" / "immutable").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "_app" / "immutable" / "app.abc123.js").write_text("console.log(1)")
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("không được lộ")
    c = build_container(Settings(_env_file=None, provider="echo", password_hash=password_hash,
                                 cookie_secure=False, web_dir=root), pool=db)
    app.dependency_overrides[get_container] = lambda: c
    yield TestClient(app, headers={"X-Requested-With": "t"})
    app.dependency_overrides.clear()


def test_deep_link_serves_app_shell(web_client):
    for path in ("/", "/novels/1/chapters/12", "/login", "/settings"):
        r = web_client.get(path)
        assert r.status_code == 200, path
        assert r.text == INDEX
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["x-robots-tag"].startswith("noindex")
        assert r.headers["cache-control"] == "no-cache"


def test_static_assets(web_client):
    r = web_client.get("/_app/immutable/app.abc123.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    assert "immutable" in r.headers["cache-control"]
    assert web_client.get("/favicon.svg").text == "<svg/>"


def test_path_traversal_blocked(web_client):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/_app/../../secret.txt"):
        r = web_client.get(path)
        assert "không được lộ" not in r.text, path


def test_api_and_docs_not_swallowed_by_spa(web_client):
    r = web_client.get("/api/does-not-exist")
    assert r.status_code == 401  # chưa đăng nhập: vẫn bị chặn như API
    from conftest import TEST_PASSWORD

    web_client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    r = web_client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    web_client.cookies.clear()
    assert web_client.get("/docs").status_code == 401
    assert web_client.get("/robots.txt").text.startswith("User-agent: *\nDisallow: /")


def test_not_built(db, password_hash, tmp_path):
    c = build_container(Settings(_env_file=None, provider="echo", password_hash=password_hash,
                                 web_dir=tmp_path / "missing"), pool=db)
    app.dependency_overrides[get_container] = lambda: c
    try:
        r = TestClient(app).get("/novels/1")
        assert r.status_code == 404 and "npm run build" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


REAL_BUILD = Path(__file__).resolve().parents[1] / "web" / "build"


@pytest.mark.skipif(not (REAL_BUILD / "index.html").is_file(),
                    reason="chưa build web (cd web && npm run build)")
def test_deep_link_with_real_build(db, password_hash):
    c = build_container(Settings(_env_file=None, provider="echo", password_hash=password_hash,
                                 web_dir=REAL_BUILD), pool=db)
    app.dependency_overrides[get_container] = lambda: c
    try:
        client = TestClient(app)
        r = client.get("/novels/1/chapters/12")
        assert r.status_code == 200 and "/_app/" in r.text
        asset = next(p for p in (REAL_BUILD / "_app" / "immutable").rglob("*.js"))
        rel = asset.relative_to(REAL_BUILD).as_posix()
        assert client.get(f"/{rel}").status_code == 200
    finally:
        app.dependency_overrides.clear()
