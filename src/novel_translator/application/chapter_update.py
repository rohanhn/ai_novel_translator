"""Cập nhật chương của truyện đã có từ file TXT (spec `chapter-update`, design D2–D4).

Luồng: draft gắn truyện (`ImportDraftService.create(..., novel_id)`) → `preview` (chế độ do
người dùng chọn, không ghi gì) → `apply` (tính lại từ đầu vào, kiểm tra revision, ghi trong một
transaction). Logic so khớp nằm ở `domain/chapter_merge.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import Enum

from ..domain import chapter_merge, chapter_split
from ..domain.models import Chapter, ChapterStatus, Novel, ReadingProgress
from ..domain.ports import NovelRepository
from .imports import Draft, ImportDraftService
from .jobs import Lane, TranslationJobManager
from .services import InvalidOperationError, NotFoundError, NovelBusyError, new_chapter

SUPPORTED_DETECTED = ("zh", "vi")
_Kind = chapter_merge.EntryKind


class UpdateMode(str, Enum):
    APPEND = "append"  # thêm chương mới sau điểm nối
    REPLACE = "replace"  # tải lại cả bộ theo thứ tự file


class LanguageMismatchError(InvalidOperationError):
    """Ngôn ngữ nhận diện của file khác ngôn ngữ nguồn của truyện (API 422)."""


class StartRequiredError(InvalidOperationError):
    """Không tự xác định được điểm nối: người dùng phải chọn chương bắt đầu (API 422)."""


class NothingNewError(InvalidOperationError):
    """Chế độ thêm nhưng file không có chương nào sau điểm nối (API 409)."""


class StalePreviewError(InvalidOperationError):
    """Truyện đã thay đổi kể từ lúc tính bản xem trước (API 409)."""


@dataclass(frozen=True)
class ProgressMove:
    from_index: int
    from_position: float
    to_index: int
    to_position: float


@dataclass
class UpdatePreview:
    novel: Novel
    mode: UpdateMode
    revision: str
    stored_count: int
    incoming_count: int
    append: chapter_merge.AppendPlan | None = None
    replace: chapter_merge.ReplacePlan | None = None
    progress: ProgressMove | None = None  # chỉ với chế độ tải lại, khi có tiến độ đọc


@dataclass
class UpdateResult:
    novel: Novel
    mode: UpdateMode
    chapter_count: int  # số chương sau cập nhật
    added: int = 0  # chế độ thêm
    reused: int = 0
    changed: int = 0
    new: int = 0
    kept: int = 0
    deleted: int = 0
    progress: ProgressMove | None = None


def chapters_revision(chapters: Iterable[Chapter]) -> str:
    """Dấu vân tay danh sách chương: mọi lần dịch/sửa/đổi trạng thái/cập nhật đều đổi `id` hoặc
    `updated_at`, nên bản xem trước cũ sẽ lệch revision."""
    h = hashlib.sha256()
    n = 0
    for c in chapters:
        n += 1
        h.update(f"{c.id}:{c.index}:{c.status.value}:{c.updated_at.isoformat()}\n".encode())
    h.update(f"count={n}".encode())
    return h.hexdigest()[:32]


def _stored_ref(c: Chapter) -> chapter_merge.StoredRef:
    return chapter_merge.StoredRef(c.index, c.title, c.source_text, c.status.value)


def _incoming(plan: chapter_split.SplitPlan) -> list[chapter_merge.Incoming]:
    return [chapter_merge.Incoming(c.number, c.title, c.body, c.heading_number)
            for c in plan.chapters]


class ChapterUpdateService:
    def __init__(self, repo: NovelRepository, drafts: ImportDraftService,
                 jobs: TranslationJobManager):
        self.repo = repo
        self.drafts = drafts
        self.jobs = jobs

    # --- nội bộ ---
    def _novel_of(self, draft: Draft) -> Novel:
        if draft.novel_id is None:
            raise InvalidOperationError("Bản xem trước này dùng để tạo truyện mới, không phải cập "
                                        "nhật chương.")
        novel = self.repo.get_novel(draft.novel_id)
        if novel is None:
            raise NotFoundError(f"Không có truyện id={draft.novel_id}")
        return novel

    @staticmethod
    def _check_language(novel: Novel, detected: str) -> None:
        if detected in SUPPORTED_DETECTED and detected != novel.source_lang:
            names = {"zh": "tiếng Trung", "vi": "tiếng Việt"}
            raise LanguageMismatchError(
                f"File là {names[detected]} ({detected}) nhưng truyện là "
                f"{names.get(novel.source_lang, novel.source_lang)} ({novel.source_lang}).")

    def _compute(self, draft: Draft, mode: UpdateMode | str, boundaries: list[int],
                 keep_front_matter: bool | None, start: int | None,
                 delete: Iterable[int]) -> tuple[UpdatePreview, list[Chapter],
                                                 list[chapter_merge.Incoming]]:
        mode = UpdateMode(mode)
        novel = self._novel_of(draft)
        self._check_language(novel, draft.detected_lang)
        split = chapter_split.apply(draft.text, boundaries, keep_front_matter)
        if not split.chapters:
            raise ValueError("Không tìm thấy nội dung trong file.")
        incoming = _incoming(split)
        chapters = self.repo.list_chapters(novel.id)
        refs = [_stored_ref(c) for c in chapters]
        preview = UpdatePreview(novel, mode, chapters_revision(chapters), len(chapters),
                                len(incoming))
        if mode is UpdateMode.APPEND:
            preview.append = chapter_merge.plan_append(refs, incoming, start)
        else:
            preview.replace = chapter_merge.plan_replace(refs, incoming, set(delete))
            progress = self.repo.get_progress(novel.id)
            if progress is not None:
                to_index, to_pos = preview.replace.remap_progress(progress.chapter_index,
                                                                  progress.position)
                preview.progress = ProgressMove(progress.chapter_index, progress.position,
                                                to_index, to_pos)
        return preview, chapters, incoming

    # --- thao tác ---
    def preview(self, draft_id: str, mode: UpdateMode | str, boundaries: list[int],
                keep_front_matter: bool | None = None, start: int | None = None,
                delete: Iterable[int] = ()) -> UpdatePreview:
        """Tính thay đổi cho chế độ đã chọn. Không ghi gì."""
        draft = self.drafts.get(draft_id)
        return self._compute(draft, mode, boundaries, keep_front_matter, start, delete)[0]

    def apply(self, draft_id: str, mode: UpdateMode | str, boundaries: list[int],
              keep_front_matter: bool | None = None, start: int | None = None,
              delete: Iterable[int] = (), revision: str = "") -> UpdateResult:
        """Tính lại từ đầu vào rồi ghi. `revision` phải khớp revision của bản xem trước, nếu
        không → `StalePreviewError`. Xong thì xóa draft; lỗi thì giữ draft để thử lại."""
        draft = self.drafts.get(draft_id)
        if UpdateMode(mode) is UpdateMode.APPEND:
            result = self._apply_append(draft, boundaries, keep_front_matter, start, revision)
        else:
            result = self._apply_replace(draft, boundaries, keep_front_matter, delete, revision)
        self.drafts.discard(draft_id)
        return result

    @staticmethod
    def _check_revision(preview: UpdatePreview, revision: str) -> None:
        if preview.revision != revision:
            raise StalePreviewError("Truyện vừa thay đổi sau lúc xem trước, hãy xem lại thay đổi.")

    def _append(self, novel: Novel, chapters: list[Chapter],
                plan: chapter_merge.AppendPlan) -> UpdateResult:
        if plan.needs_start:
            raise StartRequiredError("Không tìm thấy điểm nối; hãy chọn chương bắt đầu thêm.")
        if plan.nothing_new:
            raise NothingNewError("File không có chương mới nào sau chương cuối của truyện.")
        last = max((c.index for c in chapters), default=0)
        added = [new_chapter(novel, last + i, inc.title, inc.body)
                 for i, inc in enumerate(plan.to_add, start=1)]
        self.repo.add_chapters(added)
        return UpdateResult(novel, UpdateMode.APPEND, last + len(added), added=len(added))

    def _apply_append(self, draft: Draft, boundaries: list[int], keep_front_matter: bool | None,
                      start: int | None, revision: str) -> UpdateResult:
        preview, chapters, _ = self._compute(draft, UpdateMode.APPEND, boundaries,
                                             keep_front_matter, start, ())
        self._check_revision(preview, revision)
        return self._append(preview.novel, chapters, preview.append)

    def _apply_replace(self, draft: Draft, boundaries: list[int],
                       keep_front_matter: bool | None, delete: Iterable[int],
                       revision: str) -> UpdateResult:
        """Thay danh sách chương (design D3/D4): giữ truyện để không có job mới chen vào, bỏ
        prefetch còn chờ, từ chối khi còn job dịch, rồi ghi chương + tiến độ trong một
        transaction."""
        novel = self._novel_of(draft)
        with self.jobs.hold_novel(novel.id):
            self.jobs.cancel_queued_for_novel(novel.id, Lane.BACKGROUND)
            if self.jobs.has_jobs_for_novel(novel.id):
                raise NovelBusyError("Đang có chương của truyện được dịch; đợi dịch xong rồi tải "
                                     "lại cả bộ.")
            preview, chapters, _ = self._compute(draft, UpdateMode.REPLACE, boundaries,
                                                 keep_front_matter, None, delete)
            self._check_revision(preview, revision)
            plan = preview.replace
            by_index = {c.index: c for c in chapters}
            result: list[Chapter] = []
            for i, e in enumerate(plan.entries, start=1):
                if e.kind in (_Kind.REUSE, _Kind.KEPT):
                    old = by_index[e.stored.index]
                    ch = replace(old, id=None, index=i)
                    if e.kind is _Kind.REUSE:
                        ch.title = e.incoming.title  # thứ tự và tiêu đề gốc theo file mới
                    if ch.status == ChapterStatus.TRANSLATING:
                        ch.status = ChapterStatus.PENDING  # không còn job nào đang dịch nó
                    result.append(ch)
                else:  # CHANGED, NEW: nội dung mới, bỏ bản dịch cũ (kể cả bản sửa tay)
                    result.append(new_chapter(preview.novel, i, e.incoming.title, e.incoming.body))
            with self.repo.unit_of_work():
                self.repo.replace_chapters(preview.novel.id, result)
                if preview.progress is not None:
                    self.repo.save_progress(ReadingProgress(
                        preview.novel.id, preview.progress.to_index,
                        preview.progress.to_position))
        return UpdateResult(
            preview.novel, UpdateMode.REPLACE, len(result),
            reused=plan.count(_Kind.REUSE), changed=plan.count(_Kind.CHANGED),
            new=plan.count(_Kind.NEW), kept=plan.count(_Kind.KEPT), deleted=len(plan.deleted),
            progress=preview.progress)


__all__ = [
    "ChapterUpdateService",
    "LanguageMismatchError",
    "NothingNewError",
    "ProgressMove",
    "StalePreviewError",
    "StartRequiredError",
    "UpdateMode",
    "UpdatePreview",
    "UpdateResult",
    "chapters_revision",
]
