"""ChapterUpdateService (spec `chapter-update`): xem trước và áp cập nhật chương từ TXT."""

from __future__ import annotations

import pytest

from novel_translator.application.chapter_update import (
    LanguageMismatchError,
    UpdateMode,
)
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
