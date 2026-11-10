"""TranslationService (spec translation-pipeline + glossary suggestions), dùng provider giả."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.application.services import TranslationService
from novel_translator.domain.models import (
    Chapter,
    ChapterStatus,
    GlossaryEntry,
    Novel,
    SuggestionStatus,
)
from novel_translator.domain.ports import (
    DailyQuotaError,
    RateQuotaError,
    RefusalError,
    StreamingProvider,
    TruncatedError,
)
from novel_translator.providers.echo import EchoProvider


class Scripted(StreamingProvider):
    name, default_model = "scripted", "m-1"

    def __init__(self, output: str, errors=()):
        self.output = output
        self.errors = list(errors)
        self.calls = 0

    def stream(self, request, policy=None, on_event=None):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return iter([self.output])


OUT = ("<<TITLE>>\nChương 4\n<<BODY>>\nTô Nhu mỉm cười.\nLâm Động gật đầu.\n"
       "<<NAMES>>\n苏柔 | Tô Nhu | nhân vật\n林动 | Lâm Động | nhân vật\n")


@pytest.fixture
def setup(repo):
    novel = repo.add_novel(Novel(title="Vũ Động"))
    repo.add_chapters([Chapter(novel_id=novel.id, index=4, title="第四章",
                               source_text="苏柔微微一笑。\n林动点了点头。")])
    repo.upsert_glossary(GlossaryEntry(novel.id, "林动", "Lâm Động"))
    repo.bump_glossary_version(novel.id)
    repo.bump_glossary_version(novel.id)  # bộ tên đang ở version 2

    def make(provider):
        return TranslationService(repo, lambda name, model: provider, 20000)

    return novel, make


def test_successful_translation_records_everything(setup, repo):
    novel, make = setup
    ch = make(Scripted(OUT)).translate_chapter(novel.id, 4)
    assert ch.status == ChapterStatus.TRANSLATED
    assert ch.translated_title == "Chương 4"
    assert ch.translated_text == "Tô Nhu mỉm cười.\nLâm Động gật đầu."
    assert (ch.provider, ch.model, ch.glossary_version) == ("scripted", "m-1", 2)
    assert not ch.possible_omission and not ch.glossary_outdated
    stored = repo.get_chapter(novel.id, 4)
    assert stored.glossary_version == 2 and stored.status == ChapterStatus.TRANSLATED


def test_new_name_queued_existing_term_not(setup, repo):
    novel, make = setup
    p = Scripted(OUT)
    make(p).translate_chapter(novel.id, 4)
    assert p.calls == 1  # không có request riêng để trích tên
    pending = repo.list_suggestions(novel.id, SuggestionStatus.PENDING)
    assert [(s.source_term, s.target_term, s.category) for s in pending] == [
        ("苏柔", "Tô Nhu", "nhân vật")]  # 林动 đã có trong bộ tên → không đề xuất


def test_dismissed_term_not_resuggested(setup, repo):
    novel, make = setup
    make(Scripted(OUT)).translate_chapter(novel.id, 4)
    repo.set_suggestion_status(novel.id, "苏柔", SuggestionStatus.DISMISSED)
    make(Scripted(OUT.replace("苏柔 | Tô Nhu", "苏柔 | Tô Nhụ"))).translate_chapter(
        novel.id, 4, force=True)
    s = repo.get_suggestion(novel.id, "苏柔")
    assert s.status == SuggestionStatus.DISMISSED and s.target_term == "Tô Nhu"
    assert repo.list_suggestions(novel.id, SuggestionStatus.PENDING) == []


@pytest.mark.parametrize("status", [ChapterStatus.TRANSLATED, ChapterStatus.EDITED])
def test_already_translated_or_edited_no_llm_call(setup, repo, status):
    novel, make = setup
    ch = repo.get_chapter(novel.id, 4)
    ch.status, ch.translated_text = status, "có sẵn"
    repo.update_chapter(ch)
    p = Scripted(OUT)
    got = make(p).translate_chapter(novel.id, 4)
    assert p.calls == 0 and got.translated_text == "có sẵn"


@pytest.mark.parametrize("err", [RefusalError("r"), TruncatedError("t")])
def test_provider_failure_marks_failed_without_partial(setup, repo, err):
    novel, make = setup
    with pytest.raises(type(err)):
        make(EchoProvider(end_error=err)).translate_chapter(novel.id, 4)
    ch = repo.get_chapter(novel.id, 4)
    assert ch.status == ChapterStatus.FAILED and ch.translated_text is None


def test_malformed_output_marks_failed(setup, repo):
    novel, make = setup
    with pytest.raises(Exception, match="BODY"):
        make(Scripted("không theo định dạng")).translate_chapter(novel.id, 4)
    assert repo.get_chapter(novel.id, 4).status == ChapterStatus.FAILED


@pytest.mark.parametrize("err", [
    DailyQuotaError("hết", reset_at=datetime.now(timezone.utc) + timedelta(hours=5)),
    RateQuotaError("chậm"),
])
def test_quota_exhausted_stays_pending(setup, repo, err):
    novel, make = setup
    with pytest.raises(type(err)):
        make(Scripted(OUT, errors=[err])).translate_chapter(novel.id, 4)
    assert repo.get_chapter(novel.id, 4).status == ChapterStatus.PENDING
    assert repo.list_suggestions(novel.id) == []


def test_quota_on_forced_retranslate_keeps_existing_translation(setup, repo):
    novel, make = setup
    make(Scripted(OUT)).translate_chapter(novel.id, 4)
    with pytest.raises(DailyQuotaError):
        make(Scripted(OUT, errors=[DailyQuotaError("x")])).translate_chapter(
            novel.id, 4, force=True)
    ch = repo.get_chapter(novel.id, 4)
    assert ch.status == ChapterStatus.TRANSLATED and ch.translated_text


def test_retranslation_clears_outdated_flag(setup, repo):
    novel, make = setup
    make(Scripted(OUT)).translate_chapter(novel.id, 4)
    ch = repo.get_chapter(novel.id, 4)
    ch.glossary_outdated = True
    repo.update_chapter(ch)
    again = make(Scripted(OUT)).translate_chapter(novel.id, 4, force=True)
    assert not again.glossary_outdated
