"""GlossaryService: versioning + hàng chờ đề xuất tên (spec glossary)."""

from __future__ import annotations

import pytest

from novel_translator.application.services import NotFoundError
from novel_translator.domain.models import GlossarySuggestion, Novel, SuggestionStatus


@pytest.fixture
def g(container, repo):
    novel = repo.add_novel(Novel(title="t"))
    return novel.id, container.glossary, repo


def version(repo, nid):
    return repo.get_novel(nid).glossary_version


def test_version_bump_on_add_change_remove(g):
    nid, svc, repo = g
    svc.set_term(nid, "林动", "Lâm Động")
    svc.set_term(nid, "青阳镇", "Thanh Dương trấn")
    svc.set_term(nid, "苏柔", "Tô Nhu")
    assert version(repo, nid) == 3
    svc.set_term(nid, "柳岩", "Liễu Nham")  # Spec "Version bump": 3 → 4
    assert version(repo, nid) == 4
    svc.set_term(nid, "柳岩", "Liễu Nham")  # không đổi gì → không tăng
    assert version(repo, nid) == 4
    svc.set_term(nid, "柳岩", "Liễu Nhạn")
    assert version(repo, nid) == 5
    assert svc.remove_term(nid, "柳岩") and version(repo, nid) == 6
    assert not svc.remove_term(nid, "柳岩") and version(repo, nid) == 6


def test_set_term_validation(g):
    nid, svc, _ = g
    with pytest.raises(ValueError):
        svc.set_term(nid, " ", "x")
    with pytest.raises(NotFoundError):
        svc.set_term(999, "a", "b")


def _suggest(repo, nid, src="苏柔", tgt="Tô Nhu"):
    repo.add_suggestion(GlossarySuggestion(nid, src, tgt, "nhân vật"))


def test_accept_suggestion(g):
    nid, svc, repo = g
    _suggest(repo, nid)
    svc.accept_suggestion(nid, "苏柔")
    assert [(e.source_term, e.target_term) for e in svc.list_terms(nid)] == [("苏柔", "Tô Nhu")]
    assert svc.list_suggestions(nid) == []
    assert version(repo, nid) == 1


def test_accept_with_edit(g):
    nid, svc, repo = g
    _suggest(repo, nid)
    svc.accept_suggestion(nid, "苏柔", "Tô Nhược")
    assert [(e.source_term, e.target_term) for e in svc.list_terms(nid)] == [("苏柔", "Tô Nhược")]


def test_dismiss_keeps_record_and_leaves_queue(g):
    nid, svc, repo = g
    _suggest(repo, nid)
    _suggest(repo, nid, "青阳镇", "Thanh Dương")
    svc.dismiss_suggestion(nid, "苏柔")
    assert [s.source_term for s in svc.list_suggestions(nid)] == ["青阳镇"]
    assert repo.get_suggestion(nid, "苏柔").status == SuggestionStatus.DISMISSED
    assert svc.list_terms(nid) == [] and version(repo, nid) == 0
    with pytest.raises(NotFoundError):
        svc.accept_suggestion(nid, "苏柔")  # đã bỏ qua thì không còn trong hàng chờ


def test_unknown_suggestion(g):
    nid, svc, _ = g
    with pytest.raises(NotFoundError):
        svc.dismiss_suggestion(nid, "不存在")
