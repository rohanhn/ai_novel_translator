"""Nối ChainProvider trong container + override provider/model từ CLI (spec llm-providers)."""

from __future__ import annotations

import pytest

from novel_translator.config import Settings
from novel_translator.container import build_container
from novel_translator.domain.models import ChapterStatus
from novel_translator.domain.ports import ProviderConfigError
from novel_translator.providers.chain import ChainProvider


@pytest.fixture
def make(db, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for var in ("NT_PROVIDER", "NT_MODEL", "NT_CHAIN"):
        monkeypatch.delenv(var, raising=False)

    def _make(**kw):
        return build_container(Settings(_env_file=None, **kw), pool=db)

    return _make


def _import(c, sample_txt):
    novel = c.library.import_novel(sample_txt).novel
    return novel


def test_default_factory_is_chain_sharing_one_provider_instance(make):
    c = make(chain="echo:model-a,echo:model-b")
    p = c.provider_factory(None, None)
    assert isinstance(p, ChainProvider)
    assert [link.model for link in p.links] == ["model-a", "model-b"]
    assert p.links[0].provider is p.links[1].provider  # một instance / một key
    assert c.provider_factory(None, None) is p


def test_translation_goes_through_chain_and_counts_usage(make, sample_txt):
    c = make(chain="echo:model-a,echo:model-b")
    novel = _import(c, sample_txt)
    ch = c.translation.translate_chapter(novel.id, 1)
    assert ch.status == ChapterStatus.TRANSLATED
    assert (ch.provider, ch.model) == ("echo", "model-a")
    usage = c.quota.usage_today()
    assert [u.step for u in usage] == [1] and usage[0].requests >= 1


def test_model_override(make, sample_txt):
    # Spec "Model override": chuỗi đã cấu hình, admin truyền --model X → dùng X.
    c = make(chain="echo:model-a,echo:model-b")
    novel = _import(c, sample_txt)
    ch = c.translation.translate_chapter(novel.id, 1, model="X")
    assert ch.model == "X"


def test_select_provider_per_request_bypasses_chain(make, sample_txt):
    # Spec "Select provider per request": chuỗi mặc định là Gemini (chưa có key), nhưng
    # --provider echo dịch được mà không đụng tới chuỗi.
    c = make()
    novel = _import(c, sample_txt)
    ch = c.translation.translate_chapter(novel.id, 1, provider="echo")
    assert ch.provider == "echo" and ch.status == ChapterStatus.TRANSLATED
    assert c.quota.usage_today() == []  # không qua chuỗi → không đếm lượt chuỗi


def test_missing_key_reported_at_first_translation(make, sample_txt):
    c = make()  # chuỗi Gemini mặc định, không có GEMINI_API_KEY
    novel = _import(c, sample_txt)
    with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY"):
        c.translation.translate_chapter(novel.id, 1)
    # lỗi cấu hình xảy ra trước khi bắt đầu dịch: chương không bị đánh dấu failed
    assert c.library.get_chapter(novel.id, 1).status == ChapterStatus.PENDING


def test_env_provider_override(make, sample_txt):
    c = make(provider="echo", model="m-dev")
    novel = _import(c, sample_txt)
    ch = c.translation.translate_chapter(novel.id, 1)
    assert (ch.provider, ch.model) == ("echo", "m-dev")


def test_unknown_provider_lists_available(make, sample_txt):
    c = make()
    novel = _import(c, sample_txt)
    with pytest.raises(ValueError, match="gemini"):
        c.translation.translate_chapter(novel.id, 1, provider="nope")
