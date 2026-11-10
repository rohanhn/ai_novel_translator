"""Bản xem trước import (design D2, spec novel-library "Upload novel from the web")."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.application.imports import (
    DraftExpiredError,
    ImportDraftService,
)
from novel_translator.domain.models import ChapterStatus
from novel_translator.ingest.txt_loader import TxtLoader

BODY = "Trần Bình An ngồi trước cửa ngõ, nhìn mưa xuân rơi trên mái hiên. " * 3
VI = "\n".join(f"Chương {n}: Tên {n}\n{BODY}" for n in (1, 2, 3, 4)).encode()


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 10, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def drafts(container, clock):
    return ImportDraftService(container.library, TxtLoader(), clock=clock)


def test_create_returns_plan_without_saving(container, drafts):
    d = drafts.create("kiemlai.txt", VI)
    assert d.detected_lang == "vi" and d.default_title == "kiemlai"
    assert [c.title for c in d.plan.chapters] == [f"Chương {n}: Tên {n}" for n in (1, 2, 3, 4)]
    assert container.library.list_novels() == []  # chưa lưu gì trước khi xác nhận


def test_create_rejects_empty_and_decodes_gb18030(drafts):
    with pytest.raises(ValueError):
        drafts.create("a.txt", b"\n \n")
    d = drafts.create("gbk.txt", "第一章 少年\n林动。".encode("gb18030"))
    assert d.detected_lang == "zh" and d.plan.chapters[0].title == "第一章 少年"


def test_adjust_merge_then_commit_uses_sent_boundaries(container, drafts):
    d = drafts.create("kiemlai.txt", VI)
    b = d.plan.boundaries
    adjusted = drafts.adjust(d.id, [b[0], b[1], b[3]])  # bỏ chương 3 → gộp vào chương 2
    assert len(adjusted.plan.chapters) == 3
    assert "Chương 3: Tên 3" in adjusted.plan.chapters[1].body
    # commit nhận lại ranh giới: không phụ thuộc thứ tự các lần chỉnh trước
    res = drafts.commit(d.id, "", None, [b[0], b[1], b[3]])
    assert res.novel.title == "kiemlai" and res.chapters == 3 and res.lang == "vi"
    chs = container.library.list_chapters(res.novel.id)
    assert [c.status for c in chs] == [ChapterStatus.TRANSLATED] * 3
    assert "Chương 3: Tên 3" in chs[1].translated_text


def test_commit_with_language_override_and_title(container, drafts):
    d = drafts.create("kiemlai.txt", VI)
    res = drafts.commit(d.id, "Kiếm Lai", "zh", d.plan.boundaries)
    assert res.novel.title == "Kiếm Lai" and not res.novel.pretranslated
    assert {c.status for c in container.library.list_chapters(res.novel.id)} == {
        ChapterStatus.PENDING}


def test_commit_removes_draft(drafts):
    d = drafts.create("a.txt", VI)
    drafts.commit(d.id, None, None, d.plan.boundaries)
    with pytest.raises(DraftExpiredError):
        drafts.commit(d.id, None, None, d.plan.boundaries)


def test_expires_after_ttl_since_last_use(drafts, clock):
    d = drafts.create("a.txt", VI)
    clock.advance(minutes=50)
    drafts.get(d.id)  # dùng lại → gia hạn
    clock.advance(minutes=50)
    assert drafts.get(d.id).id == d.id
    clock.advance(minutes=61)
    with pytest.raises(DraftExpiredError):
        drafts.get(d.id)


def test_fourth_draft_evicts_oldest(drafts, clock):
    ids = []
    for i in range(4):
        ids.append(drafts.create(f"{i}.txt", VI).id)
        clock.advance(minutes=1)
    with pytest.raises(DraftExpiredError):
        drafts.get(ids[0])
    for i in ids[1:]:
        assert drafts.get(i).id == i


def test_new_service_has_no_drafts(container, drafts):
    """Server restart = service mới: draft cũ không còn."""
    d = drafts.create("a.txt", VI)
    fresh = ImportDraftService(container.library, TxtLoader())
    with pytest.raises(DraftExpiredError):
        fresh.commit(d.id, None, None, d.plan.boundaries)
    assert container.library.list_novels() == []


def test_lines_window(drafts):
    d = drafts.create("a.txt", VI)
    assert drafts.lines(d.id, 0, 2) == ["Chương 1: Tên 1", BODY]
    many = drafts.create("b.txt", ("dòng\n" * 2000).encode())
    assert len(drafts.lines(many.id, 0, 10_000)) == 500
    assert drafts.lines(many.id, 1990, 50) == ["dòng"] * 10 + [""]
    with pytest.raises(ValueError):
        drafts.lines(d.id, -1, 5)


def test_discard(container, drafts):
    d = drafts.create("a.txt", VI)
    drafts.discard(d.id)
    drafts.discard(d.id)  # gọi lại không lỗi
    with pytest.raises(DraftExpiredError):
        drafts.get(d.id)
    assert container.library.list_novels() == []


def test_invalid_boundaries_rejected(drafts):
    d = drafts.create("a.txt", VI)
    with pytest.raises(ValueError):
        drafts.adjust(d.id, [10_000])


def test_container_wires_import_service(container):
    assert isinstance(container.imports, ImportDraftService)
