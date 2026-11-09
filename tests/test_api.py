def test_api_flow(api_client):
    raw = "第一章 少年\n林动站在山上。\n第二章 修炼\n林动开始修炼。\n".encode()
    r = api_client.post("/novels", files={"file": ("demo.txt", raw, "text/plain")})
    assert r.status_code == 201
    nid = r.json()["id"]

    assert len(api_client.get(f"/novels/{nid}/chapters").json()) == 2

    r = api_client.put(f"/novels/{nid}/glossary",
                       json={"source_term": "林动", "target_term": "Lâm Động"})
    assert r.status_code == 200

    r = api_client.post(f"/novels/{nid}/chapters/1/translate", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "translated"


def test_api_404(api_client):
    assert api_client.get("/novels/999/chapters").status_code == 404


def test_api_unknown_provider(api_client):
    raw = "第一章 a\nb\n".encode()
    nid = api_client.post("/novels", files={"file": ("x.txt", raw)}).json()["id"]
    r = api_client.post(f"/novels/{nid}/chapters/1/translate", json={"provider": "nope"})
    assert r.status_code == 400
