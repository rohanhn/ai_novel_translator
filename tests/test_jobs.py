"""TranslationJobManager: một job mỗi chương, hai làn, phát lại sự kiện, nâng làn, hủy."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.application.jobs import JobState, Lane, TranslationJobManager
from novel_translator.application.services import NovelBusyError, TranslationService
from novel_translator.domain.models import ChainPolicy, Chapter, ChapterStatus, Novel
from novel_translator.domain.ports import DailyQuotaError, RefusalError, StreamingProvider
from novel_translator.providers.echo import EchoProvider

WAIT = 5.0


class Gated(StreamingProvider):
    """Provider giả: chương nằm trong `gates` sẽ dừng sau dòng đầu tới khi gate được mở."""

    name, default_model = "gated", "g"

    def __init__(self):
        self.gates: dict[str, threading.Event] = {}
        self.started: dict[str, threading.Event] = {}
        self.calls: list[tuple[str, ChainPolicy]] = []
        self.errors: dict[str, Exception] = {}

    def gate(self, marker: str) -> threading.Event:
        self.started[marker] = threading.Event()
        self.gates[marker] = threading.Event()
        return self.gates[marker]

    def stream(self, request, policy=None, on_event=None):
        marker = next((m for m in ("一", "二", "三", "四") if m in request.user), "?")
        self.calls.append((marker, policy))
        if marker in self.errors:
            raise self.errors[marker]
        return self._gen(request, marker)

    def _gen(self, request, marker):
        lines = [ln for ln in request.user.splitlines(keepends=True)]
        for i, line in enumerate(lines):
            yield line if line.startswith("<<") else f"[VI] {line}"
            if i == 3 and marker in self.gates:  # sau <<TITLE>>, tiêu đề, <<BODY>>, đoạn 1
                self.started[marker].set()
                assert self.gates[marker].wait(WAIT)


@pytest.fixture
def env(repo):
    novel = repo.add_novel(Novel(title="t"))
    repo.add_chapters([
        Chapter(novel_id=novel.id, index=i, title=f"第{m}章", source_text=f"{m}甲\n{m}乙\n{m}丙")
        for i, m in enumerate("一二三四", start=1)
    ])
    provider = Gated()
    svc = TranslationService(repo, lambda name, model: provider, 20000)
    mgr = TranslationJobManager(svc)
    yield novel.id, provider, mgr, repo
    for g in provider.gates.values():
        g.set()
    mgr.shutdown()


def types(events):
    return [e.type for e in events]


def test_completed_job_events_and_status(env):
    nid, _, mgr, repo = env
    job = mgr.submit(nid, 1)
    assert job.wait(WAIT)
    evs = job.events
    assert types(evs) == ["title", "paragraph", "paragraph", "paragraph", "completed"]
    assert [e.data["index"] for e in evs if e.type == "paragraph"] == [1, 2, 3]
    assert evs[-1].data["status"] == "translated"
    assert repo.get_chapter(nid, 1).status == ChapterStatus.TRANSLATED
    # bản dịch giả còn nguyên chữ Hán: 第一章 (3) + 一甲, 一乙, 一丙 (6)
    assert evs[-1].data["untranslated_han"] == repo.get_chapter(nid, 1).untranslated_han == 9
    assert mgr.get(nid, 1) is None  # job xong thì rời registry


def test_same_chapter_single_job_and_single_request(env):
    nid, p, mgr, _ = env
    gate = p.gate("一")
    a = mgr.submit(nid, 1)
    b = mgr.submit(nid, 1, Lane.BACKGROUND)
    assert a is b
    gate.set()
    assert a.wait(WAIT)
    assert [c[0] for c in p.calls] == ["一"]


def test_late_subscriber_gets_replay_then_live(env):
    nid, p, mgr, _ = env
    gate = p.gate("一")
    job = mgr.submit(nid, 1)
    assert p.started["一"].wait(WAIT)
    early = job.subscribe()
    first = next(early)
    late = job.subscribe()  # đăng ký khi đã có sự kiện
    gate.set()
    rest_early = [first, *early]
    rest_late = list(late)
    assert types(rest_late) == types(rest_early) == [
        "title", "paragraph", "paragraph", "paragraph", "completed"]
    assert types(list(job.subscribe())) == types(rest_late)  # sau khi xong vẫn phát lại đủ


def test_foreground_not_blocked_by_running_prefetch(env):
    nid, p, mgr, _ = env
    gate = p.gate("一")
    bg = mgr.submit(nid, 1, Lane.BACKGROUND)
    assert p.started["一"].wait(WAIT)
    fg = mgr.submit(nid, 2, Lane.FOREGROUND)
    assert fg.wait(WAIT)  # xong trong khi prefetch vẫn đang chạy
    assert bg.state == JobState.RUNNING
    gate.set()
    assert bg.wait(WAIT)
    assert dict(p.calls) == {"一": ChainPolicy.BACKGROUND, "二": ChainPolicy.FOREGROUND}


def test_queued_prefetch_promoted_to_foreground(env):
    nid, p, mgr, _ = env
    gate = p.gate("一")
    mgr.submit(nid, 1, Lane.BACKGROUND)  # chiếm làn background
    assert p.started["一"].wait(WAIT)
    queued = mgr.submit(nid, 2, Lane.BACKGROUND)
    assert queued.state == JobState.QUEUED
    same = mgr.submit(nid, 2, Lane.FOREGROUND)  # chủ sở hữu mở chương 2
    assert same is queued and same.lane == Lane.FOREGROUND
    assert same.wait(WAIT)  # chạy ở làn foreground, không chờ chương 1
    assert ("二", ChainPolicy.FOREGROUND) in p.calls
    gate.set()


def test_running_prefetch_not_promoted(env):
    nid, p, mgr, _ = env
    gate = p.gate("一")
    job = mgr.submit(nid, 1, Lane.BACKGROUND)
    assert p.started["一"].wait(WAIT)
    assert mgr.submit(nid, 1, Lane.FOREGROUND) is job
    assert job.lane == Lane.BACKGROUND and job.policy == ChainPolicy.BACKGROUND
    gate.set()
    assert job.wait(WAIT)


def test_cancel_only_queued_jobs(env):
    nid, p, mgr, repo = env
    gate = p.gate("一")
    running = mgr.submit(nid, 1, Lane.BACKGROUND)
    assert p.started["一"].wait(WAIT)
    queued = mgr.submit(nid, 2, Lane.BACKGROUND)
    assert not mgr.cancel(nid, 1)  # đã gửi request → chạy đến hết
    assert mgr.cancel(nid, 2)
    assert queued.wait(WAIT) and queued.terminal_event.type == "cancelled"
    gate.set()
    assert running.wait(WAIT) and running.terminal_event.type == "completed"
    assert "二" not in [c[0] for c in p.calls]
    assert repo.get_chapter(nid, 2).status == ChapterStatus.PENDING


def test_cancel_queued_for_novel(env):
    nid, p, mgr, _ = env
    gate = p.gate("一")
    mgr.submit(nid, 1, Lane.BACKGROUND)
    assert p.started["一"].wait(WAIT)
    mgr.submit(nid, 2, Lane.BACKGROUND)
    mgr.submit(nid, 3, Lane.BACKGROUND)
    assert mgr.cancel_queued_for_novel(nid) == 2
    gate.set()


def test_failure_and_quota_terminal_events(env):
    nid, p, mgr, repo = env
    reset = datetime.now(timezone.utc) + timedelta(hours=2)
    p.errors["一"] = RefusalError("từ chối")
    p.errors["二"] = DailyQuotaError("hết", reset_at=reset)
    f = mgr.submit(nid, 1)
    q = mgr.submit(nid, 2)
    assert f.wait(WAIT) and q.wait(WAIT)
    assert f.terminal_event.type == "failed" and f.terminal_event.data["category"] == "refusal"
    assert q.terminal_event.type == "quota_exhausted"
    assert q.terminal_event.data["reset_at"] == reset.isoformat()
    assert repo.get_chapter(nid, 1).status == ChapterStatus.FAILED
    assert repo.get_chapter(nid, 2).status == ChapterStatus.PENDING


def test_two_subscribers_receive_same_events_with_echo_delay(repo):
    novel = repo.add_novel(Novel(title="t"))
    repo.add_chapters([Chapter(novel_id=novel.id, index=1, title="题",
                               source_text="\n".join(f"段{i}" for i in range(5)))])
    svc = TranslationService(repo, lambda n, m: EchoProvider(delay=0.01), 20000)
    mgr = TranslationJobManager(svc)
    try:
        job = mgr.submit(novel.id, 1)
        subs = [job.subscribe(), job.subscribe()]
        results = [list(s) for s in subs]
        assert results[0] == results[1]
        assert types(results[0]).count("paragraph") == 5
        assert results[0][-1].type == "completed"
    finally:
        mgr.shutdown()


# --- chapter-update: giữ truyện khi tải lại cả bộ (design D3) --------------------------------


def test_has_jobs_for_novel(env):
    nid, p, mgr, _ = env
    assert not mgr.has_jobs_for_novel(nid)
    gate = p.gate("一")
    job = mgr.submit(nid, 1, Lane.FOREGROUND)
    assert p.started["一"].wait(WAIT)
    assert mgr.has_jobs_for_novel(nid) and not mgr.has_jobs_for_novel(nid + 999)
    gate.set()
    assert job.wait(WAIT)
    assert not mgr.has_jobs_for_novel(nid)


def test_submit_rejected_while_novel_held_then_allowed(env, repo):
    nid, _p, mgr, _ = env
    other = repo.add_novel(Novel(title="khác"))
    repo.add_chapters([Chapter(novel_id=other.id, index=1, title="第一章", source_text="一甲")])
    with mgr.hold_novel(nid):
        with pytest.raises(NovelBusyError):
            mgr.submit(nid, 1, Lane.FOREGROUND)
        assert not mgr.has_jobs_for_novel(nid)
        other_job = mgr.submit(other.id, 1, Lane.FOREGROUND)  # truyện khác không bị ảnh hưởng
        assert other_job.wait(WAIT)
    job = mgr.submit(nid, 1, Lane.FOREGROUND)
    assert job.wait(WAIT) and job.terminal_event.type == "completed"


def test_hold_is_exclusive_and_released_on_error(env):
    nid, _, mgr, _ = env
    with mgr.hold_novel(nid), pytest.raises(NovelBusyError), mgr.hold_novel(nid):
        pass
    with pytest.raises(RuntimeError), mgr.hold_novel(nid):
        raise RuntimeError("lỗi")
    with mgr.hold_novel(nid):  # đã được nhả
        pass
