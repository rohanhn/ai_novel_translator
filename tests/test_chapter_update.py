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


# --- apply: replace ---------------------------------------------------------------------------

SIDE = "番外 雪夜\n" + "番外的正文内容。" * 5


def by_title(repo, novel_id):
    return {c.title: c for c in repo.list_chapters(novel_id)}


def test_chapter_inserted_in_the_middle(container, novel):
    d = draft_for(container, novel, zh_txt(range(1, 6), extra_before={4: SIDE}))
    res = apply_with_preview(container, d, "replace")
    chs = container.repo.list_chapters(novel.id)
    assert [c.title for c in chs] == ["第1章 标题1", "第2章 标题2", "第3章 标题3", "番外 雪夜",
                                      "第4章 标题4", "第5章 标题5"]
    assert [c.index for c in chs] == [1, 2, 3, 4, 5, 6]
    assert (res.reused, res.new, res.changed, res.chapter_count) == (5, 1, 0, 6)


def test_unchanged_chapters_keep_translation_and_edits(container, novel):
    d = draft_for(container, novel, zh_txt(range(1, 7)))
    apply_with_preview(container, d, "replace")
    t = by_title(container.repo, novel.id)
    c2, c3 = t["第2章 标题2"], t["第3章 标题3"]
    assert (c2.status, c2.translated_text, c2.provider) == (
        ChapterStatus.TRANSLATED, "Bản dịch 2", "gemini")
    assert (c3.status, c3.translated_text) == (ChapterStatus.EDITED, "Bản dịch 3")
    assert t["第6章 标题6"].status == ChapterStatus.PENDING
    assert not container.jobs.has_jobs_for_novel(novel.id)  # không có request dịch nào


def test_revised_chapters_lose_translation_even_when_edited(container, novel):
    d = draft_for(container, novel, zh_txt(range(1, 6), revised={2, 3}))
    p = container.chapter_updates.preview(d.id, "replace", d.plan.boundaries)
    assert [s.index for s in p.replace.edited_lost] == [3]
    res = container.chapter_updates.apply(d.id, "replace", d.plan.boundaries,
                                          revision=p.revision)
    assert res.changed == 2
    t = by_title(container.repo, novel.id)
    for title in ("第2章 标题2", "第3章 标题3"):
        c = t[title]
        assert (c.status, c.translated_text, c.provider) == (ChapterStatus.PENDING, None, None)
        assert c.source_text.endswith("作者修改。")


def test_missing_chapter_kept_by_default(container, novel):
    d = draft_for(container, novel, zh_txt([1, 2, 4, 5]))
    res = apply_with_preview(container, d, "replace")
    chs = container.repo.list_chapters(novel.id)
    assert [c.title for c in chs] == [f"第{n}章 标题{n}" for n in (1, 2, 3, 4, 5)]
    assert chs[2].status == ChapterStatus.EDITED and chs[2].translated_text == "Bản dịch 3"
    assert (res.kept, res.deleted) == (1, 0)


def test_missing_chapter_deleted(container, novel):
    d = draft_for(container, novel, zh_txt([1, 2, 4, 5]))
    res = apply_with_preview(container, d, "replace", delete=[3])
    chs = container.repo.list_chapters(novel.id)
    assert [c.title for c in chs] == [f"第{n}章 标题{n}" for n in (1, 2, 4, 5)]
    assert [c.index for c in chs] == [1, 2, 3, 4]
    assert res.deleted == 1


def test_replace_moves_reading_progress(container, novel):
    repo = container.repo
    repo.save_progress(ReadingProgress(novel.id, 4, 0.4))
    d = draft_for(container, novel, zh_txt(range(1, 6), extra_before={4: SIDE}))
    res = apply_with_preview(container, d, "replace")
    p = repo.get_progress(novel.id)
    assert (p.chapter_index, p.position) == (5, 0.4)
    assert (res.progress.from_index, res.progress.to_index) == (4, 5)


def test_replace_keeps_glossary_and_details(container, novel):
    from novel_translator.domain.models import GlossaryEntry

    repo = container.repo
    repo.update_novel_details(novel.id, {"author": "Thiên Tàm Thổ Đậu"})
    for i in range(40):
        repo.upsert_glossary(GlossaryEntry(novel.id, f"词{i}", f"Từ {i}"))
    before = repo.get_novel(novel.id)
    d = draft_for(container, novel, zh_txt(range(1, 7), revised={1}))
    apply_with_preview(container, d, "replace")
    after = repo.get_novel(novel.id)
    assert (after.title, after.author, after.glossary_version) == (
        before.title, "Thiên Tàm Thổ Đậu", before.glossary_version)
    assert len(repo.list_glossary(novel.id)) == 40


def test_replace_rejected_while_job_running(container, novel, monkeypatch):
    import threading

    from novel_translator.application.jobs import Lane
    from novel_translator.application.services import NovelBusyError

    started, release = threading.Event(), threading.Event()
    real = container.translation.translate_chapter

    def slow(*a, **kw):
        started.set()
        assert release.wait(5)
        return real(*a, **kw)

    monkeypatch.setattr(container.translation, "translate_chapter", slow)
    job = container.jobs.submit(novel.id, 5, Lane.FOREGROUND)
    assert started.wait(5)
    d = draft_for(container, novel, zh_txt(range(1, 7)))
    p = container.chapter_updates.preview(d.id, "replace", d.plan.boundaries)
    before = snapshot(container.repo, novel.id)
    try:
        with pytest.raises(NovelBusyError):
            container.chapter_updates.apply(d.id, "replace", d.plan.boundaries,
                                            revision=p.revision)
        assert snapshot(container.repo, novel.id) == before
    finally:
        release.set()
        assert job.wait(5)


def test_replace_cancels_queued_prefetch(container, novel, monkeypatch):
    import threading

    from novel_translator.application.jobs import Lane

    other = container.library.import_bytes(zh_txt([1, 2]), "Khác", "zh").novel
    started, release = threading.Event(), threading.Event()
    real = container.translation.translate_chapter

    def slow(novel_id, *a, **kw):
        if novel_id == other.id:
            started.set()
            assert release.wait(5)
        return real(novel_id, *a, **kw)

    monkeypatch.setattr(container.translation, "translate_chapter", slow)
    blocker = container.jobs.submit(other.id, 1, Lane.BACKGROUND)  # giữ làn background bận
    assert started.wait(5)
    queued = container.jobs.submit(novel.id, 4, Lane.BACKGROUND)  # prefetch còn chờ
    try:
        d = draft_for(container, novel, zh_txt(range(1, 7)))
        res = apply_with_preview(container, d, "replace")
        assert res.new == 1
        assert queued.wait(5) and queued.terminal_event.type == "cancelled"
    finally:
        release.set()
        assert blocker.wait(5)


def test_failure_while_saving_rolls_back_and_keeps_draft(container, novel, monkeypatch):
    repo = container.repo
    repo.save_progress(ReadingProgress(novel.id, 4, 0.4))
    before, progress = snapshot(repo, novel.id), repo.get_progress(novel.id)
    d = draft_for(container, novel, zh_txt(range(1, 6), extra_before={4: SIDE}))
    p = container.chapter_updates.preview(d.id, "replace", d.plan.boundaries)

    def boom(_progress):
        raise RuntimeError("mất kết nối giữa chừng")

    monkeypatch.setattr(repo, "save_progress", boom)
    with pytest.raises(RuntimeError):
        container.chapter_updates.apply(d.id, "replace", d.plan.boundaries, revision=p.revision)
    assert snapshot(repo, novel.id) == before
    assert repo.get_progress(novel.id).chapter_index == progress.chapter_index
    monkeypatch.undo()
    res = container.chapter_updates.apply(d.id, "replace", d.plan.boundaries,
                                          revision=p.revision)  # draft còn: áp lại được
    assert res.chapter_count == 6


def test_replace_rejected_when_stale(container, novel):
    repo = container.repo
    d = draft_for(container, novel, zh_txt(range(1, 7)))
    p = container.chapter_updates.preview(d.id, "replace", d.plan.boundaries)
    ch = repo.get_chapter(novel.id, 1)
    ch.status = ChapterStatus.FAILED
    repo.update_chapter(ch)
    with pytest.raises(StalePreviewError):
        container.chapter_updates.apply(d.id, "replace", d.plan.boundaries, revision=p.revision)


# --- Bổ sung chương thiếu nằm giữa (task 7.2) ---------------------------------------------------


@pytest.fixture
def gappy(container):
    """Truyện tiếng Trung thiếu chương 4, 5 (đang có 1, 2, 3, 6, 7); chương 6 đã dịch."""
    n = container.library.import_bytes(zh_txt([1, 2, 3, 6, 7]), "Vũ Động", "zh").novel
    ch = container.repo.get_chapter(n.id, 4)
    assert ch.title == "第6章 标题6"
    ch.translated_title, ch.translated_text = "Chương 6", "Bản dịch 6"
    ch.status, ch.provider = ChapterStatus.TRANSLATED, "gemini"
    container.repo.update_chapter(ch)
    return n


def test_append_preview_lists_middle_chapters(container, gappy):
    d = draft_for(container, gappy, zh_txt(range(1, 9)))
    p = container.chapter_updates.preview(d.id, "append", d.plan.boundaries)
    assert [c.title for c in p.append.to_add] == ["第8章 标题8"]
    assert [c.title for c in p.append.middle] == ["第4章 标题4", "第5章 标题5"]


def test_replace_preview_shows_where_new_chapters_go(container, gappy):
    d = draft_for(container, gappy, zh_txt([4, 5]))
    p = container.chapter_updates.preview(d.id, "replace", d.plan.boundaries)
    new = [(i, e.incoming.title) for i, e in enumerate(p.replace.entries, start=1)
           if e.kind.value == "new"]
    assert new == [(4, "第4章 标题4"), (5, "第5章 标题5")]


def test_file_with_only_missing_chapters_fills_the_gap(container, gappy):
    repo = container.repo
    repo.save_progress(ReadingProgress(gappy.id, 4, 0.4))  # đang đọc chương 6
    d = draft_for(container, gappy, zh_txt([4, 5]))
    res = apply_with_preview(container, d, "replace")
    chs = repo.list_chapters(gappy.id)
    assert [c.title for c in chs] == [f"第{n}章 标题{n}" for n in range(1, 8)]
    assert [c.index for c in chs] == list(range(1, 8))
    assert (chs[5].status, chs[5].translated_text) == (ChapterStatus.TRANSLATED, "Bản dịch 6")
    assert [chs[i].status for i in (3, 4)] == [ChapterStatus.PENDING] * 2
    assert (res.new, res.kept, res.deleted) == (2, 5, 0)
    p = repo.get_progress(gappy.id)
    assert (p.chapter_index, p.position) == (6, 0.4)
