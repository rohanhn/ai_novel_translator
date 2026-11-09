"""Chuỗi fallback provider/model (design D2). Application chỉ thấy một LLMProvider.

Quy tắc:
- Bước đang hết quota ngày (theo QuotaTracker) → bỏ qua, không gửi request.
- DailyQuotaError trước khi có text → ghi nhận hết quota, chuyển bước kế tiếp.
- RateQuotaError → chờ (exponential backoff, tôn trọng retry_after) và thử lại cùng bước,
  tối đa `max_retries` lần.
- Lỗi khác, hoặc lỗi khi stream đã phát text → dừng, không thử bước sau.
- BACKGROUND chỉ dùng bước 1 (quota dự phòng dành cho chương chủ sở hữu mở).
- Chỉ đếm lượt khi request hoàn tất thành công.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ..domain.models import ChainEvent, ChainPolicy, CompletionRequest, CompletionResult
from ..domain.ports import (
    DailyQuotaError,
    LLMProvider,
    QuotaTracker,
    RateQuotaError,
    StreamingProvider,
)
from .gemini import next_pacific_midnight

MAX_RATE_RETRIES = 3
BASE_BACKOFF_S = 2.0


@dataclass(frozen=True)
class ChainLink:
    provider: LLMProvider
    model: str


class ChainRun:
    """Một lần chạy chuỗi: iterable các mẩu text; sau mẩu đầu tiên biết bước/provider/model."""

    def __init__(self, chain: ChainProvider, request: CompletionRequest, policy: ChainPolicy,
                 on_event: Callable[[ChainEvent], None] | None):
        self.chain = chain
        self.request = request
        self.policy = policy
        self.on_event = on_event or (lambda e: None)
        self.step: int | None = None
        self.provider: str | None = None
        self.model: str | None = None

    def __iter__(self) -> Iterator[str]:
        return self._run()

    def _run(self) -> Iterator[str]:
        c = self.chain
        links = c.links[:1] if self.policy == ChainPolicy.BACKGROUND else c.links
        earliest: datetime | None = None

        def note_reset(until: datetime | None) -> None:
            nonlocal earliest
            if until and (earliest is None or until < earliest):
                earliest = until

        for step, link in enumerate(links, start=1):
            until = c.tracker.exhausted_until(step)
            if until is not None:
                note_reset(until)
                continue
            name = link.provider.name
            req = replace(self.request, model=link.model)
            retries = 0
            while True:
                try:
                    it = iter(link.provider.stream(req))
                    first = next(it, None)
                except DailyQuotaError as e:
                    reset = e.reset_at or next_pacific_midnight(c.clock())
                    c.tracker.mark_exhausted(step, reset)
                    note_reset(reset)
                    break  # sang bước kế tiếp
                except RateQuotaError as e:
                    retries += 1
                    if retries > c.max_retries:
                        raise
                    delay = max(e.retry_after or 0.0, c.base_backoff * 2 ** (retries - 1))
                    self.on_event(ChainEvent("waiting_for_quota", step, name, link.model, delay))
                    c.sleep(delay)
                    continue
                # Request đã được chấp nhận: từ đây mọi lỗi đều dừng chuỗi.
                self.step, self.provider, self.model = step, name, link.model
                if step > 1:
                    self.on_event(ChainEvent("fallback_step", step, name, link.model))
                if first is not None:
                    yield first
                    yield from it
                c.tracker.record_success(step)
                return

        raise DailyQuotaError(
            "Hết quota ngày ở mọi bước được phép của chuỗi provider.", reset_at=earliest
        )


class ChainProvider(StreamingProvider):
    name = "chain"

    def __init__(
        self,
        links: list[ChainLink],
        tracker: QuotaTracker,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        max_retries: int = MAX_RATE_RETRIES,
        base_backoff: float = BASE_BACKOFF_S,
    ):
        if not links:
            raise ValueError("Chuỗi provider rỗng.")
        self.links = links
        self.tracker = tracker
        self.sleep = sleep
        self.clock = clock
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.default_model = links[0].model

    def run(self, request: CompletionRequest, policy: ChainPolicy = ChainPolicy.FOREGROUND,
            on_event: Callable[[ChainEvent], None] | None = None) -> ChainRun:
        return ChainRun(self, request, policy, on_event)

    def stream(self, request: CompletionRequest) -> Iterator[str]:
        return iter(self.run(request))

    def complete(self, request: CompletionRequest) -> CompletionResult:
        run = self.run(request)
        text = "".join(run)
        return CompletionResult(text=text, provider=run.provider or self.name,
                                model=run.model or self.default_model)
