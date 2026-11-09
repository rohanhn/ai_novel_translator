"""Buffer N+1 (spec translation-prefetch): dịch trước chương kế tiếp khi chủ sở hữu thực sự
đang đọc chương N, chỉ dùng quota bước 1 của chuỗi (policy BACKGROUND)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.models import ChapterStatus
from ..domain.ports import NovelRepository, QuotaTracker
from .jobs import Lane, TranslationJobManager
from .services import NotFoundError

PREFETCH_PREF = "prefetch"


class ReadingSignal(str, Enum):
    VISIBLE_30S = "visible_30s"  # chương hiển thị ≥30 giây
    SCROLLED_60 = "scrolled_60"  # cuộn quá 60%
    EXPLICIT = "explicit"  # bấm "Chuẩn bị chương tiếp"


@dataclass(frozen=True)
class PrefetchDecision:
    started: bool
    reason: str  # started | no_next_chapter | already_translated | edited | in_progress
    #              | disabled | primary_exhausted
    chapter_index: int | None = None


class PrefetchService:
    def __init__(self, repo: NovelRepository, jobs: TranslationJobManager, quota: QuotaTracker):
        self.repo = repo
        self.jobs = jobs
        self.quota = quota

    def enabled(self) -> bool:
        return self.repo.get_preferences().get(PREFETCH_PREF, True) is not False

    def on_reading_signal(self, novel_id: int, index: int,
                          signal: ReadingSignal) -> PrefetchDecision:
        if not self.repo.get_novel(novel_id) or not self.repo.get_chapter(novel_id, index):
            raise NotFoundError(f"Không có chương {index} của truyện {novel_id}")
        target = index + 1

        def no(reason: str) -> PrefetchDecision:
            return PrefetchDecision(False, reason, target)

        if not self.enabled():
            return no("disabled")
        nxt = self.repo.get_chapter(novel_id, target)
        if nxt is None:
            return no("no_next_chapter")
        if nxt.status == ChapterStatus.EDITED:
            return no("edited")
        if nxt.status == ChapterStatus.TRANSLATED:
            return no("already_translated")
        if nxt.status == ChapterStatus.TRANSLATING or self.jobs.get(novel_id, target):
            return no("in_progress")
        if self.quota.exhausted_until(1) is not None:
            # Bước 1 hết quota ngày: tạm dừng buffer, quota dự phòng dành cho chương được mở.
            return no("primary_exhausted")
        # Độ sâu một chương: bỏ các prefetch còn chờ khác của truyện này (đã lỗi thời).
        self.jobs.cancel_queued_for_novel(novel_id, Lane.BACKGROUND)
        self.jobs.submit(novel_id, target, Lane.BACKGROUND)
        return PrefetchDecision(True, "started", target)

    def on_leave(self, novel_id: int) -> int:
        """Chủ sở hữu rời truyện: hủy prefetch chưa gửi request; cái đang chạy thì để chạy xong."""
        return self.jobs.cancel_queued_for_novel(novel_id, Lane.BACKGROUND)
