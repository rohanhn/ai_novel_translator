"""SSE của job dịch (spec interfaces "Translation event stream", design D5)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from novel_translator.domain.models import ChainEvent
from novel_translator.domain.ports import RefusalError
from novel_translator.interfaces.api.routers import chapters
from novel_translator.pipeline.sections import Paragraph, Title

RAW = "第一章 少年\n林动站在山上。\n第二章 修炼\n林动开始修炼。\n".encode()


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln and not ln.startswith(":")]
        if not lines:
            continue
        fields = dict(ln.split(": ", 1) for ln in lines)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


@pytest.fixture
def novel(api_client):
    r = api_client.post("/api/novels", files={"file": ("demo.txt", RAW)})
    return r.json()["id"]


@pytest.fixture
def gated(container, monkeypatch):
    """Thay translate_chapter bằng bản phát 10 đoạn, chờ `gate`, rồi phát thêm 2 đoạn."""
    gate = threading.Event()
    state = {"fail": None}

    def fake(novel_id, index, *, on_event, **kw):
        on_event(Title("Thiếu niên"))
        for i in range(1, 11):
            on_event(Paragraph(f"đoạn {i}"))
        on_event(ChainEvent("fallback_step", 2, "echo", "lite"))
        assert gate.wait(5)
        if state["fail"]:
            raise state["fail"]
        for i in range(11, 13):
            on_event(Paragraph(f"đoạn {i}"))
        return container.repo.get_chapter(novel_id, index)

    monkeypatch.setattr(container.translation, "translate_chapter", fake)
    yield gate, state
    gate.set()
    container.jobs.shutdown()


def _start(api_client, container, novel):
    assert api_client.post(f"/api/novels/{novel}/chapters/1/translate", json={}).status_code == 202
    job = container.jobs.get(novel, 1)
    deadline = time.monotonic() + 5
    while sum(e.type == "paragraph" for e in job.events) < 10:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    return job


def _release_when_subscribed(job, gate, n: int) -> threading.Thread:
    def run():
        deadline = time.monotonic() + 5
        while job.subscriber_count < n and time.monotonic() < deadline:
            time.sleep(0.01)
        gate.set()

    t = threading.Thread(target=run)
    t.start()
    return t


def test_subscribe_mid_way_replays_then_continues(api_client, container, novel, gated):
    gate, _ = gated
    job = _start(api_client, container, novel)
    releaser = _release_when_subscribed(job, gate, 1)
    r = api_client.get(f"/api/novels/{novel}/chapters/1/stream")
    releaser.join()
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-accel-buffering"] == "no"
    assert r.headers["cache-control"] == "no-cache"
    events = parse_sse(r.text)
    paragraphs = [d["text"] for t, d in events if t == "paragraph"]
    assert paragraphs == [f"đoạn {i}" for i in range(1, 13)]  # 10 đoạn cũ trước, rồi đoạn mới
    assert events[0] == ("title", {"text": "Thiếu niên"})
    assert ("fallback_step", {"step": 2, "provider": "echo", "model": "lite", "delay": None}
            ) in events
    assert [t for t, _ in events].count("completed") == 1 and events[-1][0] == "completed"
    assert "id: 1\n" in r.text


def test_two_clients_receive_same_job(api_client, container, novel, gated):
    gate, _ = gated
    job = _start(api_client, container, novel)
    results: list[str] = []

    def read():
        results.append(api_client.get(f"/api/novels/{novel}/chapters/1/stream").text)

    readers = [threading.Thread(target=read) for _ in range(2)]
    for t in readers:
        t.start()
    releaser = _release_when_subscribed(job, gate, 2)
    for t in readers:
        t.join(10)
    releaser.join()
    assert len(results) == 2
    a, b = (parse_sse(x) for x in results)
    assert a == b
    assert sum(t == "paragraph" for t, _ in a) == 12 and a[-1][0] == "completed"


def test_failure_after_202_arrives_as_failed_event(api_client, container, novel, gated):
    gate, state = gated
    state["fail"] = RefusalError("Bị từ chối.")
    job = _start(api_client, container, novel)
    gate.set()
    assert job.wait(5)
    # job đã kết thúc trước khi client mở stream: vẫn nhận đủ sự kiện và lỗi kèm loại lỗi
    events = parse_sse(api_client.get(f"/api/novels/{novel}/chapters/1/stream").text)
    assert events[-1] == ("failed", {"category": "refusal", "message": "Bị từ chối."})
    assert sum(t == "paragraph" for t, _ in events) == 10


def test_keep_alive_comments(api_client, container, novel, gated, monkeypatch):
    gate, _ = gated
    monkeypatch.setattr(chapters, "KEEPALIVE_S", 0.02)
    job = _start(api_client, container, novel)

    def release_later():
        deadline = time.monotonic() + 5
        while job.subscriber_count < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.15)
        gate.set()

    t = threading.Thread(target=release_later)
    t.start()
    r = api_client.get(f"/api/novels/{novel}/chapters/1/stream")
    t.join()
    assert ": keep-alive\n\n" in r.text
    assert parse_sse(r.text)[-1][0] == "completed"


def test_stream_without_job(api_client, container, novel):
    assert api_client.get(f"/api/novels/{novel}/chapters/2/stream").status_code == 404
    container.translation.translate_chapter(novel, 2)
    events = parse_sse(api_client.get(f"/api/novels/{novel}/chapters/2/stream").text)
    assert [t for t, _ in events] == ["completed"]
    assert events[0][1]["status"] == "translated"
