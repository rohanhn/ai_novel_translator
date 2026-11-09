"""CLI `novel` (công cụ quản trị): translate qua chuỗi, override, báo hết quota."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from novel_translator.config import Settings
from novel_translator.container import build_container
from novel_translator.domain.ports import DailyQuotaError
from novel_translator.interfaces.cli import main as cli
from novel_translator.providers import registry
from novel_translator.providers.echo import EchoProvider

runner = CliRunner()


@pytest.fixture
def use(db, monkeypatch):
    def _use(**kw):
        c = build_container(Settings(_env_file=None, **kw), pool=db)
        monkeypatch.setattr(cli, "get_container", lambda: c)
        return c

    return _use


def _import(sample_txt) -> int:
    r = runner.invoke(cli.app, ["import", str(sample_txt)])
    assert r.exit_code == 0, r.output
    return 1


def test_translate_range_through_chain(use, sample_txt):
    use(chain="echo:model-a,echo:model-b")
    nid = _import(sample_txt)
    r = runner.invoke(cli.app, ["translate", str(nid), "1", "2"])
    assert r.exit_code == 0, r.output
    assert "✓ Chương 1: [VI] 第一章 少年 (echo/model-a)" in r.output
    assert "✓ Chương 2:" in r.output


def test_translate_provider_and_model_override(use, sample_txt):
    use()  # chuỗi Gemini mặc định, không có key → chỉ chạy được nhờ override
    nid = _import(sample_txt)
    r = runner.invoke(cli.app, ["translate", str(nid), "1", "--provider", "echo", "-m", "X"])
    assert r.exit_code == 0, r.output
    assert "(echo/X)" in r.output


def test_translate_reports_fallback_step(use, sample_txt, monkeypatch):
    reset = datetime.now(timezone.utc) + timedelta(hours=3)
    monkeypatch.setitem(registry._REGISTRY, "echo-daily", lambda s: EchoProvider(
        errors=[DailyQuotaError("hết", reset)], name="echo"))
    use(chain="echo-daily:chinh,echo:nhe")
    nid = _import(sample_txt)
    r = runner.invoke(cli.app, ["translate", str(nid), "1"])
    assert r.exit_code == 0, r.output
    assert "(echo/nhe) [bước dự phòng 2]" in r.output


def test_translate_whole_chain_exhausted(use, sample_txt, monkeypatch):
    reset = datetime.now(timezone.utc) + timedelta(hours=3)
    monkeypatch.setitem(registry._REGISTRY, "echo-out", lambda s: EchoProvider(
        errors=[DailyQuotaError("hết", reset)] * 5, name="echo"))
    c = use(chain="echo-out:a,echo-out:b")
    nid = _import(sample_txt)
    r = runner.invoke(cli.app, ["translate", str(nid), "1"])
    assert r.exit_code == 1
    assert "hết lượt hôm nay" in r.output and "Reset lúc" in r.output
    assert c.library.get_chapter(nid, 1).status.value == "pending"


def test_translate_missing_key_is_clear(use, sample_txt, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    use()
    nid = _import(sample_txt)
    r = runner.invoke(cli.app, ["translate", str(nid), "1"])
    assert r.exit_code == 1 and "GEMINI_API_KEY" in r.output
