"""Biên tập tay (spec translation-editing)."""

from __future__ import annotations

import pytest

from novel_translator.application.jobs import TranslationJobManager
from novel_translator.application.services import (
    ConfirmationRequiredError,
    InvalidOperationError,
    NotFoundError,
)
from novel_translator.domain.models import ChapterStatus


@pytest.fixture
def ed(container, sample_txt):
    novel = container.library.import_novel(sample_txt).novel
    container.translation.translate_chapter(novel.id, 1)
    return novel.id, container


def test_save_edit(ed):
    nid, c = ed
    ch = c.editing.edit_chapter(nid, 1, "Chương 1: Thiếu niên", "Lâm Động đứng trên núi.\n")
    assert ch.status == ChapterStatus.EDITED
    stored = c.library.get_chapter(nid, 1)
    assert stored.translated_text == "Lâm Động đứng trên núi."
    assert stored.translated_title == "Chương 1: Thiếu niên"
    assert stored.status == ChapterStatus.EDITED


def test_edit_keeps_title_when_not_given(ed):
    nid, c = ed
    c.editing.edit_chapter(nid, 1, None, "Nội dung mới")
    assert c.library.get_chapter(nid, 1).translated_title == "[VI] 第一章 少年"


def test_edit_untranslated_chapter_rejected(ed):
    nid, c = ed
    with pytest.raises(InvalidOperationError):
        c.editing.edit_chapter(nid, 2, None, "gì đó")
    assert c.library.get_chapter(nid, 2).status == ChapterStatus.PENDING


def test_edit_empty_text_rejected(ed):
    nid, c = ed
    with pytest.raises(InvalidOperationError):
        c.editing.edit_chapter(nid, 1, None, "  \n ")


def test_edit_unknown_chapter(ed):
    nid, c = ed
    with pytest.raises(NotFoundError):
        c.editing.edit_chapter(nid, 99, None, "x")


def test_unconfirmed_retranslate_of_edited_rejected(ed):
    nid, c = ed
    c.editing.edit_chapter(nid, 1, None, "Bản sửa tay")
    with pytest.raises(ConfirmationRequiredError):
        c.translation.translate_chapter(nid, 1, force=True)
    ch = c.library.get_chapter(nid, 1)
    assert ch.status == ChapterStatus.EDITED and ch.translated_text == "Bản sửa tay"


def test_confirmed_retranslate_of_edited(ed):
    nid, c = ed
    c.editing.edit_chapter(nid, 1, None, "Bản sửa tay")
    ch = c.library.get_chapter(nid, 1)
    ch.glossary_outdated = True
    c.repo.update_chapter(ch)
    ch = c.translation.translate_chapter(nid, 1, force=True, confirm_discard_edits=True)
    assert ch.status == ChapterStatus.TRANSLATED
    assert ch.translated_text != "Bản sửa tay"
    assert not ch.glossary_outdated  # Spec "Label cleared on re-translation"
    assert ch.glossary_version == c.library.get_novel(nid).glossary_version


def test_edited_without_force_returns_edit_untouched(ed):
    nid, c = ed
    c.editing.edit_chapter(nid, 1, None, "Bản sửa tay")
    assert c.translation.translate_chapter(nid, 1).translated_text == "Bản sửa tay"


def test_job_submit_requires_confirmation_upfront(ed):
    nid, c = ed
    c.editing.edit_chapter(nid, 1, None, "Bản sửa tay")
    jobs = TranslationJobManager(c.translation)
    try:
        with pytest.raises(ConfirmationRequiredError):
            jobs.submit(nid, 1, force=True)
        assert jobs.get(nid, 1) is None
        job = jobs.submit(nid, 1, force=True, confirm_discard_edits=True)
        assert job.wait(5) and job.terminal_event.type == "completed"
    finally:
        jobs.shutdown()
