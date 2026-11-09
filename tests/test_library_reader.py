"""Thư viện (spec novel-library), tiến độ đọc + tùy chọn đọc (spec web-reader)."""

from __future__ import annotations

import threading

import pytest

from novel_translator.application.jobs import Lane
from novel_translator.application.services import (
    ConfirmationRequiredError,
    NotFoundError,
)
from novel_translator.config import Settings
from novel_translator.container import build_container
from novel_translator.domain.models import GlossarySuggestion


def _import(c, tmp_path, name: str, n_chapters: int = 3) -> int:
    p = tmp_path / f"{name}.txt"
    p.write_text("".join(f"第{i}章 标题\n内容{i}\n" for i in range(1, n_chapters + 1)),
                 encoding="utf-8")
    novel, _ = c.library.import_novel(p)
    return novel.id


def test_recently_read_first_and_counts(container, tmp_path):
    a = _import(container, tmp_path, "a")
    b = _import(container, tmp_path, "b", 5)
    c = _import(container, tmp_path, "c")
    container.translation.translate_chapter(b, 1)
    container.translation.translate_chapter(b, 2)
    container.editing.edit_chapter(b, 2, None, "sửa")
    container.reader.save_progress(a, 2, 0.1)
    container.reader.save_progress(c, 1, 0.5)  # đọc truyện c SAU truyện a
    rows = container.library.overview()
    assert [r.novel.id for r in rows] == [c, a, b]  # chưa đọc xếp sau
    summary_b = rows[2]
    assert (summary_b.chapter_count, summary_b.translated_count) == (5, 2)
    assert summary_b.last_read_chapter is None
    assert rows[1].last_read_chapter == 2


def test_resume_reading(container, tmp_path):
    nid = _import(container, tmp_path, "pn", 15)
    assert container.reader.get_progress(nid) is None
    container.reader.save_progress(nid, 12, 0.4)
    p = container.reader.get_progress(nid)
    assert (p.chapter_index, p.position) == (12, pytest.approx(0.4))
    assert container.library.get_novel(nid).last_read_at is not None


def test_progress_validation(container, tmp_path):
    nid = _import(container, tmp_path, "x")
    with pytest.raises(NotFoundError):
        container.reader.save_progress(nid, 99, 0.1)
    with pytest.raises(ValueError):
        container.reader.save_progress(nid, 1, 1.5)
    with pytest.raises(NotFoundError):
        container.reader.get_progress(999)


def test_preferences_defaults_and_persist_across_devices(container, db):
    assert container.reader.get_preferences() == {
        "theme": "light", "font_size": 18, "line_height": 1.8, "prefetch": True}
    container.reader.set_preferences({"theme": "dark", "font_size": 20})
    laptop = build_container(Settings(provider="echo"), pool=db)  # "thiết bị khác"
    prefs = laptop.reader.get_preferences()
    assert prefs["theme"] == "dark" and prefs["font_size"] == 20 and prefs["line_height"] == 1.8


@pytest.mark.parametrize("bad", [
    {"theme": "neon"}, {"font_size": 99}, {"font_size": "18"}, {"line_height": 5},
    {"prefetch": "yes"}, {"unknown": 1}, {"font_size": True},
])
def test_preferences_validation(container, bad):
    with pytest.raises(ValueError):
        container.reader.set_preferences(bad)
    assert container.reader.get_preferences()["theme"] == "light"  # không lưu gì


def test_bamboo_theme_and_prefetch_toggle(container):
    prefs = container.reader.set_preferences({"theme": "bamboo", "prefetch": False})
    assert prefs["theme"] == "bamboo" and prefs["prefetch"] is False
    assert not container.prefetch.enabled()


def test_unconfirmed_delete_keeps_everything(container, tmp_path):
    nid = _import(container, tmp_path, "keep")
    with pytest.raises(ConfirmationRequiredError):
        container.library.delete_novel(nid)
    assert len(container.library.list_chapters(nid)) == 3


def test_delete_removes_all_data_and_cancels_pending_jobs(container, tmp_path, monkeypatch):
    nid = _import(container, tmp_path, "gone", 5)
    other = _import(container, tmp_path, "other")
    container.glossary.set_term(nid, "林动", "Lâm Động")
    container.repo.add_suggestion(GlossarySuggestion(nid, "苏柔", "Tô Nhu"))
    container.reader.save_progress(nid, 2, 0.3)

    # giữ làn background bận để job sau còn ở trạng thái chờ
    gate, started = threading.Event(), threading.Event()
    real = container.translation.translate_chapter

    def slow(novel_id, index, **kw):
        if (novel_id, index) == (other, 1):
            started.set()
            assert gate.wait(5)
        return real(novel_id, index, **kw)

    monkeypatch.setattr(container.translation, "translate_chapter", slow)
    running = container.jobs.submit(other, 1, Lane.BACKGROUND)
    assert started.wait(5)
    queued = container.jobs.submit(nid, 3, Lane.BACKGROUND)

    container.library.delete_novel(nid, confirm=True)
    assert queued.wait(1) and queued.terminal_event.type == "cancelled"
    with pytest.raises(NotFoundError):
        container.library.get_novel(nid)
    assert container.repo.list_chapters(nid) == []
    assert container.repo.list_glossary(nid) == []
    assert container.repo.list_suggestions(nid) == []
    assert container.repo.get_progress(nid) is None
    gate.set()
    assert running.wait(5)
    container.jobs.shutdown()


def test_delete_unknown_novel(container):
    with pytest.raises(NotFoundError):
        container.library.delete_novel(999, confirm=True)


def test_upload_title_defaults_to_file_name(container, tmp_path):
    nid = _import(container, tmp_path, "phamnhan")
    assert container.library.get_novel(nid).title == "phamnhan"
    assert {c.status.value for c in container.library.list_chapters(nid)} == {"pending"}
