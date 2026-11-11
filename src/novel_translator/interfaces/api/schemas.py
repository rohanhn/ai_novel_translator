"""Schema JSON của API. Chỉ chuyển đổi domain ↔ JSON, không chứa logic."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ...application.chapter_update import ProgressMove, UpdatePreview, UpdateResult
from ...application.imports import Draft
from ...domain.chapter_merge import EntryKind, StoredRef
from ...domain.chapter_split import SplitWarning
from ...domain.models import (
    Chapter,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    NovelSummary,
    ReadingProgress,
)


def cover_url(n: Novel) -> str | None:
    """Địa chỉ ảnh bìa có phiên bản (`?v=` theo thời điểm đổi ảnh) để không bao giờ dùng
    ảnh cũ trong cache; `None` khi chưa có ảnh (web vẽ bìa tự sinh)."""
    if n.cover_updated_at is None:
        return None
    return f"/api/novels/{n.id}/cover?v={int(n.cover_updated_at.timestamp() * 1000)}"


class NovelOut(BaseModel):
    id: int
    title: str
    author: str | None
    description: str | None  # giới thiệu ngắn, giữ xuống dòng
    cover_url: str | None
    source_lang: str
    target_lang: str
    pretranslated: bool  # bản dịch có sẵn (import từ file tiếng Việt): không dịch bằng model
    glossary_version: int
    created_at: datetime
    last_read_at: datetime | None

    @classmethod
    def of(cls, n: Novel) -> NovelOut:
        return cls(id=n.id, title=n.title, author=n.author, description=n.description,
                   cover_url=cover_url(n), source_lang=n.source_lang, target_lang=n.target_lang,
                   pretranslated=n.pretranslated, glossary_version=n.glossary_version,
                   created_at=n.created_at, last_read_at=n.last_read_at)


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
    untranslated_han: int  # số chữ Hán còn sót trong bản dịch
    chain_step: int | None  # >1: dịch bằng model dự phòng
    job_lane: str | None = None  # có job đang chờ/chạy: foreground | background (prefetch)

    @classmethod
    def of(cls, c: Chapter, job_lane: str | None = None) -> ChapterSummary:
        return cls(index=c.index, title=c.title, translated_title=c.translated_title,
                   status=c.status.value, glossary_outdated=c.glossary_outdated,
                   possible_omission=c.possible_omission,
                   untranslated_han=c.untranslated_han, chain_step=c.chain_step,
                   job_lane=job_lane)


class ChapterOut(ChapterSummary):
    source_text: str
    translated_text: str | None
    provider: str | None
    model: str | None
    glossary_version: int | None
    # chữ Hán còn sót (riêng biệt) để màn đọc tô sáng; tính theo bộ tên hiện tại
    untranslated_chars: list[str] = []

    @classmethod
    def of(cls, c: Chapter, job_lane: str | None = None,
           untranslated_chars: tuple[str, ...] = ()) -> ChapterOut:
        return cls(**ChapterSummary.of(c, job_lane).model_dump(), source_text=c.source_text,
                   translated_text=c.translated_text, provider=c.provider, model=c.model,
                   glossary_version=c.glossary_version,
                   untranslated_chars=list(untranslated_chars))


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


# ---------- import có xem trước (design D3) ----------
EXCERPT_CHARS = 80


def _excerpt(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line[:EXCERPT_CHARS] + ("…" if len(one_line) > EXCERPT_CHARS else "")


class SplitWarningOut(BaseModel):
    code: str
    message: str
    params: dict

    @classmethod
    def of(cls, w: SplitWarning) -> SplitWarningOut:
        return cls(code=w.code, message=w.message, params=w.params)


class ImportChapterOut(BaseModel):
    number: int
    start_line: int
    end_line: int
    title: str
    chars: int
    excerpt: str
    warnings: list[SplitWarningOut]


class FrontMatterOut(BaseModel):
    start_line: int
    end_line: int
    chars: int
    excerpt: str
    keep: bool


class ImportPreview(BaseModel):
    id: str
    novel_id: int | None = None  # có giá trị: bản xem trước để cập nhật chương của truyện này
    filename: str
    default_title: str
    detected_lang: str  # zh | vi | unknown
    line_count: int
    boundaries: list[int]
    front_matter: FrontMatterOut | None
    chapters: list[ImportChapterOut]
    warnings: list[SplitWarningOut]

    @classmethod
    def of(cls, d: Draft) -> ImportPreview:
        p = d.plan
        fm = p.front_matter
        return cls(
            id=d.id, novel_id=d.novel_id, filename=d.filename, default_title=d.default_title,
            detected_lang=d.detected_lang, line_count=p.line_count, boundaries=p.boundaries,
            front_matter=FrontMatterOut(start_line=fm.start_line, end_line=fm.end_line,
                                        chars=fm.chars, excerpt=_excerpt(fm.text), keep=fm.keep)
            if fm else None,
            chapters=[ImportChapterOut(
                number=c.number, start_line=c.start_line, end_line=c.end_line, title=c.title,
                chars=c.chars, excerpt=_excerpt(c.body),
                warnings=[SplitWarningOut.of(w) for w in c.warnings],
            ) for c in p.chapters],
            warnings=[SplitWarningOut.of(w) for w in p.warnings],
        )


class ImportAdjustIn(BaseModel):
    boundaries: list[int]
    keep_front_matter: bool | None = None


class ImportCommitIn(ImportAdjustIn):
    title: str | None = Field(None, max_length=300)
    lang: Literal["zh", "vi"] | None = None


class UpdateIn(ImportAdjustIn):
    """Tính thay đổi khi cập nhật chương (spec `chapter-update`). `mode` bắt buộc (422 nếu thiếu)."""

    mode: Literal["append", "replace"]
    start: int | None = Field(None, ge=1)  # chế độ thêm: vị trí chương bắt đầu trong file
    delete: list[int] = Field(default_factory=list)  # tải lại: index chương thiếu sẽ xóa


class UpdateApplyIn(UpdateIn):
    revision: str = Field(min_length=1, max_length=64)


class StoredChapterRef(BaseModel):
    index: int
    title: str
    status: str

    @classmethod
    def of(cls, s: StoredRef) -> StoredChapterRef:
        return cls(index=s.index, title=s.title, status=s.status)


class FileChapterRef(BaseModel):
    position: int  # thứ tự trong file (= `number` của chương trong ImportPreview)
    title: str


class AnchorOut(BaseModel):
    index: int
    title: str
    position: int
    match: Literal["content", "title"]


class ProgressMoveOut(BaseModel):
    from_index: int
    from_position: float
    to_index: int
    to_position: float

    @classmethod
    def of(cls, m: ProgressMove | None) -> ProgressMoveOut | None:
        if m is None:
            return None
        return cls(from_index=m.from_index, from_position=m.from_position,
                   to_index=m.to_index, to_position=m.to_position)


class NewChapterRef(BaseModel):
    """Chương mới khi tải lại: vị trí trong file và số chương sẽ nhận sau khi tải lại."""

    position: int
    title: str
    index: int


class UpdateCounts(BaseModel):
    reuse: int
    changed: int
    new: int
    missing: int


class UpdatePreviewOut(BaseModel):
    mode: Literal["append", "replace"]
    revision: str
    stored_count: int
    incoming_count: int
    warnings: list[SplitWarningOut]
    # chế độ thêm
    anchor: AnchorOut | None = None
    needs_start: bool = False
    nothing_new: bool = False
    to_add: list[FileChapterRef] = Field(default_factory=list)
    differing: list[StoredChapterRef] = Field(default_factory=list)
    middle: list[FileChapterRef] = Field(default_factory=list)  # chương thiếu ở giữa
    # chế độ tải lại
    counts: UpdateCounts | None = None
    changed: list[StoredChapterRef] = Field(default_factory=list)
    missing: list[StoredChapterRef] = Field(default_factory=list)
    new: list[NewChapterRef] = Field(default_factory=list)
    edited_lost: list[StoredChapterRef] = Field(default_factory=list)
    progress: ProgressMoveOut | None = None

    @classmethod
    def of(cls, p: UpdatePreview) -> UpdatePreviewOut:
        out = cls(mode=p.mode.value, revision=p.revision, stored_count=p.stored_count,
                  incoming_count=p.incoming_count, warnings=[], progress=ProgressMoveOut.of(
                      p.progress))
        if p.append is not None:
            a = p.append
            out.warnings = [SplitWarningOut(code=w.code, message=w.message, params=w.params)
                            for w in a.warnings]
            out.anchor = AnchorOut(index=a.anchor.stored_index, title=a.anchor.title,
                                   position=a.anchor.position, match=a.anchor.match) \
                if a.anchor else None
            out.needs_start, out.nothing_new = a.needs_start, a.nothing_new
            out.to_add = [FileChapterRef(position=c.position, title=c.title) for c in a.to_add]
            out.differing = [StoredChapterRef.of(s) for s in a.differing]
            out.middle = [FileChapterRef(position=c.position, title=c.title) for c in a.middle]
        if p.replace is not None:
            r = p.replace
            out.counts = UpdateCounts(reuse=r.count(EntryKind.REUSE),
                                      changed=r.count(EntryKind.CHANGED),
                                      new=r.count(EntryKind.NEW), missing=len(r.missing))
            out.changed = [StoredChapterRef.of(e.stored) for e in r.entries
                           if e.kind is EntryKind.CHANGED]
            out.missing = [StoredChapterRef.of(s) for s in r.missing]
            out.new = [NewChapterRef(position=e.incoming.position, title=e.incoming.title, index=i)
                       for i, e in enumerate(r.entries, start=1) if e.kind is EntryKind.NEW]
            out.edited_lost = [StoredChapterRef.of(s) for s in r.edited_lost]
        return out


class UpdateResultOut(BaseModel):
    novel: NovelOut
    mode: Literal["append", "replace"]
    chapter_count: int
    added: int
    reused: int
    changed: int
    new: int
    kept: int
    deleted: int
    progress: ProgressMoveOut | None

    @classmethod
    def of(cls, r: UpdateResult) -> UpdateResultOut:
        return cls(novel=NovelOut.of(r.novel), mode=r.mode.value, chapter_count=r.chapter_count,
                   added=r.added, reused=r.reused, changed=r.changed, new=r.new, kept=r.kept,
                   deleted=r.deleted, progress=ProgressMoveOut.of(r.progress))


class ImportLinesOut(BaseModel):
    start: int
    lines: list[str]


class NovelDetailsIn(BaseModel):
    """PATCH thông tin truyện: chỉ trường có mặt trong body được đổi (`model_fields_set`).
    Không đặt giới hạn độ dài ở đây: `normalize_details` kiểm và báo lỗi kèm `field` (400)."""

    title: str | None = None
    author: str | None = None
    description: str | None = None


class CoverFetchIn(BaseModel):
    url: str
