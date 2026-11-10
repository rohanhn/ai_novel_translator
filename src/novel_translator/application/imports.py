"""Bản xem trước khi import TXT (design D2): giữ trong bộ nhớ, có hạn dùng.

Upload trên web không lưu ngay: file được giải mã và tách chương thành một draft; người dùng
chỉnh ranh giới rồi xác nhận mới tạo truyện. Draft mất khi server restart (một process).
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import PurePath

from ..domain import chapter_split
from ..domain.ports import SourceLoader
from .services import ImportResult, LibraryService

DRAFT_TTL = timedelta(minutes=60)
MAX_DRAFTS = 3
MAX_LINES_PER_REQUEST = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DraftExpiredError(LookupError):
    """Draft không tồn tại, đã hết hạn, đã được lưu, hoặc server đã restart."""


@dataclass
class Draft:
    id: str
    filename: str
    text: str
    lines: list[str]
    detected_lang: str
    plan: chapter_split.SplitPlan
    keep_front_matter: bool | None = None  # None: lựa chọn mặc định
    last_used: datetime = field(default_factory=_utcnow)

    @property
    def default_title(self) -> str:
        return PurePath(self.filename).stem or "Truyện mới"


class ImportDraftService:
    def __init__(self, library: LibraryService, loader: SourceLoader,
                 clock: Callable[[], datetime] = _utcnow, ttl: timedelta = DRAFT_TTL,
                 max_drafts: int = MAX_DRAFTS):
        self.library = library
        self.loader = loader
        self.clock = clock
        self.ttl = ttl
        self.max_drafts = max_drafts
        self._drafts: dict[str, Draft] = {}
        self._lock = threading.Lock()

    # --- nội bộ ---
    def _purge(self, now: datetime) -> None:
        for key in [k for k, d in self._drafts.items() if now - d.last_used > self.ttl]:
            del self._drafts[key]

    def _take(self, draft_id: str) -> Draft:
        now = self.clock()
        self._purge(now)
        d = self._drafts.get(draft_id)
        if d is None:
            raise DraftExpiredError("Bản xem trước đã hết hạn hoặc không còn, hãy upload lại file.")
        d.last_used = now
        return d

    # --- thao tác ---
    def create(self, filename: str, data: bytes) -> Draft:
        text = self.loader.decode(data)
        if not text.strip():
            raise ValueError("File rỗng.")
        lines = chapter_split.split_lines(text)
        plan = chapter_split.plan(text)
        draft = Draft(secrets.token_urlsafe(16), filename, text, lines,
                      chapter_split.detect_language(text), plan, last_used=self.clock())
        with self._lock:
            self._purge(draft.last_used)
            while len(self._drafts) >= self.max_drafts:
                oldest = min(self._drafts.values(), key=lambda d: d.last_used)
                del self._drafts[oldest.id]
            self._drafts[draft.id] = draft
        return draft

    def get(self, draft_id: str) -> Draft:
        with self._lock:
            return self._take(draft_id)

    def adjust(self, draft_id: str, boundaries: list[int],
               keep_front_matter: bool | None = None) -> Draft:
        """Áp tập ranh giới mới (số dòng) và lựa chọn phần mở đầu; tính lại chương + cảnh báo."""
        with self._lock:
            d = self._take(draft_id)
            d.plan = chapter_split.apply(d.text, boundaries, keep_front_matter)
            d.keep_front_matter = keep_front_matter
            return d

    def lines(self, draft_id: str, start: int, count: int) -> list[str]:
        """Một cửa sổ dòng của file (để chọn điểm tách); tối đa 500 dòng mỗi lần."""
        if start < 0 or count < 1:
            raise ValueError("start phải ≥ 0 và count phải ≥ 1.")
        with self._lock:
            d = self._take(draft_id)
            return d.lines[start:start + min(count, MAX_LINES_PER_REQUEST)]

    def commit(self, draft_id: str, title: str | None, lang: str | None,
               boundaries: list[int], keep_front_matter: bool | None = None) -> ImportResult:
        """Tạo truyện từ ranh giới gửi kèm (không phụ thuộc thứ tự các lần chỉnh trước đó),
        rồi xóa draft. Lỗi khi lưu thì giữ draft để người dùng thử lại."""
        with self._lock:
            d = self._take(draft_id)
        plan = chapter_split.apply(d.text, boundaries, keep_front_matter)
        result = self.library.import_text(d.text, (title or "").strip() or d.default_title,
                                          lang, plan)
        with self._lock:
            self._drafts.pop(draft_id, None)
        return result

    def discard(self, draft_id: str) -> None:
        with self._lock:
            self._drafts.pop(draft_id, None)
