"""Entity thuần của domain. Không import framework, DB hay SDK LLM ở đây."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


@dataclass
class ReadingProgress:
    novel_id: int
    chapter_index: int
    position: float = 0.0  # 0–1, tỉ lệ cuộn trong chương
    updated_at: datetime = field(default_factory=_now)


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
