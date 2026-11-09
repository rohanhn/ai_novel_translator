"""API `/api` theo nhóm (spec interfaces): library, chapters, glossary, reading, settings."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.config import Settings
from novel_translator.container import build_container, get_container
from novel_translator.domain.models import GlossarySuggestion
from novel_translator.interfaces.api import routers
from novel_translator.interfaces.api.app import app

RAW = "第一章 少年\n林动站在山上。\n第二章 修炼\n林动开始修炼。\n".encode()


def _upload(client, raw: bytes = RAW, name: str = "demo.txt", **data) -> int:
    r = client.post("/api/novels", files={"file": (name, raw, "text/plain")}, data=data)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait_status(client, nid: int, index: int, want: str, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/novels/{nid}/chapters/{index}").json()
        if body["status"] == want:
            return body
        time.sleep(0.02)
    raise AssertionError(f"chương {index} không đạt trạng thái {want}: {body['status']}")


# ---------- library ----------
def test_upload_title_defaults_to_file_name_and_library_lists_it(api_client):
    nid = _upload(api_client, name="pham-nhan.txt")
    assert api_client.get(f"/api/novels/{nid}").json()["title"] == "pham-nhan"
    other = _upload(api_client, title="Tên khác")
    assert api_client.get(f"/api/novels/{other}").json()["title"] == "Tên khác"
    rows = api_client.get("/api/novels").json()
    assert {r["id"] for r in rows} == {nid, other}
    row = next(r for r in rows if r["id"] == nid)
    assert (row["chapter_count"], row["translated_count"], row["last_read_chapter"]) == (2, 0, None)


def test_upload_gbk_uses_import_encoding_rules(api_client):
    nid = _upload(api_client, raw="第一章 少年\n林动。\n".encode("gbk"), name="gbk.txt")
    assert api_client.get(f"/api/novels/{nid}/chapters/1").json()["source_text"] == "林动。"


def test_upload_rejects_too_large_empty_and_non_txt(api_client, monkeypatch):
    monkeypatch.setattr(routers.library, "MAX_UPLOAD_BYTES", 10)
    r = api_client.post("/api/novels", files={"file": ("big.txt", RAW)})
    assert r.status_code == 413
    assert api_client.post("/api/novels", files={"file": ("e.txt", b"")}).status_code == 400
    assert api_client.post("/api/novels", files={"file": ("a.epub", RAW)}).status_code == 400
    assert api_client.get("/api/novels").json() == []


def test_delete_requires_confirmation(api_client):
    nid = _upload(api_client)
    r = api_client.delete(f"/api/novels/{nid}")
    assert r.status_code == 409 and r.json()["code"] == "confirmation_required"
    assert api_client.get(f"/api/novels/{nid}").status_code == 200
    assert api_client.delete(f"/api/novels/{nid}?confirm=true").status_code == 204
    assert api_client.get(f"/api/novels/{nid}").status_code == 404


def test_404s(api_client):
    for path in ("/api/novels/999", "/api/novels/999/chapters", "/api/novels/999/chapters/1",
                 "/api/novels/999/glossary", "/api/novels/999/suggestions",
                 "/api/novels/999/progress"):
        assert api_client.get(path).status_code == 404, path
    nid = _upload(api_client)
    assert api_client.get(f"/api/novels/{nid}/chapters/9").status_code == 404
    r = api_client.post(f"/api/novels/{nid}/chapters/9/translate", json={})
    assert r.status_code == 404


# ---------- chapters ----------
def test_translate_returns_202_then_chapter_is_translated(api_client):
    nid = _upload(api_client)
    r = api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={})
    assert r.status_code == 202, r.text
    assert r.json()["stream_url"] == f"/api/novels/{nid}/chapters/1/stream"
    assert r.json()["lane"] == "foreground"
    body = _wait_status(api_client, nid, 1, "translated")
    assert body["translated_title"] == "[VI] 第一章 少年"
    assert body["translated_text"] == "[VI] 林动站在山上。"
    assert body["provider"] == "echo"
    # đã có bản dịch, không force → 200 kèm chương, không tạo job
    again = api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={})
    assert again.status_code == 200 and again.json()["status"] == "translated"
    summaries = api_client.get(f"/api/novels/{nid}/chapters").json()
    assert [s["status"] for s in summaries] == ["translated", "pending"]


def test_edit_chapter_and_confirmed_retranslation(api_client):
    nid = _upload(api_client)
    r = api_client.put(f"/api/novels/{nid}/chapters/1", json={"translated_text": "sửa"})
    assert r.status_code == 409  # chưa có bản dịch
    api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={})
    _wait_status(api_client, nid, 1, "translated")
    r = api_client.put(f"/api/novels/{nid}/chapters/1",
                       json={"translated_title": "Thiếu niên", "translated_text": "Bản sửa."})
    assert r.status_code == 200 and r.json()["status"] == "edited"
    r = api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={"force": True})
    assert r.status_code == 409 and r.json()["code"] == "confirmation_required"
    assert api_client.get(f"/api/novels/{nid}/chapters/1").json()["translated_text"] == "Bản sửa."
    r = api_client.post(f"/api/novels/{nid}/chapters/1/translate",
                        json={"force": True, "confirm_discard_edits": True})
    assert r.status_code == 202
    _wait_status(api_client, nid, 1, "translated")


def test_unknown_provider_returns_400_listing_available(api_client):
    nid = _upload(api_client)
    r = api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={"provider": "nope"})
    assert r.status_code == 400
    assert "echo" in r.json()["detail"] and "gemini" in r.json()["detail"]


@pytest.fixture
def chain_client(db, password_hash, monkeypatch):
    """Client với container tùy biến (chuỗi provider thật sự, không override provider)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from conftest import TEST_PASSWORD
    from fastapi.testclient import TestClient

    def make(**kw):
        c = build_container(Settings(_env_file=None, password_hash=password_hash,
                                     cookie_secure=False, **kw), pool=db)
        app.dependency_overrides[get_container] = lambda: c
        client = TestClient(app, headers={"X-Requested-With": "t"})
        assert client.post("/api/auth/login", json={"password": TEST_PASSWORD}).status_code == 204
        return client, c

    yield make
    app.dependency_overrides.clear()


def test_quota_exhausted_returns_429_with_reset_at(chain_client):
    client, c = chain_client(chain="echo:a,echo:b")
    nid = _upload(client)
    first = datetime.now(timezone.utc) + timedelta(hours=3)
    c.quota.mark_exhausted(1, first + timedelta(hours=1))
    c.quota.mark_exhausted(2, first)
    r = client.post(f"/api/novels/{nid}/chapters/1/translate", json={})
    assert r.status_code == 429
    body = r.json()
    assert body["category"] == "daily_quota"
    assert datetime.fromisoformat(body["reset_at"]) == first  # thời điểm reset sớm nhất
    assert 0 < int(r.headers["retry-after"]) <= 3 * 3600
    assert c.jobs.get(nid, 1) is None  # không tạo job
    assert client.get(f"/api/novels/{nid}/chapters/1").json()["status"] == "pending"


def test_one_step_left_is_accepted(chain_client):
    client, c = chain_client(chain="echo:a,echo:b")
    nid = _upload(client)
    c.quota.mark_exhausted(1, datetime.now(timezone.utc) + timedelta(hours=1))
    assert client.post(f"/api/novels/{nid}/chapters/1/translate", json={}).status_code == 202
    assert _wait_status(client, nid, 1, "translated")["chain_step"] == 2


def test_missing_key_returns_502_with_category(chain_client):
    client, c = chain_client()  # chuỗi Gemini mặc định, không có key
    nid = _upload(client)
    r = client.post(f"/api/novels/{nid}/chapters/1/translate", json={})
    assert r.status_code == 502
    assert r.json()["category"] == "config"
    assert "GEMINI_API_KEY" in r.json()["detail"]
    assert c.jobs.get(nid, 1) is None


# ---------- glossary ----------
def test_glossary_crud_and_affected_chapters(api_client):
    nid = _upload(api_client)
    r = api_client.put(f"/api/novels/{nid}/glossary",
                       json={"source_term": "林动", "target_term": "Lâm Động"})
    assert r.status_code == 200 and r.json()["target_term"] == "Lâm Động"
    assert api_client.get(f"/api/novels/{nid}").json()["glossary_version"] == 1
    assert [g["source_term"] for g in api_client.get(f"/api/novels/{nid}/glossary").json()] == [
        "林动"]
    api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={})
    _wait_status(api_client, nid, 1, "translated")
    affected = api_client.get(f"/api/novels/{nid}/glossary/林动/chapters").json()
    assert [a["index"] for a in affected] == [1]
    assert api_client.delete(f"/api/novels/{nid}/glossary/林动").status_code == 204
    assert api_client.delete(f"/api/novels/{nid}/glossary/林动").status_code == 404
    r = api_client.put(f"/api/novels/{nid}/glossary", json={"source_term": "", "target_term": "x"})
    assert r.status_code == 422


def test_suggestions_accept_with_edit_and_dismiss(api_client, container):
    nid = _upload(api_client)
    container.repo.add_suggestion(GlossarySuggestion(nid, "苏柔", "Tô Nhu", "person"))
    container.repo.add_suggestion(GlossarySuggestion(nid, "青阳镇", "Thanh Dương trấn"))
    rows = api_client.get(f"/api/novels/{nid}/suggestions").json()
    assert {r["source_term"] for r in rows} == {"苏柔", "青阳镇"}
    r = api_client.post(f"/api/novels/{nid}/suggestions/苏柔/accept",
                        json={"target_term": "Tô Nhược"})
    assert r.status_code == 200 and r.json()["target_term"] == "Tô Nhược"
    assert api_client.post(f"/api/novels/{nid}/suggestions/青阳镇/dismiss").status_code == 204
    assert api_client.get(f"/api/novels/{nid}/suggestions").json() == []
    terms = api_client.get(f"/api/novels/{nid}/glossary").json()
    assert [(t["source_term"], t["target_term"]) for t in terms] == [("苏柔", "Tô Nhược")]
    r = api_client.post(f"/api/novels/{nid}/suggestions/青阳镇/accept")
    assert r.status_code == 404  # đã bỏ qua → không còn chờ duyệt


# ---------- reading ----------
def test_progress_roundtrip(api_client):
    nid = _upload(api_client)
    assert api_client.get(f"/api/novels/{nid}/progress").status_code == 204
    r = api_client.put(f"/api/novels/{nid}/progress", json={"chapter_index": 2, "position": 0.4})
    assert r.status_code == 200
    got = api_client.get(f"/api/novels/{nid}/progress").json()
    assert (got["chapter_index"], got["position"]) == (2, 0.4)
    assert api_client.get("/api/novels").json()[0]["last_read_chapter"] == 2
    bad = api_client.put(f"/api/novels/{nid}/progress", json={"chapter_index": 2, "position": 2})
    assert bad.status_code == 400
    missing = api_client.put(f"/api/novels/{nid}/progress", json={"chapter_index": 9})
    assert missing.status_code == 404


def test_preferences(api_client):
    assert api_client.get("/api/preferences").json()["theme"] == "light"
    r = api_client.patch("/api/preferences", json={"theme": "bamboo", "font_size": 20})
    assert r.status_code == 200 and r.json()["theme"] == "bamboo"
    assert api_client.patch("/api/preferences", json={"theme": "neon"}).status_code == 400
    assert api_client.get("/api/preferences").json()["font_size"] == 20


# ---------- settings ----------
def test_settings_never_exposes_keys(chain_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "khoa-bi-mat-123")
    client, _ = chain_client()
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert [s["step"] for s in body["chain"]] == [1, 2]
    assert body["gemini_key_configured"] is True
    assert "echo" in body["available_providers"]
    assert "khoa-bi-mat-123" not in r.text
