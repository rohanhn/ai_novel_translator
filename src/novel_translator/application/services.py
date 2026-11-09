"""Use case của ứng dụng. CLI và API chỉ gọi vào đây, không chạm trực tiếp storage/provider."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain.models import Chapter, ChapterStatus, GlossaryEntry, Novel
from ..domain.ports import Exporter, LLMProvider, NovelRepository, SourceLoader, TranslationError
from ..pipeline.translator import ChapterTranslator


class NotFoundError(LookupError):
    pass


class LibraryService:
    def __init__(self, repo: NovelRepository, loader: SourceLoader):
        self.repo = repo
        self.loader = loader

    def import_novel(self, path: Path, title: str | None = None) -> tuple[Novel, int]:
        raw = self.loader.load(path)
        if not raw:
            raise ValueError(f"Không tìm thấy nội dung trong {path}")
        novel = self.repo.add_novel(Novel(title=title or path.stem))
        chapters = [
            Chapter(novel_id=novel.id, index=i + 1, title=r.title, source_text=r.text)
            for i, r in enumerate(raw)
        ]
        self.repo.add_chapters(chapters)
        return novel, len(chapters)

    def get_novel(self, novel_id: int) -> Novel:
        novel = self.repo.get_novel(novel_id)
        if not novel:
            raise NotFoundError(f"Không có truyện id={novel_id}")
        return novel

    def list_novels(self) -> list[Novel]:
        return self.repo.list_novels()

    def list_chapters(self, novel_id: int) -> list[Chapter]:
        self.get_novel(novel_id)
        return self.repo.list_chapters(novel_id)

    def get_chapter(self, novel_id: int, index: int) -> Chapter:
        ch = self.repo.get_chapter(novel_id, index)
        if not ch:
            raise NotFoundError(f"Không có chương {index} của truyện {novel_id}")
        return ch


class GlossaryService:
    def __init__(self, repo: NovelRepository):
        self.repo = repo

    def set_term(self, novel_id: int, source: str, target: str, note: str | None = None):
        return self.repo.upsert_glossary(GlossaryEntry(novel_id, source, target, note))

    def list_terms(self, novel_id: int) -> list[GlossaryEntry]:
        return self.repo.list_glossary(novel_id)

    def remove_term(self, novel_id: int, source: str) -> bool:
        return self.repo.delete_glossary(novel_id, source)


class TranslationService:
    def __init__(
        self,
        repo: NovelRepository,
        provider_factory: Callable[[str | None], LLMProvider],
        max_segment_chars: int,
        default_model: str | None = None,
    ):
        self.repo = repo
        self.provider_factory = provider_factory
        self.max_segment_chars = max_segment_chars
        self.default_model = default_model

    def translate_chapter(
        self,
        novel_id: int,
        index: int,
        provider: str | None = None,
        model: str | None = None,
        force: bool = False,
    ) -> Chapter:
        novel = self.repo.get_novel(novel_id)
        chapter = self.repo.get_chapter(novel_id, index)
        if not novel or not chapter:
            raise NotFoundError(f"Không có chương {index} của truyện {novel_id}")
        if chapter.status == ChapterStatus.TRANSLATED and not force:
            return chapter

        translator = ChapterTranslator(
            self.provider_factory(provider),
            self.max_segment_chars,
            # NT_MODEL chỉ áp dụng cho provider mặc định; provider khác dùng model mặc định của nó.
            model=model or (self.default_model if provider is None else None),
        )
        chapter.status = ChapterStatus.TRANSLATING
        self.repo.update_chapter(chapter)
        try:
            out = translator.translate(
                novel, self.repo.list_glossary(novel_id), chapter.title, chapter.source_text
            )
        except TranslationError:
            chapter.status = ChapterStatus.FAILED
            self.repo.update_chapter(chapter)
            raise
        chapter.translated_title = out.title
        chapter.translated_text = out.text
        chapter.provider, chapter.model = out.provider, out.model
        chapter.status = ChapterStatus.TRANSLATED
        self.repo.update_chapter(chapter)
        return chapter

    def translate_range(
        self, novel_id: int, start: int, end: int, **kwargs
    ) -> list[Chapter]:
        return [self.translate_chapter(novel_id, i, **kwargs) for i in range(start, end + 1)]


class ExportService:
    def __init__(self, repo: NovelRepository, exporters: dict[str, Exporter]):
        self.repo = repo
        self.exporters = exporters

    def export(self, novel_id: int, dest: Path, fmt: str = "txt") -> Path:
        novel = self.repo.get_novel(novel_id)
        if not novel:
            raise NotFoundError(f"Không có truyện id={novel_id}")
        if fmt not in self.exporters:
            raise ValueError(f"Định dạng '{fmt}' chưa hỗ trợ. Có: {', '.join(self.exporters)}")
        return self.exporters[fmt].export(novel, self.repo.list_chapters(novel_id), dest)
