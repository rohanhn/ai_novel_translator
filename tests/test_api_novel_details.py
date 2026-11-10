"""API sửa thông tin truyện và ảnh bìa (spec novel-library "Edit novel details", "Novel details
validation", "Novel cover upload", "Cover image processing", "Cover image access", "Cover image
from a link"). Không gọi mạng: bộ tải ảnh là bản giả."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from novel_translator.domain.novel_details import CoverFetchError
from novel_translator.interfaces.api import routers

ZH = "第一章 少年\n" + "林动站在山上。" * 20 + "\n第二章 修炼\n" + "林动开始修炼。" * 20


def _img(w=300, h=450, fmt="PNG") -> bytes:
    out = BytesIO()
    Image.new("RGB", (w, h), "navy").save(out, fmt)
    return out.getvalue()


@pytest.fixture
def nid(api_client):
    r = api_client.post("/api/novels", files={"file": ("kiem-lai-full.txt", ZH.encode())})
    return r.json()["id"]


class FakeFetcher:
    def __init__(self, result):
        self.result, self.urls = result, []

    def fetch(self, url):
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _put_cover(client, nid, data, name="bia.png"):
    return client.put(f"/api/novels/{nid}/cover", files={"file": (name, data, "image/png")})


# --- thông tin truyện ---------------------------------------------------------------------

def test_new_novel_has_no_details(api_client, nid):
    n = api_client.get(f"/api/novels/{nid}").json()
    assert (n["author"], n["description"], n["cover_url"]) == (None, None, None)
    item = api_client.get("/api/novels").json()[0]
    assert {"author", "description", "cover_url"} <= item.keys()


def test_rename_add_author_partial_and_clear(api_client, nid):
    before = api_client.get(f"/api/novels/{nid}/chapters").json()
    r = api_client.patch(f"/api/novels/{nid}",
                         json={"title": "Kiếm Lai", "author": "Phong Hỏa Hí Chư Hầu"})
    assert r.status_code == 200, r.text
    assert (r.json()["title"], r.json()["author"]) == ("Kiếm Lai", "Phong Hỏa Hí Chư Hầu")
    r = api_client.patch(f"/api/novels/{nid}", json={"description": "Dòng một\r\nDòng hai"})
    n = r.json()
    assert (n["title"], n["author"], n["description"]) == (
        "Kiếm Lai", "Phong Hỏa Hí Chư Hầu", "Dòng một\nDòng hai")
    assert api_client.patch(f"/api/novels/{nid}", json={"author": ""}).json()["author"] is None
    assert api_client.patch(f"/api/novels/{nid}",
                            json={"description": None}).json()["description"] is None
    assert api_client.get(f"/api/novels/{nid}/chapters").json() == before
    lib = api_client.get("/api/novels").json()[0]
    assert lib["title"] == "Kiếm Lai"


@pytest.mark.parametrize("body, field, text", [
    ({"title": "   "}, "title", "không được để trống"),
    ({"title": None}, "title", "không được để trống"),
    ({"title": "a" * 201}, "title", "200"),
    ({"author": "b" * 101}, "author", "100"),
    ({"description": "c" * 2001}, "description", "2000"),
])
def test_invalid_details_400_with_field(api_client, nid, body, field, text):
    r = api_client.patch(f"/api/novels/{nid}", json={**body, "author": "X"}
                         if field != "author" else body)
    assert r.status_code == 400 and r.json()["field"] == field and text in r.json()["detail"]
    n = api_client.get(f"/api/novels/{nid}").json()
    assert (n["title"], n["author"]) == ("kiem-lai-full", None)  # không đổi gì


def test_empty_patch_and_unknown_novel(api_client, nid):
    assert api_client.patch(f"/api/novels/{nid}", json={}).status_code == 400
    assert api_client.patch("/api/novels/999999", json={"title": "x"}).status_code == 404


# --- ảnh bìa ------------------------------------------------------------------------------

def test_upload_get_replace_remove(api_client, nid):
    r = _put_cover(api_client, nid, _img(1200, 1800, "JPEG"), "bia.jpg")
    assert r.status_code == 200, r.text
    url1 = r.json()["cover_url"]
    assert url1.startswith(f"/api/novels/{nid}/cover?v=")
    g = api_client.get(url1)
    assert g.status_code == 200 and g.headers["content-type"] == "image/webp"
    assert g.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert "noindex" in g.headers["x-robots-tag"]
    assert Image.open(BytesIO(g.content)).size == (600, 900)
    assert api_client.get("/api/novels").json()[0]["cover_url"] == url1

    url2 = _put_cover(api_client, nid, _img(300, 450)).json()["cover_url"]
    assert url2 != url1
    assert Image.open(BytesIO(api_client.get(url2).content)).size == (300, 450)

    assert api_client.delete(f"/api/novels/{nid}/cover").status_code == 204
    assert api_client.get(f"/api/novels/{nid}").json()["cover_url"] is None
    assert api_client.get(f"/api/novels/{nid}/cover").status_code == 404
    assert api_client.delete(f"/api/novels/{nid}/cover").status_code == 204  # idempotent


def test_not_an_image_keeps_previous(api_client, nid):
    url = _put_cover(api_client, nid, _img()).json()["cover_url"]
    r = _put_cover(api_client, nid, b"van ban doi duoi " * 20, "bia.jpg")
    assert r.status_code == 400 and r.json()["field"] == "cover"
    assert "không phải ảnh JPG, PNG hoặc WebP" in r.json()["detail"]
    assert api_client.get(f"/api/novels/{nid}").json()["cover_url"] == url


def test_too_large_and_empty(api_client, nid, monkeypatch):
    monkeypatch.setattr(routers.library, "COVER_MAX_BYTES", 100)
    r = _put_cover(api_client, nid, _img())
    assert r.status_code == 413 and "10 MB" in r.json()["detail"]
    monkeypatch.undo()
    assert _put_cover(api_client, nid, b"").status_code == 400
    assert api_client.get(f"/api/novels/{nid}").json()["cover_url"] is None


def test_delete_novel_removes_cover(api_client, nid):
    _put_cover(api_client, nid, _img())
    api_client.delete(f"/api/novels/{nid}?confirm=true")
    assert api_client.get(f"/api/novels/{nid}/cover").status_code == 404


def test_requires_session_and_csrf(anon_client, api_client, nid):
    _put_cover(api_client, nid, _img())
    r = anon_client.get(f"/api/novels/{nid}/cover")
    assert r.status_code == 401 and not r.headers["content-type"].startswith("image/")
    assert anon_client.patch(f"/api/novels/{nid}", json={"title": "x"}).status_code == 401
    assert anon_client.post("/api/covers/fetch", json={"url": "https://a.test/x.png"}
                            ).status_code == 401
    api_client.headers.pop("X-Requested-With")
    assert api_client.patch(f"/api/novels/{nid}", json={"title": "x"}).status_code == 403
    assert _put_cover(api_client, nid, _img()).status_code == 403
    assert api_client.delete(f"/api/novels/{nid}/cover").status_code == 403
    assert api_client.post("/api/covers/fetch", json={"url": "https://a.test/x.png"}
                           ).status_code == 403


# --- ảnh từ link ---------------------------------------------------------------------------

def test_fetch_preview_saves_nothing(api_client, container, nid):
    fake = FakeFetcher(_img(1200, 1800, "JPEG"))
    container.library.cover_fetcher = fake
    r = api_client.post("/api/covers/fetch", json={"url": "https://anh.test/bia.jpg"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "no-store"
    assert (r.headers["x-cover-width"], r.headers["x-cover-height"]) == ("600", "900")
    assert fake.urls == ["https://anh.test/bia.jpg"]
    assert api_client.get(f"/api/novels/{nid}").json()["cover_url"] is None
    # lưu: gửi lại chính ảnh xem trước qua đường upload
    saved = api_client.put(f"/api/novels/{nid}/cover",
                           files={"file": ("bia.webp", r.content, "image/webp")})
    assert saved.status_code == 200 and saved.json()["cover_url"]


@pytest.mark.parametrize("error", [
    CoverFetchError("invalid_url", "Chỉ nhận link http hoặc https."),
    CoverFetchError("blocked_address", "Không được tải ảnh từ địa chỉ nội bộ."),
    CoverFetchError("download_failed", "Không tải được ảnh từ link này (máy chủ trả lỗi 404)."),
    CoverFetchError("too_large", "Ảnh ở link này lớn hơn 10 MB."),
])
def test_fetch_errors_400_with_reason(api_client, container, error):
    container.library.cover_fetcher = FakeFetcher(error)
    r = api_client.post("/api/covers/fetch", json={"url": "https://anh.test/x"})
    assert r.status_code == 400
    assert r.json() == {"detail": str(error), "field": "cover_url", "reason": error.reason}


def test_fetch_html_is_not_an_image(api_client, container):
    container.library.cover_fetcher = FakeFetcher(b"<html>trang web</html>")
    r = api_client.post("/api/covers/fetch", json={"url": "https://anh.test/trang"})
    assert r.status_code == 400 and r.json()["field"] == "cover"


def test_fetch_real_validation_long_url_is_400_not_422(api_client):
    """Bộ tải ảnh thật kiểm link trước khi gọi mạng: link quá dài → 400 có field."""
    r = api_client.post("/api/covers/fetch", json={"url": "https://a.test/" + "a" * 2000})
    assert r.status_code == 400 and r.json()["reason"] == "invalid_url"
    r = api_client.post("/api/covers/fetch", json={"url": "http://127.0.0.1:8000/api/novels"})
    assert r.status_code == 400 and r.json()["field"] == "cover_url"
