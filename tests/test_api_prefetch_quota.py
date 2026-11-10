"""API tín hiệu đọc (spec translation-prefetch) và lượt dùng quota (spec llm-providers)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

RAW = "".join(f"第{i}章 标题\n内容{i}\n" for i in range(1, 4)).encode()


def _novel(client) -> int:
    return client.post("/api/novels", files={"file": ("n.txt", RAW)}).json()["id"]


def _wait_translated(client, nid, index, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get(f"/api/novels/{nid}/chapters/{index}").json()["status"] == "translated":
            return
        time.sleep(0.02)
    raise AssertionError("chưa dịch xong")


def test_reading_signal_prefetches_next_chapter(api_client, container):
    nid = _novel(api_client)
    r = api_client.post(f"/api/novels/{nid}/chapters/1/reading-signal",
                        json={"signal": "scrolled_60"})
    assert r.status_code == 200
    assert r.json() == {"started": True, "reason": "started", "chapter_index": 2}
    _wait_translated(api_client, nid, 2)
    again = api_client.post(f"/api/novels/{nid}/chapters/1/reading-signal",
                            json={"signal": "explicit"}).json()
    assert again["started"] is False and again["reason"] == "already_translated"
    last = api_client.post(f"/api/novels/{nid}/chapters/3/reading-signal",
                           json={"signal": "visible_30s"}).json()
    assert last["reason"] == "no_next_chapter"
    container.jobs.shutdown()


def test_reading_signal_respects_setting_and_validates(api_client):
    nid = _novel(api_client)
    api_client.patch("/api/preferences", json={"prefetch": False})
    r = api_client.post(f"/api/novels/{nid}/chapters/1/reading-signal",
                        json={"signal": "explicit"})
    assert r.json()["reason"] == "disabled"
    bad = api_client.post(f"/api/novels/{nid}/chapters/1/reading-signal",
                          json={"signal": "opened"})
    assert bad.status_code == 422
    missing = api_client.post(f"/api/novels/{nid}/chapters/9/reading-signal",
                              json={"signal": "explicit"})
    assert missing.status_code == 404


def test_leave_novel(api_client):
    nid = _novel(api_client)
    r = api_client.post(f"/api/novels/{nid}/leave")
    assert r.status_code == 200 and r.json() == {"cancelled": 0}
    assert api_client.post("/api/novels/999/leave").status_code == 404


def test_quota_usage(api_client, container):
    steps = container.settings.chain_steps()
    r = api_client.get("/api/settings/quota").json()
    assert [s["requests_today"] for s in r["steps"]] == [0] * len(steps)
    assert all(s["exhausted"] is False for s in r["steps"])
    for _ in range(12):
        container.quota.record_success(1)
    reset = datetime.now(timezone.utc) + timedelta(hours=2)
    container.quota.mark_exhausted(1, reset)
    r = api_client.get("/api/settings/quota").json()
    step1 = r["steps"][0]
    assert step1["requests_today"] == 12 and step1["exhausted"] is True
    assert datetime.fromisoformat(step1["reset_at"]) == reset
    assert (step1["provider"], step1["model"]) == (steps[0].provider, steps[0].model)
    assert all(s["requests_today"] == 0 for s in r["steps"][1:])
    assert r["provider_override"] == "echo"


def test_endpoints_require_session(anon_client):
    assert anon_client.get("/api/settings/quota").status_code == 401
    assert anon_client.post("/api/novels/1/chapters/1/reading-signal",
                            json={"signal": "explicit"}).status_code == 401
