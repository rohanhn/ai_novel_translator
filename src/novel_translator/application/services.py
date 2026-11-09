"""Use case của ứng dụng. CLI và API chỉ gọi vào đây, không chạm trực tiếp storage/provider."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..domain.models import (
    ChainPolicy,
    Chapter,
    ChapterStatus,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    SuggestionStatus,
)
from ..domain.ports import (
    DailyQuotaError,
    Exporter,
    LLMProvider,
    NovelRepository,
    RateQuotaError,
    SourceLoader,
    TranslationError,
)
from ..domain.rename import replace_whole_word
from ..pipeline.sections import NameItem
from ..pipeline.translator import ChapterTranslator, TranslatorEvent


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
    """Bộ tên của truyện. Mọi thay đổi (thêm/sửa/xóa) đều tăng `glossary_version`."""

    def __init__(self, repo: NovelRepository):
        self.repo = repo

    def _require_novel(self, novel_id: int) -> Novel:
        novel = self.repo.get_novel(novel_id)
        if not novel:
            raise NotFoundError(f"Không có truyện id={novel_id}")
        return novel

    def set_term(self, novel_id: int, source: str, target: str, note: str | None = None
                 ) -> GlossaryEntry:
        """Thêm/sửa một tên. Đổi bản dịch của tên đã có → lan truyền sang các chương đã dịch
        (design D9). Toàn bộ chạy trong một transaction."""
        source, target = source.strip(), target.strip()
        if not source or not target:
            raise ValueError("Thuật ngữ nguồn và bản dịch không được để trống.")
        self._require_novel(novel_id)
        with self.repo.unit_of_work():
            current = self._get(novel_id, source)
            entry = self.repo.upsert_glossary(GlossaryEntry(novel_id, source, target, note))
            if current is None or (current.target_term, current.note) != (target, note):
                self.repo.bump_glossary_version(novel_id)
            if current is not None and current.target_term != target:
                self._propagate(novel_id, source, current.target_term, target)
        return entry

    def list_terms(self, novel_id: int) -> list[GlossaryEntry]:
        return self.repo.list_glossary(novel_id)

    def remove_term(self, novel_id: int, source: str) -> bool:
        """Xóa tên; chương bị ảnh hưởng chỉ được gắn nhãn (không thay chữ)."""
        with self.repo.unit_of_work():
            removed = self.repo.delete_glossary(novel_id, source)
            if removed:
                self.repo.bump_glossary_version(novel_id)
                self._propagate(novel_id, source, None, None)
        return removed

    def affected_chapters(self, novel_id: int, source: str) -> list[Chapter]:
        """Chương đã dịch/đã biên tập có raw chứa tên: bị ảnh hưởng nếu đổi/xóa tên này."""
        return [ch for ch in self.repo.chapters_with_source_term(novel_id, source)
                if ch.status in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED)]

    def _get(self, novel_id: int, source: str) -> GlossaryEntry | None:
        return {g.source_term: g for g in self.repo.list_glossary(novel_id)}.get(source)

    def _propagate(self, novel_id: int, source: str, old: str | None, new: str | None) -> None:
        for ch in self.affected_chapters(novel_id, source):
            if ch.status == ChapterStatus.TRANSLATED and old and new:
                ch.translated_text, _ = replace_whole_word(ch.translated_text or "", old, new)
                if ch.translated_title:
                    ch.translated_title, _ = replace_whole_word(ch.translated_title, old, new)
            # chương edited: chỉ gắn nhãn, không bao giờ tự sửa chữ
            ch.glossary_outdated = True
            self.repo.update_chapter(ch)

    # --- hàng chờ tên do LLM đề xuất ---
    def list_suggestions(self, novel_id: int) -> list[GlossarySuggestion]:
        self._require_novel(novel_id)
        return self.repo.list_suggestions(novel_id, SuggestionStatus.PENDING)

    def _pending(self, novel_id: int, source: str) -> GlossarySuggestion:
        s = self.repo.get_suggestion(novel_id, source)
        if not s or s.status != SuggestionStatus.PENDING:
            raise NotFoundError(f"Không có đề xuất '{source}' đang chờ duyệt")
        return s

    def accept_suggestion(self, novel_id: int, source: str, target: str | None = None
                          ) -> GlossaryEntry:
        """Đồng ý (có thể kèm sửa bản dịch): thêm vào bộ tên và bỏ khỏi hàng chờ."""
        s = self._pending(novel_id, source)
        entry = self.set_term(novel_id, s.source_term, (target or s.target_term),
                              note=s.category)
        self.repo.delete_suggestion(novel_id, s.source_term)
        return entry

    def dismiss_suggestion(self, novel_id: int, source: str) -> None:
        """Bỏ qua: giữ bản ghi `dismissed` để lần dịch sau không đề xuất lại."""
        self._pending(novel_id, source)
        self.repo.set_suggestion_status(novel_id, source, SuggestionStatus.DISMISSED)


class TranslationService:
    def __init__(
        self,
        repo: NovelRepository,
        provider_factory: Callable[[str | None, str | None], LLMProvider],
        chapter_char_limit: int,
        default_model: str | None = None,
    ):
        self.repo = repo
        self.provider_factory = provider_factory
        self.chapter_char_limit = chapter_char_limit
        self.default_model = default_model

    def translate_chapter(
        self,
        novel_id: int,
        index: int,
        provider: str | None = None,
        model: str | None = None,
        force: bool = False,
        policy: ChainPolicy = ChainPolicy.FOREGROUND,
        on_event: Callable[[TranslatorEvent], None] | None = None,
    ) -> Chapter:
        novel = self.repo.get_novel(novel_id)
        chapter = self.repo.get_chapter(novel_id, index)
        if not novel or not chapter:
            raise NotFoundError(f"Không có chương {index} của truyện {novel_id}")
        if chapter.status in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED) and not force:
            return chapter  # đã có bản dịch: không gọi LLM

        # NT_MODEL chỉ áp dụng khi không chỉ định provider; provider khác dùng model mặc định.
        model = model or (self.default_model if provider is None else None)
        translator = ChapterTranslator(
            self.provider_factory(provider, model), self.chapter_char_limit, model=model
        )
        glossary = self.repo.list_glossary(novel_id)
        previous = chapter.status
        chapter.status = ChapterStatus.TRANSLATING
        self.repo.update_chapter(chapter)
        try:
            out = translator.translate(
                novel, glossary, chapter.title, chapter.source_text,
                policy=policy, on_event=on_event,
            )
        except (DailyQuotaError, RateQuotaError):
            # Hết quota không phải lỗi của chương: giữ nguyên để dịch lại sau.
            keep = previous in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED)
            chapter.status = previous if keep else ChapterStatus.PENDING
            self.repo.update_chapter(chapter)
            raise
        except TranslationError:
            chapter.status = ChapterStatus.FAILED  # không lưu bản dịch dở dang
            self.repo.update_chapter(chapter)
            raise
        chapter.translated_title = out.title
        chapter.translated_text = out.text
        chapter.provider, chapter.model = out.provider, out.model
        chapter.chain_step = out.chain_step
        chapter.glossary_version = novel.glossary_version
        chapter.glossary_outdated = False
        chapter.possible_omission = out.possible_omission
        chapter.status = ChapterStatus.TRANSLATED
        self.repo.update_chapter(chapter)
        self._queue_suggestions(novel_id, glossary, out.names)
        return chapter

    def _queue_suggestions(self, novel_id: int, glossary: list[GlossaryEntry],
                           names: list[NameItem]) -> None:
        """Đưa tên mới vào hàng chờ duyệt; bỏ qua term đã có trong bộ tên. Term đã có trong
        hàng chờ (kể cả đã bị bỏ qua) không bị thêm lại (repository ON CONFLICT DO NOTHING)."""
        known = {g.source_term for g in glossary}
        for item in names:
            if item.source in known:
                continue
            self.repo.add_suggestion(
                GlossarySuggestion(novel_id, item.source, item.target, item.category)
            )

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
