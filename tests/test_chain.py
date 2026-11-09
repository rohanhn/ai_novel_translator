"""ChainProvider: các scenario của spec llm-providers (fallback, quota, retry, policy)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.domain.models import ChainPolicy, CompletionRequest, StepUsage
from novel_translator.domain.ports import (
    DailyQuotaError,
    ProviderError,
    RateQuotaError,
    RefusalError,
    TruncatedError,
)
from novel_translator.providers.chain import ChainLink, ChainProvider
from novel_translator.providers.echo import EchoProvider

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
REQ = CompletionRequest(system="s", user="dòng 1\ndòng 2")


class FakeTracker:
    def __init__(self):
        self.until: dict[int, datetime] = {}
        self.success: dict[int, int] = {}

    def exhausted_until(self, step):
        u = self.until.get(step)
        return u if u and u > NOW else None

    def record_success(self, step):
        self.success[step] = self.success.get(step, 0) + 1

    def mark_exhausted(self, step, until):
        self.until[step] = until

    def usage_today(self):
        return [StepUsage(s, n) for s, n in sorted(self.success.items())]


def make_chain(p1: EchoProvider, p2: EchoProvider, tracker=None, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return ChainProvider(
        [ChainLink(p1, "model-chinh"), ChainLink(p2, "model-nhe")],
        tracker or FakeTracker(), sleep=sleeps.append, clock=lambda: NOW,
    )


def test_primary_success_counts_usage():
    p1, p2 = EchoProvider(name="gemini"), EchoProvider(name="gemini")
    chain = make_chain(p1, p2)
    run = chain.run(REQ)
    assert "".join(run) == "[VI] dòng 1\n[VI] dòng 2"
    assert (run.step, run.provider, run.model) == (1, "gemini", "model-chinh")
    assert p1.calls[0].model == "model-chinh" and not p2.calls
    assert chain.tracker.success == {1: 1}


def test_primary_exhausted_falls_back_to_step2():
    reset = NOW + timedelta(hours=14)
    p1 = EchoProvider(name="gemini", errors=[DailyQuotaError("hết", reset_at=reset)])
    p2 = EchoProvider(name="gemini")
    chain = make_chain(p1, p2)
    events = []
    run = chain.run(REQ, on_event=events.append)
    text = "".join(run)
    assert text.startswith("[VI]")
    assert (run.step, run.model) == (2, "model-nhe")
    assert p2.calls[0].model == "model-nhe"
    assert chain.tracker.until[1] == reset
    assert chain.tracker.success == {2: 1}
    assert [(e.kind, e.step, e.model) for e in events] == [("fallback_step", 2, "model-nhe")]
    res = make_chain(EchoProvider(errors=[DailyQuotaError("x", reset)]), EchoProvider()
                     ).complete(REQ)
    assert res.model == "model-nhe"  # bản dịch lưu lại model của bước 2


def test_exhausted_step_skipped_without_request():
    tracker = FakeTracker()
    tracker.until[1] = NOW + timedelta(hours=3)
    p1, p2 = EchoProvider(), EchoProvider()
    run = make_chain(p1, p2, tracker).run(REQ)
    "".join(run)
    assert not p1.calls and run.step == 2


def test_non_quota_error_stops_chain():
    p1, p2 = EchoProvider(errors=[RefusalError("từ chối")]), EchoProvider()
    with pytest.raises(RefusalError):
        "".join(make_chain(p1, p2).run(REQ))
    assert not p2.calls


def test_whole_chain_exhausted_reports_earliest_reset():
    r1, r2 = NOW + timedelta(hours=10), NOW + timedelta(hours=4)
    p1 = EchoProvider(errors=[DailyQuotaError("a", reset_at=r1)])
    p2 = EchoProvider(errors=[DailyQuotaError("b", reset_at=r2)])
    chain = make_chain(p1, p2)
    with pytest.raises(DailyQuotaError) as ei:
        "".join(chain.run(REQ))
    assert ei.value.reset_at == r2
    assert chain.tracker.success == {}


def test_daily_without_reset_time_uses_next_pacific_midnight():
    p1, p2 = EchoProvider(errors=[DailyQuotaError("a")]), EchoProvider()
    chain = make_chain(p1, p2)
    "".join(chain.run(REQ))
    assert chain.tracker.until[1] == datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)


def test_rate_limit_recovered_after_wait():
    p1 = EchoProvider(errors=[RateQuotaError("chậm", retry_after=5.0), None])
    sleeps: list[float] = []
    chain = make_chain(p1, EchoProvider(), sleeps=sleeps)
    events = []
    run = chain.run(REQ, on_event=events.append)
    assert "".join(run).startswith("[VI]")
    assert run.step == 1 and len(p1.calls) == 2
    assert sleeps == [5.0]
    assert [(e.kind, e.step, e.delay) for e in events] == [("waiting_for_quota", 1, 5.0)]


def test_rate_limit_exponential_backoff_and_max_three_retries():
    p1 = EchoProvider(errors=[RateQuotaError("x")] * 4)
    p2 = EchoProvider()
    sleeps: list[float] = []
    with pytest.raises(RateQuotaError):
        "".join(make_chain(p1, p2, sleeps=sleeps).run(REQ))
    assert len(p1.calls) == 4  # 1 lần đầu + 3 lần thử lại
    assert sleeps == [2.0, 4.0, 8.0]
    assert not p2.calls  # rate limit không chuyển bước


def test_midstream_error_does_not_switch_step():
    p1 = EchoProvider(midstream_error=ProviderError("đứt"))
    p2 = EchoProvider()
    chain = make_chain(p1, p2)
    got = []
    with pytest.raises(ProviderError):
        for t in chain.run(REQ):
            got.append(t)  # noqa: PERF402
    assert got == ["[VI] dòng 1\n"] and not p2.calls
    assert chain.tracker.success == {}


def test_truncated_at_end_not_counted():
    chain = make_chain(EchoProvider(end_error=TruncatedError("cắt")), EchoProvider())
    with pytest.raises(TruncatedError):
        "".join(chain.run(REQ))
    assert chain.tracker.success == {}


def test_background_uses_only_step1():
    p1 = EchoProvider(errors=[DailyQuotaError("hết", NOW + timedelta(hours=2))])
    p2 = EchoProvider()
    with pytest.raises(DailyQuotaError):
        "".join(make_chain(p1, p2).run(REQ, ChainPolicy.BACKGROUND))
    assert not p2.calls


def test_background_skips_when_step1_known_exhausted():
    tracker = FakeTracker()
    tracker.until[1] = NOW + timedelta(hours=2)
    p1, p2 = EchoProvider(), EchoProvider()
    with pytest.raises(DailyQuotaError):
        "".join(make_chain(p1, p2, tracker).run(REQ, ChainPolicy.BACKGROUND))
    assert not p1.calls and not p2.calls


def test_single_key_per_provider_in_config():
    # Spec "Single key per provider": cấu hình chỉ có MỘT trường key cho Gemini, không có
    # trường key theo bước.
    from novel_translator.config import Settings

    key_fields = [f for f in Settings.model_fields if "key" in f]
    assert key_fields == ["gemini_api_key"]
