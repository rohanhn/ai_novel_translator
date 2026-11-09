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
    FAILED = "failed"


@dataclass
class Novel:
    title: str
    source_lang: str = "zh"
    target_lang: str = "vi"
    id: int | None = None
    created_at: datetime = field(default_factory=_now)


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
