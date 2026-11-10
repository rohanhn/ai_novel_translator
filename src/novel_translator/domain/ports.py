"""Port (interface) mà domain/application cần. Adapter ở các package khác hiện thực chúng."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import (
    ChainEvent,
    ChainPolicy,
    Chapter,
    CompletionRequest,
    CompletionResult,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    NovelSummary,
    ReadingProgress,
    StepUsage,
    SuggestionStatus,
)


class TranslationError(RuntimeError):
    """Lỗi khi gọi LLM. Provider luôn ném một trong các lớp con bên dưới (không phụ thuộc SDK)."""

    category = "provider_error"


class RefusalError(TranslationError):
    """Model từ chối dịch (safety/policy)."""

    category = "refusal"


class TruncatedError(TranslationError):
    """Output bị cắt (chạm giới hạn token)."""

    category = "truncated"


class RateQuotaError(TranslationError):
    """Hết quota theo phút: chờ `retry_after` giây (nếu provider gợi ý) rồi thử lại."""

    category = "rate_quota"

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class DailyQuotaError(TranslationError):
    """Hết quota theo ngày: chuyển bước trong chuỗi hoặc dừng tới `reset_at`."""

    category = "daily_quota"

    def __init__(self, message: str, reset_at: datetime | None = None):
        super().__init__(message)
        self.reset_at = reset_at


class MalformedOutputError(TranslationError):
    """Output của model không đúng định dạng yêu cầu (vd. thiếu phần BODY) hoặc rỗng."""

    category = "malformed"


class ProviderError(TranslationError):
    """Lỗi API/mạng/cấu hình khác của provider."""

    category = "provider_error"


class ProviderConfigError(ProviderError):
    """Thiếu/sai cấu hình provider (vd. chưa đặt API key). Thông điệp nêu tên biến, không lộ giá trị."""

    category = "config"


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    default_model: str

    def stream(self, request: CompletionRequest, policy: ChainPolicy = ChainPolicy.FOREGROUND,
               on_event: Callable[[ChainEvent], None] | None = None) -> Iterable[str]:
        """Trả về các mẩu text thô theo thứ tự. Lỗi → lớp con của TranslationError; lỗi
        truncated/refusal phát hiện ở cuối luồng được ném sau mẩu text cuối.

        `policy`/`on_event` chỉ có ý nghĩa với provider ghép (chuỗi fallback); provider đơn
        bỏ qua. Kết quả có thể có thuộc tính `provider`/`model`/`step` cho biết thực tế đã
        dùng gì (đọc được sau khi lặp xong)."""
        ...

    def complete(self, request: CompletionRequest) -> CompletionResult: ...


class StreamingProvider:
    """Lớp nền tiện dụng: `complete()` mặc định ghép kết quả của `stream()`."""

    name: str
    default_model: str

    def stream(self, request: CompletionRequest, policy: ChainPolicy = ChainPolicy.FOREGROUND,
               on_event: Callable[[ChainEvent], None] | None = None
               ) -> Iterable[str]:  # pragma: no cover
        raise NotImplementedError

    def complete(self, request: CompletionRequest) -> CompletionResult:
        text = "".join(self.stream(request))
        return CompletionResult(
            text=text, provider=self.name, model=request.model or self.default_model
        )


class NovelRepository(Protocol):
    def unit_of_work(self) -> AbstractContextManager[None]:
        """Các thao tác trong khối chạy trong một transaction."""
        ...

    def add_novel(self, novel: Novel) -> Novel: ...
    def get_novel(self, novel_id: int) -> Novel | None: ...
    def list_novels(self) -> list[Novel]: ...
    def delete_novel(self, novel_id: int) -> bool: ...
    def library_overview(self) -> list[NovelSummary]: ...
    def touch_novel_read(self, novel_id: int) -> None: ...
    def bump_glossary_version(self, novel_id: int) -> int: ...

    def add_chapters(self, chapters: list[Chapter]) -> list[Chapter]: ...
    def get_chapter(self, novel_id: int, index: int) -> Chapter | None: ...
    def list_chapters(self, novel_id: int) -> list[Chapter]: ...
    def update_chapter(self, chapter: Chapter) -> None: ...
    def chapters_with_source_term(self, novel_id: int, term: str) -> list[Chapter]: ...
    def reset_translating(self) -> int: ...

    def upsert_glossary(self, entry: GlossaryEntry) -> GlossaryEntry: ...
    def list_glossary(self, novel_id: int) -> list[GlossaryEntry]: ...
    def delete_glossary(self, novel_id: int, source_term: str) -> bool: ...

    def add_suggestion(self, suggestion: GlossarySuggestion) -> bool: ...
    def list_suggestions(
        self, novel_id: int, status: SuggestionStatus | None = None
    ) -> list[GlossarySuggestion]: ...
    def get_suggestion(self, novel_id: int, source_term: str) -> GlossarySuggestion | None: ...
    def set_suggestion_status(
        self, novel_id: int, source_term: str, status: SuggestionStatus
    ) -> bool: ...
    def delete_suggestion(self, novel_id: int, source_term: str) -> bool: ...

    def get_progress(self, novel_id: int) -> ReadingProgress | None: ...
    def save_progress(self, progress: ReadingProgress) -> None: ...

    def get_preferences(self) -> dict[str, object]: ...
    def set_preference(self, key: str, value: object) -> None: ...


@runtime_checkable
class QuotaTracker(Protocol):
    """Đếm lượt dùng thành công theo ngày cho từng bước của chuỗi và ghi nhớ bước nào đã hết
    quota ngày (tới thời điểm reset). Bước đánh số từ 1."""

    def exhausted_until(self, step: int) -> datetime | None:
        """Thời điểm reset nếu bước đang hết quota; None nếu dùng được."""
        ...

    def record_success(self, step: int) -> None: ...
    def mark_exhausted(self, step: int, until: datetime) -> None: ...
    def usage_today(self) -> list[StepUsage]: ...


class SessionStore(Protocol):
    """Lưu session đăng nhập theo hash của token (không bao giờ lưu token gốc)."""

    def create_session(self, token_hash: str, now: datetime) -> None: ...

    def touch_session(self, token_hash: str, now: datetime, idle_after: datetime) -> bool:
        """Session tồn tại và last_seen_at > idle_after → cập nhật last_seen_at, trả True.
        Session quá hạn bị xóa và trả False."""
        ...

    def delete_session(self, token_hash: str) -> None: ...


class SourceLoader(Protocol):
    """Đọc và giải mã file nguồn thành văn bản. Tách chương: `domain/chapter_split.py`."""

    def read_text(self, path: Path) -> str: ...

    def decode(self, data: bytes) -> str: ...


class Exporter(Protocol):
    format: str

    def export(self, novel: Novel, chapters: list[Chapter], dest: Path) -> Path: ...
