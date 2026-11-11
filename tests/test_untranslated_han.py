"""Số chữ Hán còn sót được ghi theo bản dịch đang lưu (spec translation-pipeline
"Untranslated Han check", "Untranslated count follows the stored translation")."""

from __future__ import annotations

import pytest

from novel_translator.application.services import EditingService, TranslationService
from novel_translator.domain.models import Chapter, ChapterStatus, GlossaryEntry, Novel
from novel_translator.domain.ports import StreamingProvider


class Scripted(StreamingProvider):
    name, default_model = "scripted", "m-1"

    def __init__(self, output: str):
        self.output = output

    def stream(self, request, policy=None, on_event=None):
        return iter([self.output])


LEFTOVER = "<<TITLE>>\nChương 2\n<<BODY>>\nHoảng đ蕩 hoàn nhiệt.\nThảm đạm 幽 lục, một 瞬.\n<<NAMES>>\n"
CLEAN = "<<TITLE>>\nChương 2\n<<BODY>>\nRung rinh quanh mình.\nÁnh sáng u lục.\n<<NAMES>>\n"


@pytest.fixture
def setup(repo):
    novel = repo.add_novel(Novel(title="Kiếm Chúc"))
    repo.add_chapters([Chapter(novel_id=novel.id, index=2, title="第二章",
                               source_text="晃荡着环绕在周围。\n惨淡幽绿，照亮一瞬。")])

    def translate(output: str, force=False, confirm=False):
        svc = TranslationService(repo, lambda name, model: Scripted(output), 20000)
        return svc.translate_chapter(novel.id, 2, force=force, confirm_discard_edits=confirm)

    return novel, translate


def test_han_characters_left_in_the_translation(setup):
    _, translate = setup
    ch = translate(LEFTOVER)
    assert (ch.status, ch.untranslated_han) == (ChapterStatus.TRANSLATED, 3)


def test_clean_translation(setup):
    _, translate = setup
    assert translate(CLEAN).untranslated_han == 0


def test_glossary_kept_character_not_counted(setup, repo):
    novel, translate = setup
    repo.upsert_glossary(GlossaryEntry(novel.id, "幽", "u (幽)"))
    assert translate(LEFTOVER).untranslated_han == 2


def test_re_translation_clears_count(setup, repo):
    novel, translate = setup
    translate(LEFTOVER)
    translate(CLEAN, force=True)
    assert repo.get_chapter(novel.id, 2).untranslated_han == 0


def test_manual_edit_removes_the_leftovers(setup, repo):
    novel, translate = setup
    translate(LEFTOVER)
    ed = EditingService(repo)
    ch = ed.edit_chapter(novel.id, 2, None, "Rung rinh.\nU lục.")
    assert (ch.status, ch.untranslated_han) == (ChapterStatus.EDITED, 0)
    ch = ed.edit_chapter(novel.id, 2, "Chương 2 幽", "Rung rinh.\nU lục.")
    assert repo.get_chapter(novel.id, 2).untranslated_han == 1
