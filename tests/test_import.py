"""Import TXT: tách chương, ngôn ngữ, truyện bản dịch có sẵn (spec novel-library)."""

from __future__ import annotations

import pytest

from novel_translator.application.services import InvalidOperationError
from novel_translator.domain.models import IMPORT_PROVIDER, ChapterStatus

VI = "Chương 1: Rồng ngẩng đầu\n" + "Trần Bình An ngồi trước cửa. " * 8 + \
    "\nChương 2: Mở cửa\n" + "Trời vừa tảng sáng, gà còn chưa gáy. " * 8


def _write(tmp_path, name, text, enc="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(enc))
    return p


def test_chinese_file_pending_chapters(container, sample_txt):
    res = container.library.import_novel(sample_txt)
    assert (res.lang, res.detected_lang, res.chapters) == ("zh", "zh", 2)
    assert not res.novel.pretranslated
    chs = container.library.list_chapters(res.novel.id)
    assert [c.status for c in chs] == [ChapterStatus.PENDING] * 2
    assert all(c.translated_text is None for c in chs)


def test_vietnamese_file_is_pretranslated(container, tmp_path):
    res = container.library.import_novel(_write(tmp_path, "kiemlai.txt", VI))
    assert (res.lang, res.chapters) == ("vi", 2)
    novel = container.library.get_novel(res.novel.id)
    assert novel.pretranslated and novel.source_lang == "vi"
    assert novel.title == "kiemlai"
    chs = container.library.list_chapters(novel.id)
    assert [c.status for c in chs] == [ChapterStatus.TRANSLATED] * 2
    assert [c.translated_title for c in chs] == ["Chương 1: Rồng ngẩng đầu", "Chương 2: Mở cửa"]
    assert chs[1].translated_text.startswith("Trời vừa tảng sáng")
    assert chs[1].translated_text == chs[1].source_text
    assert {(c.provider, c.model, c.chain_step) for c in chs} == {(IMPORT_PROVIDER, None, None)}
    assert {c.glossary_version for c in chs} == {novel.glossary_version}


def test_language_override(container, tmp_path):
    res = container.library.import_novel(_write(tmp_path, "a.txt", VI), lang="zh")
    assert (res.lang, res.detected_lang) == ("zh", "vi")
    assert not res.novel.pretranslated
    chs = container.library.list_chapters(res.novel.id)
    assert {c.status for c in chs} == {ChapterStatus.PENDING}


def test_unknown_language_defaults_to_zh(container, tmp_path):
    res = container.library.import_novel(_write(tmp_path, "a.txt", "Chapter 1\nHello there.\n"))
    assert (res.lang, res.detected_lang) == ("zh", "unknown")


def test_unsupported_language_rejected(container, tmp_path):
    with pytest.raises(InvalidOperationError):
        container.library.import_novel(_write(tmp_path, "a.txt", VI), lang="en")
    assert container.library.list_novels() == []


def test_file_without_headings_single_chapter_with_warning(container, tmp_path):
    res = container.library.import_novel(_write(tmp_path, "a.txt", "Một đoạn văn.\nĐoạn hai."))
    assert res.chapters == 1
    assert [w.code for w in res.plan.warnings] == ["no_headings"]
    ch = container.library.get_chapter(res.novel.id, 1)
    assert ch.source_text == "Một đoạn văn.\nĐoạn hai."


def test_empty_file_rejected(container, tmp_path):
    with pytest.raises(ValueError):
        container.library.import_novel(_write(tmp_path, "a.txt", "  \n\n"))
    assert container.library.list_novels() == []


def test_import_text_with_adjusted_plan(container):
    from novel_translator.domain import chapter_split
    p = chapter_split.apply(VI, [0])  # bỏ ranh giới chương 2 → gộp
    res = container.library.import_text(VI, "gop", plan=p)
    assert res.chapters == 1
    body = container.library.get_chapter(res.novel.id, 1).translated_text
    assert "Chương 2: Mở cửa" in body


def test_gb18030_chinese_file(container, tmp_path):
    p = _write(tmp_path, "gbk.txt", "第一章 少年\n林动站在山上。\n", enc="gb18030")
    res = container.library.import_novel(p)
    assert res.lang == "zh"
    assert container.library.get_chapter(res.novel.id, 1).title == "第一章 少年"
