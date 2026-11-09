"""Xác thực một chủ sở hữu (spec access-control, design D7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest import TEST_PASSWORD
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from novel_translator.application.auth import (
    AuthConfigError,
    AuthService,
    InvalidCredentialsError,
    LoginLockedError,
)
from novel_translator.config import Settings
from novel_translator.container import build_container, get_container
from novel_translator.interfaces.api.app import app
from novel_translator.interfaces.cli import main as cli
from novel_translator.security import verify_password

H = {"X-Requested-With": "test"}


@pytest.fixture
def client_for(db, password_hash):
    def _make(**settings):
        settings.setdefault("password_hash", password_hash)
        settings.setdefault("cookie_secure", False)
        c = build_container(Settings(_env_file=None, provider="echo", **settings), pool=db)
        app.dependency_overrides[get_container] = lambda: c
        return TestClient(app, headers=H), c

    yield _make
    app.dependency_overrides.clear()


def _sessions(db) -> int:
    with db.connection() as conn:
        return conn.execute("SELECT count(*) AS n FROM sessions").fetchone()["n"]


def test_correct_password_creates_session_cookie(client_for, db):
    client, _ = client_for(cookie_secure=True)
    r = client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("nt_session=")
    for attr in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert attr.lower() in cookie.lower()
    assert _sessions(db) == 1
    with db.connection() as conn:  # DB chỉ lưu hash của token
        token = cookie.split(";")[0].split("=", 1)[1]
        stored = conn.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert stored != token and len(stored) == 64


def test_session_grants_access(anon_client):
    assert anon_client.get("/api/auth/me").status_code == 401
    assert anon_client.post("/api/auth/login", json={"password": TEST_PASSWORD}).status_code == 204
    assert anon_client.get("/api/auth/me").json() == {"authenticated": True}
    assert anon_client.get("/api/novels").status_code == 200


def test_wrong_password(anon_client, db):
    r = anon_client.post("/api/auth/login", json={"password": "sai"})
    assert r.status_code == 401
    assert "set-cookie" not in r.headers
    assert _sessions(db) == 0


def test_missing_configuration_fails_startup(client_for):
    client_for(password_hash=None)
    with pytest.raises(AuthConfigError, match="NT_PASSWORD_HASH"), TestClient(app):
        pass


def test_invalid_hash_format_fails_startup(client_for):
    _, c = client_for(password_hash="plaintext-password")
    with pytest.raises(AuthConfigError, match="argon2"):
        c.auth.ensure_configured()


def test_unauthenticated_api_calls_return_401(anon_client):
    for path in ("/api/novels", "/api/settings", "/api/novels/1/chapters", "/api/auth/me",
                 "/docs"):
        r = anon_client.get(path)
        assert r.status_code == 401, path
        assert r.json() == {"detail": "Chưa đăng nhập."}
    assert anon_client.get("/health").status_code == 200


def test_logout_invalidates_session(api_client):
    old = api_client.cookies.get("nt_session")
    r = api_client.post("/api/auth/logout")
    assert r.status_code == 204
    assert 'nt_session=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]
    api_client.cookies.set("nt_session", old)
    assert api_client.get("/api/novels").status_code == 401


def test_expired_session(api_client, db):
    with db.connection() as conn:
        conn.execute("UPDATE sessions SET last_seen_at = now() - interval '31 days'")
    assert api_client.get("/api/novels").status_code == 401
    assert _sessions(db) == 0  # session quá hạn bị dọn


def test_active_session_slides(api_client, db):
    with db.connection() as conn:
        conn.execute("UPDATE sessions SET last_seen_at = now() - interval '29 days'")
    assert api_client.get("/api/novels").status_code == 200
    with db.connection() as conn:
        age = conn.execute("SELECT now() - last_seen_at AS a FROM sessions").fetchone()["a"]
    assert age < timedelta(minutes=1)


def test_too_many_failures_locks_ip_even_with_correct_password(anon_client):
    for _ in range(5):
        assert anon_client.post("/api/auth/login", json={"password": "sai"}).status_code == 401
    r = anon_client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert r.status_code == 429
    assert 0 < int(r.headers["retry-after"]) <= 15 * 60


def test_lock_expires_after_15_minutes_and_success_resets():
    now = [datetime(2026, 11, 9, tzinfo=timezone.utc)]

    class Store:
        def create_session(self, h, t):
            pass

    svc = AuthService(Store(), "$argon2-fake", lambda h, p: p == "dung",
                      clock=lambda: now[0])
    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            svc.login("sai", "1.2.3.4")
    svc.login("dung", "1.2.3.4")  # thành công → đếm lại từ đầu
    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            svc.login("sai", "1.2.3.4")
    with pytest.raises(LoginLockedError):
        svc.login("dung", "1.2.3.4")
    svc.login("dung", "5.6.7.8")  # IP khác không bị ảnh hưởng
    now[0] += timedelta(minutes=15, seconds=1)
    svc.login("dung", "1.2.3.4")


def test_failures_outside_window_not_counted():
    now = [datetime(2026, 11, 9, tzinfo=timezone.utc)]

    class Store:
        def create_session(self, h, t):
            pass

    svc = AuthService(Store(), "$argon2-fake", lambda h, p: p == "dung", clock=lambda: now[0])
    for _ in range(4):
        with pytest.raises(InvalidCredentialsError):
            svc.login("sai", "ip")
        now[0] += timedelta(minutes=5)  # trải dài hơn 15 phút
    with pytest.raises(InvalidCredentialsError):
        svc.login("sai", "ip")
    svc.login("dung", "ip")  # không bị khóa


def test_x_forwarded_for_only_from_trusted_proxy(client_for):
    client, _ = client_for(trusted_proxy="testclient")
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "x"},
                    headers={"X-Forwarded-For": "203.0.113.7"})
    locked = client.post("/api/auth/login", json={"password": TEST_PASSWORD},
                         headers={"X-Forwarded-For": "203.0.113.7"})
    assert locked.status_code == 429
    other = client.post("/api/auth/login", json={"password": TEST_PASSWORD},
                        headers={"X-Forwarded-For": "203.0.113.8"})
    assert other.status_code == 204


def test_spoofed_x_forwarded_for_ignored_without_trusted_proxy(client_for):
    client, _ = client_for()
    for i in range(5):
        client.post("/api/auth/login", json={"password": "x"},
                    headers={"X-Forwarded-For": f"10.0.0.{i}"})
    r = client.post("/api/auth/login", json={"password": TEST_PASSWORD},
                    headers={"X-Forwarded-For": "10.0.0.99"})
    assert r.status_code == 429  # cùng IP kết nối thật → vẫn bị khóa


def test_mutating_request_requires_csrf_header(api_client):
    r = api_client.post("/api/auth/logout", headers={"X-Requested-With": ""})
    assert r.status_code == 403
    assert api_client.get("/api/novels").status_code == 200  # GET không cần


def test_hash_password_cli():
    runner = CliRunner()
    r = runner.invoke(cli.app, ["hash-password"], input="matkhau-dai\nmatkhau-dai\n")
    assert r.exit_code == 0, r.output
    line = next(ln for ln in r.output.splitlines() if ln.startswith("$argon2"))
    assert verify_password(line, "matkhau-dai") and not verify_password(line, "khac")
    short = runner.invoke(cli.app, ["hash-password"], input="ngan\nngan\n")
    assert short.exit_code == 1
