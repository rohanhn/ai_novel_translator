"""Schema JSON của API. Chỉ chuyển đổi domain ↔ JSON, không chứa logic."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ...domain.models import (
    Chapter,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    NovelSummary,
    ReadingProgress,
)


class NovelOut(BaseModel):
    id: int
    title: str
    source_lang: str
    target_lang: str
    glossary_version: int
    created_at: datetime
    last_read_at: datetime | None

    @classmethod
    def of(cls, n: Novel) -> NovelOut:
        return cls(id=n.id, title=n.title, source_lang=n.source_lang, target_lang=n.target_lang,
                   glossary_version=n.glossary_version, created_at=n.created_at,
                   last_read_at=n.last_read_at)


class LibraryItem(NovelOut):
    chapter_count: int
    translated_count: int
    last_read_chapter: int | None

    @classmethod
    def of_summary(cls, s: NovelSummary) -> LibraryItem:
        return cls(**NovelOut.of(s.novel).model_dump(), chapter_count=s.chapter_count,
                   translated_count=s.translated_count, last_read_chapter=s.last_read_chapter)


class ChapterSummary(BaseModel):
    index: int
    title: str
    translated_title: str | None
    status: str
    glossary_outdated: bool
    possible_omission: bool

    @classmethod
    def of(cls, c: Chapter) -> ChapterSummary:
        return cls(index=c.index, title=c.title, translated_title=c.translated_title,
                   status=c.status.value, glossary_outdated=c.glossary_outdated,
                   possible_omission=c.possible_omission)


class ChapterOut(ChapterSummary):
    source_text: str
    translated_text: str | None
    provider: str | None
    model: str | None
    chain_step: int | None
    glossary_version: int | None

    @classmethod
    def of(cls, c: Chapter) -> ChapterOut:
        return cls(**ChapterSummary.of(c).model_dump(), source_text=c.source_text,
                   translated_text=c.translated_text, provider=c.provider, model=c.model,
                   chain_step=c.chain_step, glossary_version=c.glossary_version)


class ChapterEditIn(BaseModel):
    translated_title: str | None = None
    translated_text: str


class TranslateIn(BaseModel):
    force: bool = False
    confirm_discard_edits: bool = False
    provider: str | None = None  # chỉ định → bỏ qua chuỗi provider
    model: str | None = None


class TranslateAccepted(BaseModel):
    state: str  # queued | running
    lane: str
    stream_url: str


class GlossaryIn(BaseModel):
    source_term: str = Field(min_length=1)
    target_term: str = Field(min_length=1)
    note: str | None = None


class GlossaryOut(GlossaryIn):
    @classmethod
    def of(cls, g: GlossaryEntry) -> GlossaryOut:
        return cls(source_term=g.source_term, target_term=g.target_term, note=g.note)


class SuggestionOut(BaseModel):
    source_term: str
    target_term: str
    category: str | None
    created_at: datetime

    @classmethod
    def of(cls, s: GlossarySuggestion) -> SuggestionOut:
        return cls(source_term=s.source_term, target_term=s.target_term, category=s.category,
                   created_at=s.created_at)


class AcceptSuggestionIn(BaseModel):
    target_term: str | None = None  # sửa bản dịch trước khi đồng ý


class ProgressIn(BaseModel):
    chapter_index: int
    position: float = 0.0


class ProgressOut(ProgressIn):
    updated_at: datetime

    @classmethod
    def of(cls, p: ReadingProgress) -> ProgressOut:
        return cls(chapter_index=p.chapter_index, position=p.position, updated_at=p.updated_at)
