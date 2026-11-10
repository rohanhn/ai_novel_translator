"""Lan truyền đổi tên (design D9, spec glossary)."""

from __future__ import annotations

import pytest

from novel_translator.domain.models import Chapter, ChapterStatus, Novel
from novel_translator.domain.rename import replace_whole_word


def test_replace_whole_word_rules():
    assert replace_whole_word("Tô Nhu cười. Tô Nhuận đi.", "Tô Nhu", "Tô Nhược") == (
        "Tô Nhược cười. Tô Nhuận đi.", 1)
    assert replace_whole_word("(Tô Nhu)", "Tô Nhu", "X")[0] == "(X)"
    assert replace_whole_word("tô nhu", "Tô Nhu", "X")[0] == "tô nhu"  # phân biệt hoa thường
    assert replace_whole_word("Tô Nhu2", "Tô Nhu", "X")[0] == "Tô Nhu2"
    assert replace_whole_word("a.b", "a.b", "c") == ("c", 1)  # ký tự đặc biệt được escape
    assert replace_whole_word("x", "", "y") == ("x", 0)


@pytest.fixture
def lib(container, repo):
    novel = repo.add_novel(Novel(title="t"))
    chapters = {
        3: ("苏柔笑了。", "Tô Nhu cười. Tô Nhuận gật đầu.", ChapterStatus.TRANSLATED),
        4: ("苏柔来了。", "Tô Nhu tới.", ChapterStatus.EDITED),
        5: ("没有她。", "Tô Nhu không có trong raw.", ChapterStatus.TRANSLATED),
        6: ("苏柔走了。", None, ChapterStatus.PENDING),
        7: ("苏柔！", "Tô Nhu!", ChapterStatus.TRANSLATED),
    }
    repo.add_chapters([Chapter(novel_id=novel.id, index=i, title=f"第{i}章", source_text=src)
                       for i, (src, _, _) in chapters.items()])
    for i, (_, text, status) in chapters.items():
        ch = repo.get_chapter(novel.id, i)
        ch.translated_text, ch.status = text, status
        ch.translated_title = f"Chương {i}: Tô Nhu" if text else None
        repo.update_chapter(ch)
    container.glossary.set_term(novel.id, "苏柔", "Tô Nhu")
    return novel.id, container.glossary, repo


def test_rename_applied_to_translated_chapters_with_term(lib):
    nid, svc, repo = lib
    svc.set_term(nid, "苏柔", "Tô Nhược")
    ch3, ch7 = repo.get_chapter(nid, 3), repo.get_chapter(nid, 7)
    assert ch3.translated_text == "Tô Nhược cười. Tô Nhuận gật đầu."  # Tô Nhuận giữ nguyên
    assert ch3.translated_title == "Chương 3: Tô Nhược"
    assert ch7.translated_text == "Tô Nhược!"
    assert ch3.glossary_outdated and ch7.glossary_outdated


def test_unrelated_chapter_untouched(lib):
    nid, svc, repo = lib
    svc.set_term(nid, "苏柔", "Tô Nhược")
    ch5 = repo.get_chapter(nid, 5)
    assert ch5.translated_text == "Tô Nhu không có trong raw." and not ch5.glossary_outdated


def test_edited_chapter_labelled_only(lib):
    nid, svc, repo = lib
    svc.set_term(nid, "苏柔", "Tô Nhược")
    ch4 = repo.get_chapter(nid, 4)
    assert ch4.translated_text == "Tô Nhu tới." and ch4.glossary_outdated
    assert ch4.status == ChapterStatus.EDITED


def test_pending_chapter_untouched_and_version_bumped(lib):
    nid, svc, repo = lib
    before = repo.get_novel(nid).glossary_version
    svc.set_term(nid, "苏柔", "Tô Nhược")
    assert repo.get_novel(nid).glossary_version == before + 1
    ch6 = repo.get_chapter(nid, 6)
    assert ch6.status == ChapterStatus.PENDING and not ch6.glossary_outdated


def test_note_only_change_does_not_propagate(lib):
    nid, svc, repo = lib
    svc.set_term(nid, "苏柔", "Tô Nhu", note="nữ chính")
    assert not repo.get_chapter(nid, 3).glossary_outdated


def test_remove_term_labels_without_replacing(lib):
    nid, svc, repo = lib
    assert svc.remove_term(nid, "苏柔")
    ch3, ch4 = repo.get_chapter(nid, 3), repo.get_chapter(nid, 4)
    assert ch3.glossary_outdated and ch4.glossary_outdated
    assert ch3.translated_text == "Tô Nhu cười. Tô Nhuận gật đầu."


def test_affected_chapters_preview(lib):
    nid, svc, _ = lib
    assert [c.index for c in svc.affected_chapters(nid, "苏柔")] == [3, 4, 7]


def test_rename_is_atomic(lib, monkeypatch):
    nid, svc, repo = lib
    calls = {"n": 0}
    real = repo.update_chapter

    def flaky(ch):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("lỗi giữa chừng")
        real(ch)

    monkeypatch.setattr(repo, "update_chapter", flaky)
    with pytest.raises(RuntimeError):
        svc.set_term(nid, "苏柔", "Tô Nhược")
    monkeypatch.undo()
    # rollback toàn bộ: bộ tên, version và chương đầu tiên đều như cũ
    assert [g.target_term for g in svc.list_terms(nid)] == ["Tô Nhu"]
    assert repo.get_chapter(nid, 3).translated_text.startswith("Tô Nhu cười")
    assert not repo.get_chapter(nid, 3).glossary_outdated
    assert repo.get_novel(nid).glossary_version == 1
