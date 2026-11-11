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


# --- API và CLI (task 4.1) ---------------------------------------------------------------------


def test_api_lists_count_and_detail_lists_chars(api_client, container):
    repo = container.repo
    novel = repo.add_novel(Novel(title="Kiếm Chúc"))
    repo.add_chapters([Chapter(novel_id=novel.id, index=1, title="第一章", source_text="幽")])
    repo.upsert_glossary(GlossaryEntry(novel.id, "丹", "Đan (丹)"))
    ch = repo.get_chapter(novel.id, 1)
    ch.translated_title, ch.translated_text = "Chương 1", "Thảm đạm 幽 lục 瞬, Đan (丹) 幽."
    ch.status, ch.untranslated_han = ChapterStatus.TRANSLATED, 3
    repo.update_chapter(ch)

    summary = api_client.get(f"/api/novels/{novel.id}/chapters").json()[0]
    assert summary["untranslated_han"] == 3
    detail = api_client.get(f"/api/novels/{novel.id}/chapters/1").json()
    assert detail["untranslated_chars"] == ["幽", "瞬"]  # 丹 do bộ tên giữ

    r = api_client.put(f"/api/novels/{novel.id}/chapters/1",
                       json={"translated_text": "Thảm đạm u lục."})
    assert r.status_code == 200, r.text
    assert (r.json()["untranslated_han"], r.json()["untranslated_chars"]) == (0, [])


def test_cli_chapters_and_translate_show_flag(db, monkeypatch, sample_txt):
    from typer.testing import CliRunner

    from novel_translator.config import Settings
    from novel_translator.container import build_container
    from novel_translator.interfaces.cli import main as cli

    c = build_container(Settings(_env_file=None, provider="echo"), pool=db)
    monkeypatch.setattr(cli, "get_container", lambda: c)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["import", str(sample_txt)]).exit_code == 0
    r = runner.invoke(cli.app, ["translate", "1", "1"])
    assert r.exit_code == 0, r.output
    n = c.repo.get_chapter(1, 1).untranslated_han
    assert n > 0  # provider echo giữ nguyên chữ Hán
    assert f"còn {n} chữ chưa dịch" in r.output
    r = runner.invoke(cli.app, ["chapters", "1"])
    assert f"[còn {n} chữ chưa dịch]" in r.output.splitlines()[0]
