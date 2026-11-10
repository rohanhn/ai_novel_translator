"""ChapterUpdateService (spec `chapter-update`): xem trước và áp cập nhật chương từ TXT."""

from __future__ import annotations

import pytest

from novel_translator.application.chapter_update import (
    LanguageMismatchError,
    NothingNewError,
    StalePreviewError,
    StartRequiredError,
    UpdateMode,
)
from novel_translator.application.imports import DraftExpiredError
from novel_translator.domain.models import ChapterStatus, ReadingProgress


def zh_txt(numbers, revised=(), extra_before=None) -> bytes:
    """File tiếng Trung với các chương `numbers`; chương trong `revised` có nội dung khác."""
    parts = []
    for n in numbers:
        if extra_before and n in extra_before:
            parts.append(extra_before[n])
        body = f"林动第{n}章的正文，内容足够长。" * 3
        if n in revised:
            body += "作者修改。"
        parts.append(f"第{n}章 标题{n}\n{body}")
    return "\n".join(parts).encode()


@pytest.fixture
def novel(container):
    """Truyện tiếng Trung 1..5, chương 2 đã dịch, chương 3 đã sửa tay."""
    n = container.library.import_bytes(zh_txt(range(1, 6)), "Vũ Động", "zh").novel
    repo = container.repo
    for idx, status in ((2, ChapterStatus.TRANSLATED), (3, ChapterStatus.EDITED)):
        ch = repo.get_chapter(n.id, idx)
        ch.translated_title, ch.translated_text = f"Chương {idx}", f"Bản dịch {idx}"
        ch.status, ch.provider = status, "gemini"
        repo.update_chapter(ch)
    return n


def draft_for(container, novel, data: bytes):
    return container.imports.create("moi.txt", data, novel_id=novel.id)


def snapshot(repo, novel_id):
    return [(c.id, c.index, c.title, c.status, c.translated_text, c.updated_at)
            for c in repo.list_chapters(novel_id)]


def test_preview_does_not_modify(container, novel):
    repo = container.repo
    repo.save_progress(ReadingProgress(novel.id, 3, 0.4))
    before, progress = snapshot(repo, novel.id), repo.get_progress(novel.id)
    d = draft_for(container, novel, zh_txt(range(1, 8), revised={2}))
    for mode in UpdateMode:
        container.chapter_updates.preview(d.id, mode, d.plan.boundaries)
    container.imports.discard(d.id)
    assert snapshot(repo, novel.id) == before
    after = repo.get_progress(novel.id)
    assert (after.chapter_index, after.position) == (progress.chapter_index, progress.position)


def test_append_preview(container, novel):
    d = draft_for(container, novel, zh_txt(range(1, 8)))
    p = container.chapter_updates.preview(d.id, "append", d.plan.boundaries)
    assert p.mode is UpdateMode.APPEND and p.stored_count == 5 and p.incoming_count == 7
    assert p.append.anchor.stored_index == 5
    assert [c.title for c in p.append.to_add] == ["第6章 标题6", "第7章 标题7"]
    assert p.replace is None and p.progress is None and len(p.revision) == 32


def test_replace_preview_counts(container, novel):
    container.repo.save_progress(ReadingProgress(novel.id, 4, 0.5))
    side = "番外 雪夜\n" + "番外的正文内容。" * 5
    data = zh_txt([1, 2, 3, 4, 6, 7], revised={2, 3}, extra_before={4: side})
    d = draft_for(container, novel, data)
    p = container.chapter_updates.preview(d.id, "replace", d.plan.boundaries)
    r = p.replace
    counts = {k: r.count(k) for k in r.entries[0].kind.__class__}
    assert counts == {"reuse": 2, "changed": 2, "new": 3, "kept": 1}
    assert [s.index for s in r.missing] == [5]
    assert [s.index for s in r.edited_lost] == [3]
    # chương 4 đứng sau "番外" mới chèn → thành chương 5, giữ vị trí cuộn
    assert (p.progress.from_index, p.progress.to_index, p.progress.to_position) == (4, 5, 0.5)


def test_vietnamese_file_for_a_chinese_novel(container, novel):
    vi = "\n".join(f"Chương {n}: Tên {n}\n" + "Lâm Động đứng trên núi nhìn về phía xa. " * 3
                   for n in (6, 7)).encode()
    d = draft_for(container, novel, vi)
    with pytest.raises(LanguageMismatchError) as e:
        container.chapter_updates.preview(d.id, "append", d.plan.boundaries)
    assert "(vi)" in str(e.value) and "(zh)" in str(e.value)


def test_unknown_language_file_is_accepted(container, novel):
    d = draft_for(container, novel, b"Chapter 6\nplain ascii text without accents\n")
    assert d.detected_lang == "unknown"
    p = container.chapter_updates.preview(d.id, "append", d.plan.boundaries)
    assert [c.title for c in p.append.to_add] == ["Chapter 6"]


def test_import_draft_cannot_be_used_for_update(container, novel):
    from novel_translator.application.services import InvalidOperationError

    d = container.imports.create("a.txt", zh_txt([6]))
    with pytest.raises(InvalidOperationError):
        container.chapter_updates.preview(d.id, "append", d.plan.boundaries)


def test_invalid_mode_rejected(container, novel):
    d = draft_for(container, novel, zh_txt([6]))
    with pytest.raises(ValueError):
        container.chapter_updates.preview(d.id, "merge", d.plan.boundaries)


# --- apply: append ----------------------------------------------------------------------------


def apply_with_preview(container, draft, mode, **kw):
    svc = container.chapter_updates
    p = svc.preview(draft.id, mode, draft.plan.boundaries, **kw)
    return svc.apply(draft.id, mode, draft.plan.boundaries, revision=p.revision, **kw)


def test_chapters_appended(container, novel):
    repo = container.repo
    repo.save_progress(ReadingProgress(novel.id, 2, 0.3))
    before = snapshot(repo, novel.id)
    d = draft_for(container, novel, zh_txt(range(1, 9), revised={3}))
    res = apply_with_preview(container, d, "append")
    assert (res.added, res.chapter_count) == (3, 8)
    chs = repo.list_chapters(novel.id)
    assert snapshot(repo, novel.id)[:5] == before  # chương cũ không đổi (kể cả chương 3 đã sửa)
    assert [(c.index, c.title, c.status) for c in chs[5:]] == [
        (6, "第6章 标题6", ChapterStatus.PENDING), (7, "第7章 标题7", ChapterStatus.PENDING),
        (8, "第8章 标题8", ChapterStatus.PENDING)]
    assert "林动第7章" in chs[6].source_text and chs[6].translated_text is None
    p = repo.get_progress(novel.id)
    assert (p.chapter_index, p.position) == (2, 0.3)  # thêm chương không đổi tiến độ đọc
    with pytest.raises(DraftExpiredError):  # draft đã xóa sau khi áp
        container.imports.get(d.id)


def test_append_to_a_vietnamese_novel_makes_no_llm_request(container):
    body = "Trần Bình An ngồi trước cửa ngõ, nhìn mưa xuân rơi trên mái hiên. " * 3

    def vi(ns) -> bytes:
        return "\n".join(f"Chương {n}: Tên {n}\n{body}{n}" for n in ns).encode()

    novel = container.library.import_bytes(vi(range(1, 4)), "Kiếm Lai", "vi").novel
    d = container.imports.create("moi.txt", vi(range(1, 9)), novel_id=novel.id)
    res = apply_with_preview(container, d, "append")
    assert res.added == 5
    new = container.repo.list_chapters(novel.id)[3:]
    assert all(c.status == ChapterStatus.TRANSLATED and c.provider == "import" for c in new)
    assert new[0].translated_text == new[0].source_text
    assert not container.jobs.has_jobs_for_novel(novel.id)
    assert container.quota.usage_today() == []


def test_append_rejected_when_chapter_translated_after_preview(container, novel):
    repo = container.repo
    d = draft_for(container, novel, zh_txt(range(1, 7)))
    p = container.chapter_updates.preview(d.id, "append", d.plan.boundaries)
    ch = repo.get_chapter(novel.id, 1)
    ch.translated_title, ch.translated_text, ch.status = "C1", "Dịch", ChapterStatus.TRANSLATED
    repo.update_chapter(ch)
    before = snapshot(repo, novel.id)
    with pytest.raises(StalePreviewError):
        container.chapter_updates.apply(d.id, "append", d.plan.boundaries, revision=p.revision)
    assert snapshot(repo, novel.id) == before
    assert container.imports.get(d.id)  # draft còn để xem lại


def test_append_nothing_new(container, novel):
    d = draft_for(container, novel, zh_txt(range(1, 6)))
    with pytest.raises(NothingNewError):
        apply_with_preview(container, d, "append")


def test_append_needs_start_then_owner_picks(container, novel):
    d = draft_for(container, novel, "番外 一\n番外内容一\n番外 二\n番外内容二".encode())
    p = container.chapter_updates.preview(d.id, "append", d.plan.boundaries)
    assert p.append.needs_start
    with pytest.raises(StartRequiredError):
        container.chapter_updates.apply(d.id, "append", d.plan.boundaries, revision=p.revision)
    res = apply_with_preview(container, d, "append", start=2)
    assert res.added == 1
    assert container.repo.get_chapter(novel.id, 6).title == "番外 二"
