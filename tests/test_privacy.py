"""noindex + robots.txt (spec access-control "No search indexing")."""

from __future__ import annotations


def test_crawler_request_robots_txt(anon_client):
    r = anon_client.get("/robots.txt")  # công khai, không cần đăng nhập
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text == "User-agent: *\nDisallow: /\n"


def test_every_response_has_noindex_header(anon_client, api_client):
    responses = [
        anon_client.get("/robots.txt"),
        anon_client.get("/health"),
        anon_client.get("/novels"),  # 401
        anon_client.post("/api/auth/logout", headers={"X-Requested-With": ""}),  # 403
        anon_client.post("/api/auth/login", json={"password": "sai"}),  # 401
        api_client.get("/novels"),  # 200
        api_client.get("/khong-ton-tai"),  # 404
    ]
    for r in responses:
        assert r.headers.get("x-robots-tag") == "noindex, nofollow", (r.request.url, r.status_code)
