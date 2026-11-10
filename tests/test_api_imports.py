"""API `/api/imports` (design D3) và chặn dịch truyện bản dịch có sẵn (spec novel-library)."""

from __future__ import annotations

import pytest

from novel_translator.config import Settings
from novel_translator.container import build_container, get_container
from novel_translator.interfaces.api import routers
from novel_translator.interfaces.api.app import app

BODY = "Trần Bình An ngồi trước cửa ngõ, nhìn mưa xuân rơi trên mái hiên. " * 3
VI = "Kiếm Lai\n" + "\n".join(f"Chương {n}: Tên {n}\n{BODY}" for n in (1, 2, 3, 5))
ZH = "第一章 少年\n" + "林动站在山上。" * 20 + "\n第二章 修炼\n" + "林动开始修炼。" * 20


def _preview(client, text=VI, name="kiemlai.txt"):
    r = client.post("/api/imports", files={"file": (name, text.encode(), "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()


def test_preview_shape_and_nothing_saved(api_client):
    p = _preview(api_client)
    assert (p["filename"], p["default_title"], p["detected_lang"]) == (
        "kiemlai.txt", "kiemlai", "vi")
    assert [c["title"] for c in p["chapters"]] == [
        "Chương 1: Tên 1", "Chương 2: Tên 2", "Chương 3: Tên 3", "Chương 5: Tên 5"]
    assert p["boundaries"] == [c["start_line"] for c in p["chapters"]]
    assert p["front_matter"]["excerpt"] == "Kiếm Lai" and p["front_matter"]["keep"] is False
    assert [w["code"] for w in p["warnings"]] == ["front_matter"]
    gap = p["chapters"][3]["warnings"]
    assert [w["code"] for w in gap] == ["number_gap"] and "Thiếu chương 4" in gap[0]["message"]
    first = p["chapters"][0]
    assert first["chars"] == len(BODY.strip()) and first["excerpt"].endswith("…")
    assert len(first["excerpt"]) == 81
    assert api_client.get("/api/novels").json() == []


def test_upload_review_confirm(api_client):
    p = _preview(api_client)
    r = api_client.post(f"/api/imports/{p['id']}/commit", json={"boundaries": p["boundaries"]})
    assert r.status_code == 201, r.text
    novel = r.json()
    assert (novel["title"], novel["source_lang"], novel["pretranslated"]) == (
        "kiemlai", "vi", True)
    chs = api_client.get(f"/api/novels/{novel['id']}/chapters").json()
    assert [c["status"] for c in chs] == ["translated"] * 4
    # draft đã dùng xong
    assert api_client.get(f"/api/imports/{p['id']}").status_code == 410


def test_cancel_preview_creates_nothing(api_client):
    p = _preview(api_client)
    assert api_client.delete(f"/api/imports/{p['id']}").status_code == 204
    assert api_client.post(f"/api/imports/{p['id']}/commit",
                           json={"boundaries": p["boundaries"]}).status_code == 410
    assert api_client.get("/api/novels").json() == []


def test_merge_false_heading_before_saving(api_client):
    p = _preview(api_client)
    b = p["boundaries"]
    merged = [b[0], b[1], b[3]]  # bỏ "Chương 3"
    r = api_client.put(f"/api/imports/{p['id']}", json={"boundaries": merged})
    assert r.status_code == 200
    assert len(r.json()["chapters"]) == 3
    nid = api_client.post(f"/api/imports/{p['id']}/commit",
                          json={"boundaries": merged, "title": "Kiếm Lai"}).json()["id"]
    ch2 = api_client.get(f"/api/novels/{nid}/chapters/2").json()
    assert "Chương 3: Tên 3" in ch2["translated_text"]
    assert len(api_client.get(f"/api/novels/{nid}/chapters").json()) == 3


def test_split_keep_front_matter_and_change_language(api_client):
    p = _preview(api_client)
    extra = p["boundaries"][0] + 1  # tách tại dòng thân đầu tiên của chương 1
    r = api_client.put(f"/api/imports/{p['id']}",
                       json={"boundaries": sorted(p["boundaries"] + [extra]),
                             "keep_front_matter": True})
    body = r.json()
    assert body["chapters"][0]["title"] == "Mở đầu" and body["front_matter"]["keep"] is True
    assert len(body["chapters"]) == 6
    nid = api_client.post(f"/api/imports/{p['id']}/commit", json={
        "boundaries": body["boundaries"], "keep_front_matter": True, "lang": "zh"}).json()["id"]
    novel = api_client.get(f"/api/novels/{nid}").json()
    assert novel["pretranslated"] is False and novel["source_lang"] == "zh"
    chs = api_client.get(f"/api/novels/{nid}/chapters").json()
    assert len(chs) == 6 and {c["status"] for c in chs} == {"pending"}


def test_lines_window(api_client):
    p = _preview(api_client)
    r = api_client.get(f"/api/imports/{p['id']}/lines", params={"start": 1, "count": 2})
    assert r.json() == {"start": 1, "lines": ["Chương 1: Tên 1", BODY]}
    assert api_client.get(f"/api/imports/{p['id']}/lines",
                          params={"count": 501}).status_code == 422


def test_invalid_boundaries_400(api_client):
    p = _preview(api_client)
    r = api_client.put(f"/api/imports/{p['id']}", json={"boundaries": [99_999]})
    assert r.status_code == 400


def test_expired_preview_after_restart(api_client, db, password_hash):
    p = _preview(api_client)
    fresh = build_container(
        Settings(provider="echo", password_hash=password_hash, cookie_secure=False), pool=db)
    app.dependency_overrides[get_container] = lambda: fresh
    r = api_client.post(f"/api/imports/{p['id']}/commit", json={"boundaries": p["boundaries"]})
    assert r.status_code == 410 and r.json()["code"] == "draft_expired"
    assert "upload lại" in r.json()["detail"]
    assert api_client.get("/api/novels").json() == []


def test_oversized_empty_and_non_txt(api_client, monkeypatch):
    monkeypatch.setattr(routers.library, "MAX_UPLOAD_BYTES", 10)
    r = api_client.post("/api/imports", files={"file": ("big.txt", VI.encode())})
    assert r.status_code == 413
    monkeypatch.undo()
    assert api_client.post("/api/imports", files={"file": ("e.txt", b"")}).status_code == 400
    assert api_client.post("/api/imports", files={"file": ("a.epub", b"x")}).status_code == 400
    assert api_client.post("/api/imports", files={"file": ("w.txt", b"\n\n")}).status_code == 400
    assert api_client.get("/api/novels").json() == []


def test_requires_session_and_csrf_header(anon_client, api_client):
    assert anon_client.post("/api/imports", files={"file": ("a.txt", b"x")}).status_code == 401
    p = _preview(api_client)
    api_client.headers.pop("X-Requested-With")
    r = api_client.post(f"/api/imports/{p['id']}/commit", json={"boundaries": p["boundaries"]})
    assert r.status_code == 403


# --- POST /api/novels (lưu ngay) nhận lang; truyện bản dịch có sẵn bị chặn dịch -------------

def test_direct_upload_with_lang(api_client):
    r = api_client.post("/api/novels", files={"file": ("a.txt", VI.encode())}, data={"lang": "zh"})
    assert r.status_code == 201 and r.json()["pretranslated"] is False
    r = api_client.post("/api/novels", files={"file": ("b.txt", VI.encode())})
    assert r.json()["pretranslated"] is True and r.json()["title"] == "b"
    r = api_client.post("/api/novels", files={"file": ("c.txt", VI.encode())}, data={"lang": "en"})
    assert r.status_code == 422


@pytest.mark.parametrize("force", [False, True])
def test_translate_request_rejected_for_pretranslated(api_client, container, force):
    r = api_client.post("/api/novels", files={"file": ("a.txt", VI.encode())})
    nid = r.json()["id"]
    r = api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={"force": force})
    assert r.status_code == 409 and r.json()["code"] == "pretranslated"
    assert container.jobs.get(nid, 1) is None
    assert container.provider_factory(None).calls == []


def test_chinese_upload_still_translatable(api_client):
    r = api_client.post("/api/novels", files={"file": ("zh.txt", ZH.encode())})
    assert r.json()["pretranslated"] is False
    nid = r.json()["id"]
    assert api_client.post(f"/api/novels/{nid}/chapters/1/translate", json={}).status_code == 202
