"""Cập nhật chương của truyện đã có từ file TXT (spec `chapter-update`, design D2–D4).

Luồng: draft gắn truyện (`ImportDraftService.create(..., novel_id)`) → `preview` (chế độ do
người dùng chọn, không ghi gì) → `apply` (tính lại từ đầu vào, kiểm tra revision, ghi trong một
transaction). Logic so khớp nằm ở `domain/chapter_merge.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from ..domain import chapter_merge, chapter_split
from ..domain.models import Chapter, Novel
from ..domain.ports import NovelRepository
from .imports import Draft, ImportDraftService
from .jobs import TranslationJobManager
from .services import InvalidOperationError, NotFoundError

SUPPORTED_DETECTED = ("zh", "vi")


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


__all__ = [
    "ChapterUpdateService",
    "LanguageMismatchError",
    "NothingNewError",
    "ProgressMove",
    "StalePreviewError",
    "StartRequiredError",
    "UpdateMode",
    "UpdatePreview",
    "chapters_revision",
]
