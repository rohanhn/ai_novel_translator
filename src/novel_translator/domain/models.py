"""Entity thuần của domain. Không import framework, DB hay SDK LLM ở đây."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    return datetime.now(timezone.utc)


IMPORT_PROVIDER = "import"  # nhãn nguồn của chương lấy từ bản dịch có sẵn


class ChapterStatus(str, Enum):
    PENDING = "pending"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    EDITED = "edited"  # đã biên tập tay; không bị thay đổi tự động
    FAILED = "failed"


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    DISMISSED = "dismissed"


@dataclass
class Novel:
    title: str
    source_lang: str = "zh"
    target_lang: str = "vi"
    id: int | None = None
    glossary_version: int = 0
    created_at: datetime = field(default_factory=_now)
    last_read_at: datetime | None = None
    author: str | None = None
    description: str | None = None  # giới thiệu ngắn, giữ xuống dòng
    cover_updated_at: datetime | None = None  # None = chưa có ảnh bìa (dùng bìa tự vẽ)

    @property
    def has_cover(self) -> bool:
        return self.cover_updated_at is not None

    @property
    def pretranslated(self) -> bool:
        """Truyện import từ bản đã dịch sẵn (vd. file tiếng Việt): không bao giờ gửi tới LLM."""
        return self.source_lang == self.target_lang


@dataclass
class Chapter:
    novel_id: int
    index: int
    title: str
    source_text: str
    translated_title: str | None = None
    translated_text: str | None = None
    status: ChapterStatus = ChapterStatus.PENDING
    provider: str | None = None
    model: str | None = None
    chain_step: int | None = None
    glossary_version: int | None = None  # phiên bản bộ tên dùng lúc dịch
    glossary_outdated: bool = False
    possible_omission: bool = False
    id: int | None = None
    updated_at: datetime = field(default_factory=_now)


@dataclass
class GlossaryEntry:
    """Một thuật ngữ cố định cho một truyện (tên nhân vật, địa danh, cảnh giới...)."""

    novel_id: int
    source_term: str
    target_term: str
    note: str | None = None
    id: int | None = None


@dataclass
class GlossarySuggestion:
    """Tên riêng do LLM đề xuất, chờ chủ sở hữu duyệt."""

    novel_id: int
    source_term: str
    target_term: str
    category: str | None = None
    status: SuggestionStatus = SuggestionStatus.PENDING
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class NovelSummary:
    """Một dòng trong thư viện."""

    novel: Novel
    chapter_count: int
    translated_count: int  # translated + edited
    last_read_chapter: int | None = None


@dataclass
class ReadingProgress:
    novel_id: int
    chapter_index: int
    position: float = 0.0  # 0–1, tỉ lệ cuộn trong chương
    updated_at: datetime = field(default_factory=_now)


class ChainPolicy(str, Enum):
    """FOREGROUND: chương chủ sở hữu mở, dùng mọi bước. BACKGROUND: prefetch, chỉ bước 1."""

    FOREGROUND = "foreground"
    BACKGROUND = "background"


@dataclass(frozen=True)
class ChainEvent:
    """Sự kiện tiến trình của chuỗi provider.

    kind: `waiting_for_quota` (đang chờ vì giới hạn tốc độ, `delay` giây) |
          `fallback_step` (đang dùng bước dự phòng `step` > 1).
    """

    kind: str
    step: int
    provider: str
    model: str
    delay: float | None = None


@dataclass(frozen=True)
class StepUsage:
    """Lượt dùng trong ngày của một bước trong chuỗi provider."""

    step: int  # 1-based
    requests: int
    exhausted_until: datetime | None = None  # chỉ có giá trị khi bước còn đang hết quota


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    user: str
    model: str | None = None
    max_output_tokens: int = 16000


@dataclass(frozen=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
