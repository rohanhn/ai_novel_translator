"""PrefetchService: các scenario của spec translation-prefetch."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.application.jobs import Lane, TranslationJobManager
from novel_translator.application.prefetch import PrefetchService, ReadingSignal
from novel_translator.application.services import NotFoundError, TranslationService
from novel_translator.domain.models import Chapter, ChapterStatus, Novel
from novel_translator.domain.ports import DailyQuotaError
from novel_translator.providers.chain import ChainLink, ChainProvider
from novel_translator.providers.echo import EchoProvider
from novel_translator.storage.quota_repo import PostgresQuotaTracker

WAIT = 5.0


class Recording(EchoProvider):
    """Echo ghi lại policy và có thể chặn để giữ job ở trạng thái đang chạy."""

    def __init__(self, name="gemini"):
        super().__init__(name=name)
        self.policies: list = []
        self.hold = threading.Event()
        self.hold.set()
        self.started = threading.Event()

    def stream(self, request, policy=None, on_event=None):
        self.policies.append(policy)
        self.started.set()
        assert self.hold.wait(WAIT)
        return super().stream(request)


@pytest.fixture
def env(repo, db):
    novel = repo.add_novel(Novel(title="t"))
    repo.add_chapters([Chapter(novel_id=novel.id, index=i, title=f"第{i}章", source_text=f"内容{i}")
                       for i in range(1, 11)])
    quota = PostgresQuotaTracker(db)
    step1, step2 = Recording(), Recording()
    chain = ChainProvider([ChainLink(step1, "chinh"), ChainLink(step2, "nhe")], quota,
                          sleep=lambda s: None)
    svc = TranslationService(repo, lambda n, m: chain, 20000)
    jobs = TranslationJobManager(svc)
    pre = PrefetchService(repo, jobs, quota)
    yield novel.id, pre, jobs, svc, repo, quota, step1, step2
    step1.hold.set()
    jobs.shutdown()


def _wait_job(jobs, nid, idx):
    job = jobs.get(nid, idx)
    if job:
        assert job.wait(WAIT)
    return job


def test_read_long_enough_prefetches_next_in_background(env):
    nid, pre, jobs, _, repo, quota, step1, step2 = env
    d = pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S)
    assert d.started and d.chapter_index == 8
    _wait_job(jobs, nid, 8)
    assert repo.get_chapter(nid, 8).status == ChapterStatus.TRANSLATED
    assert len(step1.policies) == 1 and not step2.policies
    assert [u.requests for u in quota.usage_today()] == [1]


def test_prefetch_hitting_daily_quota_does_not_fall_back(env):
    nid, pre, jobs, _, repo, quota, step1, step2 = env
    step1.errors = [DailyQuotaError("hết", datetime.now(timezone.utc) + timedelta(hours=3))]
    assert pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S).started
    job = _wait_job(jobs, nid, 8)
    assert job.terminal_event.type == "quota_exhausted"
    assert not step2.policies  # policy BACKGROUND: không dùng bước dự phòng
    assert repo.get_chapter(nid, 8).status == ChapterStatus.PENDING
    assert quota.exhausted_until(1) is not None


@pytest.mark.parametrize("signal", list(ReadingSignal))
def test_every_signal_kind_triggers(env, signal):
    nid, pre, jobs, *_ = env
    assert pre.on_reading_signal(nid, 3, signal).started
    _wait_job(jobs, nid, 4)


def test_next_already_translated_no_request(env):
    nid, pre, _, svc, _, _, step1, _ = env
    svc.translate_chapter(nid, 8)
    step1.policies.clear()
    d = pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S)
    assert (d.started, d.reason) == (False, "already_translated")
    assert step1.policies == []


def test_next_edited_blocked(env):
    nid, pre, _, _, repo, *_ = env
    ch = repo.get_chapter(nid, 8)
    ch.status, ch.translated_text = ChapterStatus.EDITED, "sửa tay"
    repo.update_chapter(ch)
    assert pre.on_reading_signal(nid, 7, ReadingSignal.SCROLLED_60).reason == "edited"


def test_last_chapter_no_prefetch(env):
    nid, pre, *_ = env
    d = pre.on_reading_signal(nid, 10, ReadingSignal.VISIBLE_30S)
    assert (d.started, d.reason) == (False, "no_next_chapter")


def test_next_being_translated_not_duplicated(env):
    nid, pre, jobs, _, _, _, step1, _ = env
    step1.hold.clear()
    jobs.submit(nid, 8, Lane.FOREGROUND)  # chủ sở hữu đã mở chương 8
    assert step1.started.wait(WAIT)
    d = pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S)
    assert (d.started, d.reason) == (False, "in_progress")
    step1.hold.set()
    _wait_job(jobs, nid, 8)
    assert len(step1.policies) == 1


def test_disabled_setting(env):
    nid, pre, _, _, repo, *_ = env
    assert pre.enabled()  # mặc định bật
    repo.set_preference("prefetch", False)
    d = pre.on_reading_signal(nid, 7, ReadingSignal.EXPLICIT)
    assert (d.started, d.reason) == (False, "disabled")


def test_primary_exhausted_blocks_prefetch_but_not_foreground(env):
    nid, pre, _, svc, _, quota, step1, step2 = env
    quota.mark_exhausted(1, datetime.now(timezone.utc) + timedelta(hours=5))
    d = pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S)
    assert (d.started, d.reason) == (False, "primary_exhausted")
    assert not step1.policies and not step2.policies  # không request nào tới bước 2
    # Spec "Owner opens chapter after primary exhausted": foreground dùng bước 2.
    ch = svc.translate_chapter(nid, 8)
    assert (ch.model, ch.chain_step) == ("nhe", 2)


def test_no_chaining(env):
    nid, pre, jobs, _, repo, *_ = env
    pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S)
    _wait_job(jobs, nid, 8)
    assert repo.get_chapter(nid, 9).status == ChapterStatus.PENDING
    assert jobs.get(nid, 9) is None


def test_one_chapter_depth_replaces_stale_queued_prefetch(env):
    nid, pre, jobs, _, repo, _, step1, _ = env
    step1.hold.clear()
    pre.on_reading_signal(nid, 1, ReadingSignal.VISIBLE_30S)  # chương 2 đang chạy
    assert step1.started.wait(WAIT)
    pre.on_reading_signal(nid, 4, ReadingSignal.VISIBLE_30S)  # chương 5 chờ
    pre.on_reading_signal(nid, 6, ReadingSignal.VISIBLE_30S)  # đọc tiếp: 7 thay cho 5
    assert jobs.get(nid, 5) is None and jobs.get(nid, 7) is not None
    step1.hold.set()
    _wait_job(jobs, nid, 2)
    _wait_job(jobs, nid, 7)
    assert repo.get_chapter(nid, 5).status == ChapterStatus.PENDING


def test_leave_cancels_queued_but_running_completes(env):
    nid, pre, jobs, _, repo, _, step1, _ = env
    step1.hold.clear()
    pre.on_reading_signal(nid, 7, ReadingSignal.VISIBLE_30S)  # 8 đang stream
    assert step1.started.wait(WAIT)
    pre.on_reading_signal(nid, 2, ReadingSignal.VISIBLE_30S)  # 3 còn chờ
    assert pre.on_leave(nid) == 1
    step1.hold.set()
    _wait_job(jobs, nid, 8)
    assert repo.get_chapter(nid, 8).status == ChapterStatus.TRANSLATED  # chạy đến hết
    assert repo.get_chapter(nid, 3).status == ChapterStatus.PENDING


def test_unknown_chapter(env):
    nid, pre, *_ = env
    with pytest.raises(NotFoundError):
        pre.on_reading_signal(nid, 99, ReadingSignal.VISIBLE_30S)


def test_prefetch_skipped_while_novel_is_updating(env):
    nid, pre, jobs, *_ = env
    with jobs.hold_novel(nid):
        d = pre.on_reading_signal(nid, 3, ReadingSignal.EXPLICIT)
    assert not d.started and d.reason == "updating"
    assert jobs.get(nid, 4) is None
