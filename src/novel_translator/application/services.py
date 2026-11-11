"""Use case của ứng dụng. CLI và API chỉ gọi vào đây, không chạm trực tiếp storage/provider."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..domain import chapter_split
from ..domain.models import (
    IMPORT_PROVIDER,
    ChainPolicy,
    Chapter,
    ChapterStatus,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    NovelSummary,
    ReadingProgress,
    SuggestionStatus,
)
from ..domain.novel_details import UNSET, CoverImage, Unset, normalize_details
from ..domain.ports import (
    CoverImageFetcher,
    CoverImageProcessor,
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


class InvalidOperationError(ValueError):
    """Thao tác không hợp lệ với trạng thái hiện tại (vd. sửa chương chưa dịch)."""


class PreTranslatedError(InvalidOperationError):
    """Chương của truyện bản dịch có sẵn: không bao giờ gửi tới LLM (spec novel-library)."""


class ConfirmationRequiredError(InvalidOperationError):
    """Thao tác làm mất dữ liệu (dịch lại chương đã biên tập) cần chủ sở hữu xác nhận."""


class NovelBusyError(InvalidOperationError):
    """Truyện đang được cập nhật chương, hoặc còn job dịch khi muốn tải lại cả bộ."""


SUPPORTED_IMPORT_LANGS = ("zh", "vi")


@dataclass
class ImportResult:
    novel: Novel
    plan: chapter_split.SplitPlan
    lang: str  # ngôn ngữ đã dùng để lưu
    detected_lang: str  # zh | vi | unknown

    @property
    def chapters(self) -> int:
        return len(self.plan.chapters)


def new_chapter(novel: Novel, index: int, title: str, body: str) -> Chapter:
    """Chương mới lấy từ file: `pending`, hoặc với truyện bản dịch có sẵn (`vi`) thì lưu luôn ở
    trạng thái Đã dịch, không bao giờ qua LLM. Dùng chung cho import và cập nhật chương."""
    ch = Chapter(novel_id=novel.id, index=index, title=title, source_text=body)
    if novel.pretranslated:
        ch.translated_title, ch.translated_text = title, body
        ch.status = ChapterStatus.TRANSLATED
        ch.provider = IMPORT_PROVIDER
        ch.glossary_version = novel.glossary_version
    return ch


class LibraryService:
    def __init__(self, repo: NovelRepository, loader: SourceLoader,
                 on_delete: Callable[[int], object] | None = None,
                 covers: CoverImageProcessor | None = None,
                 cover_fetcher: CoverImageFetcher | None = None):
        self.repo = repo
        self.loader = loader
        self.on_delete = on_delete  # vd. hủy prefetch đang chờ của truyện
        self.covers = covers  # kiểm tra + chuẩn hoá ảnh bìa (adapter nối trong container)
        self.cover_fetcher = cover_fetcher  # tải ảnh từ link, chặn địa chỉ nội bộ

    def overview(self) -> list[NovelSummary]:
        return self.repo.library_overview()

    def delete_novel(self, novel_id: int, confirm: bool = False) -> None:
        """Xóa vĩnh viễn truyện + raw, bản dịch, bộ tên, đề xuất, tiến độ. Cần xác nhận."""
        self.get_novel(novel_id)
        if not confirm:
            raise ConfirmationRequiredError(
                "Xóa truyện sẽ xóa vĩnh viễn mọi dữ liệu liên quan. Cần xác nhận để tiếp tục."
            )
        if self.on_delete is not None:
            self.on_delete(novel_id)
        self.repo.delete_novel(novel_id)

    def import_novel(
        self, path: Path, title: str | None = None, lang: str | None = None
    ) -> ImportResult:
        """Đọc file, tách theo kết quả mặc định của `chapter_split.plan` rồi lưu ngay."""
        return self.import_text(self.loader.read_text(path), title or path.stem, lang)

    def import_bytes(self, data: bytes, title: str, lang: str | None = None) -> ImportResult:
        """Như `import_novel` nhưng từ nội dung file đã nhận (upload web, lưu ngay)."""
        return self.import_text(self.loader.decode(data), title, lang)

    def import_text(
        self, text: str, title: str, lang: str | None = None,
        plan: chapter_split.SplitPlan | None = None,
    ) -> ImportResult:
        """Tạo truyện từ văn bản đã giải mã. `lang` None → ngôn ngữ nhận diện được (`unknown`
        → `zh`). Truyện `vi` là bản dịch có sẵn: chương lưu ở trạng thái Đã dịch, không qua
        LLM. `plan` None → cách tách mặc định."""
        detected = chapter_split.detect_language(text)
        lang = lang or (detected if detected in SUPPORTED_IMPORT_LANGS else "zh")
        if lang not in SUPPORTED_IMPORT_LANGS:
            raise InvalidOperationError(f"Ngôn ngữ không hỗ trợ: {lang} (chỉ zh hoặc vi).")
        plan = plan or chapter_split.plan(text)
        if not plan.chapters:
            raise ValueError("Không tìm thấy nội dung trong file.")
        novel = self.repo.add_novel(Novel(title=title, source_lang=lang, target_lang="vi"))
        self.repo.add_chapters([new_chapter(novel, i + 1, r.title, r.body)
                                for i, r in enumerate(plan.chapters)])
        return ImportResult(novel, plan, lang, detected)

    def get_novel(self, novel_id: int) -> Novel:
        novel = self.repo.get_novel(novel_id)
        if not novel:
            raise NotFoundError(f"Không có truyện id={novel_id}")
        return novel

    def list_novels(self) -> list[Novel]:
        return self.repo.list_novels()

    # --- thông tin truyện + ảnh bìa (spec novel-library "Edit novel details") ---
    def update_details(
        self, novel_id: int, *,
        title: str | None | Unset = UNSET,
        author: str | None | Unset = UNSET,
        description: str | None | Unset = UNSET,
    ) -> Novel:
        """Đổi các trường được truyền (bỏ qua `UNSET`); rỗng/`None` ở tác giả, giới thiệu = xoá.
        Không đụng chương, bản dịch, bộ tên, tiến độ; không gọi LLM."""
        fields = normalize_details(title=title, author=author, description=description)
        if not fields:
            raise ValueError("Cần ít nhất một trường để cập nhật (tên, tác giả hoặc giới thiệu).")
        self.get_novel(novel_id)
        novel = self.repo.update_novel_details(novel_id, fields)
        if novel is None:
            raise NotFoundError(f"Không có truyện id={novel_id}")
        return novel

    def _processor(self) -> CoverImageProcessor:
        if self.covers is None:
            raise RuntimeError("Chưa cấu hình bộ xử lý ảnh bìa.")
        return self.covers

    def process_cover(self, data: bytes) -> CoverImage:
        """Kiểm tra + chuẩn hoá ảnh, không lưu (dùng cho xem trước). Lỗi → `InvalidImageError`."""
        return self._processor().process(data)

    def preview_cover_from_url(self, url: str) -> CoverImage:
        """Tải ảnh từ link rồi xử lý như ảnh upload; KHÔNG lưu gì (chỉ để xem trước).
        Lỗi tải → `CoverFetchError`; không phải ảnh → `InvalidImageError`."""
        if self.cover_fetcher is None:
            raise RuntimeError("Chưa cấu hình bộ tải ảnh từ link.")
        return self.process_cover(self.cover_fetcher.fetch(url))

    def set_cover(self, novel_id: int, data: bytes) -> Novel:
        """Thay ảnh bìa. Ảnh không hợp lệ → `InvalidImageError`, ảnh cũ giữ nguyên."""
        self.get_novel(novel_id)
        image = self.process_cover(data)
        novel = self.repo.set_cover(novel_id, image)
        if novel is None:
            raise NotFoundError(f"Không có truyện id={novel_id}")
        return novel

    def remove_cover(self, novel_id: int) -> Novel:
        """Gỡ ảnh bìa (idempotent): truyện quay về bìa tự vẽ."""
        self.get_novel(novel_id)
        self.repo.delete_cover(novel_id)
        return self.get_novel(novel_id)

    def get_cover(self, novel_id: int) -> CoverImage:
        self.get_novel(novel_id)
        image = self.repo.get_cover(novel_id)
        if image is None:
            raise NotFoundError("Truyện này chưa có ảnh bìa.")
        return image

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
        confirm_discard_edits: bool = False,
    ) -> Chapter:
        novel = self.repo.get_novel(novel_id)
        chapter = self.check_translatable(novel_id, index, force, confirm_discard_edits)
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

    def preflight(self, novel_id: int, index: int, provider: str | None = None,
                  model: str | None = None, force: bool = False,
                  confirm_discard_edits: bool = False,
                  policy: ChainPolicy = ChainPolicy.FOREGROUND) -> Chapter:
        """Kiểm tra những gì biết được ngay, trước khi tạo job (design D5):
        - chương không tồn tại → NotFoundError; dịch lại chương đã biên tập chưa xác nhận →
          ConfirmationRequiredError;
        - provider không tồn tại → ValueError; cấu hình sai/thiếu key → ProviderConfigError;
        - mọi bước được phép của chuỗi đang hết quota ngày → DailyQuotaError kèm reset_at.
        Lỗi phát sinh sau đó (trong lúc dịch) đi qua sự kiện của job."""
        chapter = self.check_translatable(novel_id, index, force, confirm_discard_edits)
        if chapter.status in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED) and not force:
            return chapter
        model = model or (self.default_model if provider is None else None)
        llm = self.provider_factory(provider, model)
        check = getattr(llm, "all_exhausted_until", None)
        if check is not None and (reset := check(policy)) is not None:
            raise DailyQuotaError(
                "Hết quota ngày ở mọi bước được phép của chuỗi provider.", reset_at=reset
            )
        return chapter

    def check_translatable(self, novel_id: int, index: int, force: bool = False,
                           confirm_discard_edits: bool = False) -> Chapter:
        """Kiểm tra trước khi tạo job: chương tồn tại; truyện bản dịch có sẵn không bao giờ
        được dịch; dịch lại chương đã biên tập phải có xác nhận (bản sửa tay sẽ mất)."""
        chapter = self.repo.get_chapter(novel_id, index)
        novel = self.repo.get_novel(novel_id)
        if not novel or not chapter:
            raise NotFoundError(f"Không có chương {index} của truyện {novel_id}")
        if novel.pretranslated:
            raise PreTranslatedError(
                "Truyện này là bản dịch có sẵn (import từ file tiếng Việt), không dịch bằng model."
            )
        if chapter.status == ChapterStatus.EDITED and force and not confirm_discard_edits:
            raise ConfirmationRequiredError(
                f"Chương {index} đã được biên tập tay; dịch lại sẽ mất bản sửa. "
                "Cần xác nhận để tiếp tục."
            )
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


THEMES = ("light", "sepia", "dark", "bamboo")  # Tuyên chỉ, Hoàng quyển, Dạ nguyệt, Trúc lâm
DEFAULT_PREFERENCES: dict[str, object] = {
    "theme": "light", "font_size": 18, "line_height": 1.8, "prefetch": True,
}


class ReaderService:
    """Tiến độ đọc theo truyện + tùy chọn đọc (lưu server-side, dùng chung mọi thiết bị)."""

    def __init__(self, repo: NovelRepository):
        self.repo = repo

    def save_progress(self, novel_id: int, chapter_index: int, position: float
                      ) -> ReadingProgress:
        if not self.repo.get_chapter(novel_id, chapter_index):
            raise NotFoundError(f"Không có chương {chapter_index} của truyện {novel_id}")
        if not 0.0 <= position <= 1.0:
            raise ValueError("position phải nằm trong khoảng 0–1.")
        progress = ReadingProgress(novel_id, chapter_index, position)
        with self.repo.unit_of_work():
            self.repo.save_progress(progress)
            self.repo.touch_novel_read(novel_id)
        return progress

    def get_progress(self, novel_id: int) -> ReadingProgress | None:
        if not self.repo.get_novel(novel_id):
            raise NotFoundError(f"Không có truyện id={novel_id}")
        return self.repo.get_progress(novel_id)

    def get_preferences(self) -> dict[str, object]:
        stored = self.repo.get_preferences()
        return {k: stored.get(k, v) for k, v in DEFAULT_PREFERENCES.items()}

    def set_preferences(self, changes: dict[str, object]) -> dict[str, object]:
        clean = {k: _validate_pref(k, v) for k, v in changes.items()}
        with self.repo.unit_of_work():
            for k, v in clean.items():
                self.repo.set_preference(k, v)
        return self.get_preferences()


def _validate_pref(key: str, value: object) -> object:
    if key == "theme":
        if value not in THEMES:
            raise ValueError(f"theme phải là một trong: {', '.join(THEMES)}")
        return value
    if key == "font_size":
        if isinstance(value, bool) or not isinstance(value, int) or not 12 <= value <= 32:
            raise ValueError("font_size phải là số nguyên 12–32.")
        return value
    if key == "line_height":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not (
                1.2 <= value <= 2.4):
            raise ValueError("line_height phải trong khoảng 1.2–2.4.")
        return float(value)
    if key == "prefetch":
        if not isinstance(value, bool):
            raise ValueError("prefetch phải là true/false.")
        return value
    raise ValueError(f"Tùy chọn không hỗ trợ: {key}")


class EditingService:
    """Sửa tay bản dịch. Chương đã sửa có trạng thái `edited` và không bị thay đổi tự động."""

    def __init__(self, repo: NovelRepository):
        self.repo = repo

    def edit_chapter(self, novel_id: int, index: int, translated_title: str | None,
                     translated_text: str) -> Chapter:
        chapter = self.repo.get_chapter(novel_id, index)
        if not chapter:
            raise NotFoundError(f"Không có chương {index} của truyện {novel_id}")
        if (chapter.status not in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED)
                or chapter.translated_text is None):
            raise InvalidOperationError(f"Chương {index} chưa có bản dịch để biên tập.")
        text = "\n".join(line.rstrip() for line in translated_text.strip().splitlines())
        if not text:
            raise InvalidOperationError("Nội dung bản dịch không được để trống.")
        title = translated_title.strip() if translated_title else None
        chapter.translated_title = title or chapter.translated_title
        chapter.translated_text = text
        chapter.status = ChapterStatus.EDITED
        self.repo.update_chapter(chapter)
        return chapter


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
