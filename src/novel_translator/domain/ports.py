"""Port (interface) mà domain/application cần. Adapter ở các package khác hiện thực chúng."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Chapter, CompletionRequest, CompletionResult, GlossaryEntry, Novel


class TranslationError(RuntimeError):
    """Lỗi khi gọi LLM (refusal, hết quota, mất kết nối...)."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    default_model: str

    def complete(self, request: CompletionRequest) -> CompletionResult: ...


class NovelRepository(Protocol):
    def add_novel(self, novel: Novel) -> Novel: ...
    def get_novel(self, novel_id: int) -> Novel | None: ...
    def list_novels(self) -> list[Novel]: ...

    def add_chapters(self, chapters: list[Chapter]) -> list[Chapter]: ...
    def get_chapter(self, novel_id: int, index: int) -> Chapter | None: ...
    def list_chapters(self, novel_id: int) -> list[Chapter]: ...
    def update_chapter(self, chapter: Chapter) -> None: ...

    def upsert_glossary(self, entry: GlossaryEntry) -> GlossaryEntry: ...
    def list_glossary(self, novel_id: int) -> list[GlossaryEntry]: ...
    def delete_glossary(self, novel_id: int, source_term: str) -> bool: ...


class RawChapter(Protocol):
    title: str
    text: str


class SourceLoader(Protocol):
    """Đọc file nguồn và tách thành danh sách chương."""

    def load(self, path: Path) -> list[RawChapter]: ...


class Exporter(Protocol):
    format: str

    def export(self, novel: Novel, chapters: list[Chapter], dest: Path) -> Path: ...
