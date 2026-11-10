"""API cập nhật chương từ TXT (spec `chapter-update`, design D5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel_translator.config import Settings
from novel_translator.container import build_container, get_container
from novel_translator.interfaces.api.app import app


def zh(numbers, revised=()) -> str:
    out = []
    for n in numbers:
        body = f"林动第{n}章的正文，内容足够长。" * 3 + ("作者修改。" if n in revised else "")
        out.append(f"第{n}章 标题{n}\n{body}")
    return "\n".join(out)


def make_novel(client, numbers=range(1, 6)) -> int:
    r = client.post("/api/imports", files={"file": ("a.txt", zh(numbers).encode(), "text/plain")})
    p = r.json()
    r = client.post(f"/api/imports/{p['id']}/commit", json={"boundaries": p["boundaries"],
                                                             "title": "Vũ Động"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload_update(client, novel_id, text: str):
    return client.post("/api/imports", data={"novel_id": str(novel_id)},
                       files={"file": ("moi.txt", text.encode(), "text/plain")})


def test_upload_for_an_existing_novel(api_client):
    nid = make_novel(api_client)
    r = upload_update(api_client, nid, zh(range(1, 8)))
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["novel_id"] == nid and len(p["chapters"]) == 7
    assert len(api_client.get(f"/api/novels/{nid}/chapters").json()) == 5  # chưa ghi gì


def test_unknown_novel(api_client):
    assert upload_update(api_client, 987654, zh([1])).status_code == 404


def test_append_flow(api_client):
    nid = make_novel(api_client)
    p = upload_update(api_client, nid, zh(range(1, 8))).json()
    body = {"mode": "append", "boundaries": p["boundaries"]}
    r = api_client.post(f"/api/imports/{p['id']}/update-preview", json=body)
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["anchor"] == {"index": 5, "title": "第5章 标题5", "position": 5, "match": "content"}
    assert [c["title"] for c in pv["to_add"]] == ["第6章 标题6", "第7章 标题7"]
    assert pv["needs_start"] is False and pv["counts"] is None
    r = api_client.post(f"/api/imports/{p['id']}/update",
                        json={**body, "revision": pv["revision"]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["added"], res["chapter_count"], res["novel"]["id"]) == (2, 7, nid)
    chs = api_client.get(f"/api/novels/{nid}/chapters").json()
    assert len(chs) == 7
    assert api_client.get(f"/api/imports/{p['id']}").status_code == 410


def test_replace_flow_with_delete(api_client):
    nid = make_novel(api_client)
    p = upload_update(api_client, nid, zh([1, 2, 4, 5, 6], revised={2})).json()
    body = {"mode": "replace", "boundaries": p["boundaries"]}
    pv = api_client.post(f"/api/imports/{p['id']}/update-preview", json=body).json()
    assert pv["counts"] == {"reuse": 3, "changed": 1, "new": 1, "missing": 1}
    assert [m["index"] for m in pv["missing"]] == [3]
    assert [c["index"] for c in pv["changed"]] == [2]
    body["delete"] = [3]
    pv = api_client.post(f"/api/imports/{p['id']}/update-preview", json=body).json()
    r = api_client.post(f"/api/imports/{p['id']}/update", json={**body, "revision": pv["revision"]})
    assert r.status_code == 200, r.text
    assert (r.json()["deleted"], r.json()["chapter_count"]) == (1, 5)
    titles = [c["title"] for c in api_client.get(f"/api/novels/{nid}/chapters").json()]
    assert titles == [f"第{n}章 标题{n}" for n in (1, 2, 4, 5, 6)]


def test_mode_missing(api_client):
    nid = make_novel(api_client)
    p = upload_update(api_client, nid, zh(range(1, 7))).json()
    for path, extra in (("update-preview", {}), ("update", {"revision": "x"})):
        r = api_client.post(f"/api/imports/{p['id']}/{path}",
                            json={"boundaries": p["boundaries"], **extra})
        assert r.status_code == 422
    assert len(api_client.get(f"/api/novels/{nid}/chapters").json()) == 5


def test_no_anchor_and_no_usable_numbers_requires_start(api_client):
    nid = make_novel(api_client)
    p = upload_update(api_client, nid, "番外 一\n番外内容一\n番外 二\n番外内容二").json()
    body = {"mode": "append", "boundaries": p["boundaries"]}
    pv = api_client.post(f"/api/imports/{p['id']}/update-preview", json=body).json()
    assert pv["needs_start"] is True and pv["to_add"] == []
    r = api_client.post(f"/api/imports/{p['id']}/update", json={**body, "revision": pv["revision"]})
    assert r.status_code == 422 and r.json()["code"] == "start_required"
    body["start"] = 1
    pv = api_client.post(f"/api/imports/{p['id']}/update-preview", json=body).json()
    r = api_client.post(f"/api/imports/{p['id']}/update", json={**body, "revision": pv["revision"]})
    assert r.status_code == 200 and r.json()["added"] == 2


def test_nothing_new_and_stale_and_language(api_client, container):
    nid = make_novel(api_client)
    p = upload_update(api_client, nid, zh(range(1, 6))).json()
    body = {"mode": "append", "boundaries": p["boundaries"]}
    pv = api_client.post(f"/api/imports/{p['id']}/update-preview", json=body).json()
    assert pv["nothing_new"] is True
    r = api_client.post(f"/api/imports/{p['id']}/update", json={**body, "revision": pv["revision"]})
    assert r.status_code == 409 and r.json()["code"] == "nothing_new"

    p = upload_update(api_client, nid, zh(range(1, 7))).json()
    body = {"mode": "append", "boundaries": p["boundaries"]}
    r = api_client.post(f"/api/imports/{p['id']}/update", json={**body, "revision": "cu"})
    assert r.status_code == 409 and r.json()["code"] == "stale_preview"

    vi = "\n".join(f"Chương {n}: Tên\n" + "Lâm Động đứng trên núi nhìn về phía xa. " * 3
                   for n in (6, 7))
    p = upload_update(api_client, nid, vi).json()
    r = api_client.post(f"/api/imports/{p['id']}/update-preview",
                        json={"mode": "append", "boundaries": p["boundaries"]})
    assert r.status_code == 422 and r.json()["code"] == "language_mismatch"


def test_preview_expired(api_client):
    r = api_client.post("/api/imports/khong-co/update",
                        json={"mode": "append", "boundaries": [0], "revision": "x"})
    assert r.status_code == 410


def test_routes_require_session_and_csrf(container, db, password_hash):
    app.dependency_overrides[get_container] = lambda: container
    try:
        anon = TestClient(app, headers={"X-Requested-With": "test"})
        for path in ("/api/imports/x/update-preview", "/api/imports/x/update"):
            assert anon.post(path, json={}).status_code == 401
        no_csrf = TestClient(app)
        for path in ("/api/imports/x/update-preview", "/api/imports/x/update"):
            assert no_csrf.post(path, json={}).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_container_builds_chapter_updates(db, password_hash):
    c = build_container(Settings(provider="echo", password_hash=password_hash,
                                 cookie_secure=False), pool=db)
    assert c.chapter_updates.drafts is c.imports
