"""QuotaTracker PostgreSQL: đếm lượt, hết quota có thời hạn, an toàn khi ghi đồng thời."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from novel_translator.domain.models import StepUsage
from novel_translator.domain.ports import QuotaTracker
from novel_translator.storage.quota_repo import PostgresQuotaTracker


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# 10:00 giờ Pacific ngày 2026-11-09
T0 = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)


def test_counts_successes_per_step(db):
    t = PostgresQuotaTracker(db, clock=Clock(T0))
    assert isinstance(t, QuotaTracker)
    for _ in range(12):
        t.record_success(1)
    t.record_success(2)
    assert t.usage_today() == [StepUsage(1, 12), StepUsage(2, 1)]


def test_new_day_resets_count(db):
    clock = Clock(T0)
    t = PostgresQuotaTracker(db, clock=clock)
    t.record_success(1)
    clock.now = T0 + timedelta(days=1)
    assert t.usage_today() == []
    t.record_success(1)
    assert t.usage_today() == [StepUsage(1, 1)]


def test_exhausted_until_expires_at_reset(db):
    clock = Clock(T0)
    t = PostgresQuotaTracker(db, clock=clock)
    reset = T0 + timedelta(hours=14)
    assert t.exhausted_until(1) is None
    t.mark_exhausted(1, reset)
    assert t.exhausted_until(1) == reset
    assert t.exhausted_until(2) is None
    assert t.usage_today() == [StepUsage(1, 0, reset)]
    # một reset sớm hơn không rút ngắn thời hạn đã biết
    t.mark_exhausted(1, T0 + timedelta(hours=1))
    assert t.exhausted_until(1) == reset
    clock.now = reset + timedelta(seconds=1)  # qua thời điểm reset → tự hết hiệu lực
    assert t.exhausted_until(1) is None


def test_exhaustion_spanning_day_boundary(db):
    clock = Clock(T0)
    t = PostgresQuotaTracker(db, clock=clock)
    t.mark_exhausted(1, T0 + timedelta(days=1, hours=1))
    clock.now = T0 + timedelta(days=1)  # đã sang ngày mới nhưng chưa tới reset
    assert t.exhausted_until(1) is not None


def test_concurrent_increments_lose_nothing(db):
    t = PostgresQuotaTracker(db, clock=Clock(T0))
    n_threads, per_thread = 4, 25
    barrier = threading.Barrier(n_threads)

    def work():
        barrier.wait()
        for _ in range(per_thread):
            t.record_success(1)

    threads = [threading.Thread(target=work) for _ in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert t.usage_today() == [StepUsage(1, n_threads * per_thread)]
