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


# --- import: tách chương, ngôn ngữ, cảnh báo (spec novel-library) ----------------------------

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures" / "split"


def test_import_vietnamese_fixture(use):
    c = use(provider="echo")
    r = runner.invoke(cli.app, ["import", str(FIXTURES / "kiem-lai-vi.txt"), "--title", "Kiếm Lai"])
    assert r.exit_code == 0, r.output
    assert "3 chương (bản dịch có sẵn, đọc ngay)" in r.output
    assert "Cảnh báo" not in r.output
    novel = c.library.list_novels()[0]
    assert novel.title == "Kiếm Lai" and novel.pretranslated


def test_import_chinese_fixture_prints_warnings(use):
    c = use(provider="echo")
    r = runner.invoke(cli.app, ["import", str(FIXTURES / "lin-dong-zh.txt")])
    assert r.exit_code == 0, r.output
    assert "4 chương (raw tiếng Trung, cần dịch)" in r.output
    assert "trước tiêu đề đầu tiên" in r.output  # phần đầu file (tên truyện, tác giả)
    assert not c.library.list_novels()[0].pretranslated


def test_import_lang_override(use):
    c = use(provider="echo")
    r = runner.invoke(cli.app, ["import", str(FIXTURES / "kiem-lai-vi.txt"), "--lang", "zh"])
    assert r.exit_code == 0, r.output
    assert "raw tiếng Trung" in r.output
    assert not c.library.list_novels()[0].pretranslated


def test_import_unknown_language_warns(use, tmp_path):
    use(provider="echo")
    p = tmp_path / "en.txt"
    p.write_text("Chapter 1\n" + "Hello there. " * 20 + "\nChapter 3\n" + "Bye. " * 30)
    r = runner.invoke(cli.app, ["import", str(p)])
    assert r.exit_code == 0, r.output
    assert "không nhận diện được ngôn ngữ" in r.output
    assert "chương 2 'Chapter 3'" in r.output and "Thiếu chương 2" in r.output


def test_import_invalid_lang_and_empty_file(use, tmp_path):
    c = use(provider="echo")
    r = runner.invoke(cli.app, ["import", str(FIXTURES / "kiem-lai-vi.txt"), "--lang", "en"])
    assert r.exit_code == 1 and "--lang" in r.output
    p = tmp_path / "empty.txt"
    p.write_text("\n\n")
    r = runner.invoke(cli.app, ["import", str(p)])
    assert r.exit_code == 1
    assert c.library.list_novels() == []


# --- edit-novel-details 3.2: novel edit ---------------------------------------------------

def test_edit_author_keeps_title_and_list_shows_author(use, sample_txt):
    use = use(provider="echo")
    runner.invoke(cli.app, ["import", str(sample_txt)])
    nid = use.library.list_novels()[0].id
    r = runner.invoke(cli.app, ["edit", str(nid), "--author", "Phong Hỏa Hí Chư Hầu"])
    assert r.exit_code == 0, r.output
    n = use.library.get_novel(nid)
    assert (n.title, n.author) == ("sample", "Phong Hỏa Hí Chư Hầu")
    r = runner.invoke(cli.app, ["list"])
    assert f"#{nid}\tsample\tPhong Hỏa Hí Chư Hầu\tzh→vi" in r.output
    # "" xoá tác giả; giới thiệu giữ xuống dòng
    r = runner.invoke(cli.app, ["edit", str(nid), "--author", "", "--description", "A\nB"])
    assert r.exit_code == 0, r.output
    n = use.library.get_novel(nid)
    assert (n.author, n.description) == (None, "A\nB")
    assert f"#{nid}\tsample\t-\tzh→vi" in runner.invoke(cli.app, ["list"]).output


def test_edit_without_option_fails(use, sample_txt):
    use = use(provider="echo")
    runner.invoke(cli.app, ["import", str(sample_txt)])
    nid = use.library.list_novels()[0].id
    r = runner.invoke(cli.app, ["edit", str(nid)])
    assert r.exit_code != 0 and "ít nhất một" in r.output


def test_edit_invalid_or_unknown_novel_fails(use, sample_txt):
    use = use(provider="echo")
    runner.invoke(cli.app, ["import", str(sample_txt)])
    nid = use.library.list_novels()[0].id
    r = runner.invoke(cli.app, ["edit", str(nid), "--title", "   ", "--author", "X"])
    assert r.exit_code != 0 and "Tên truyện không được để trống" in r.output
    assert use.library.get_novel(nid).author is None
    r = runner.invoke(cli.app, ["edit", "999", "--title", "X"])
    assert r.exit_code != 0 and "Không có truyện" in r.output


# --- chapter-update: novel import --into -------------------------------------------------------


def _zh_file(tmp_path, name, numbers):
    p = tmp_path / name
    p.write_text("\n".join(f"第{n}章 标题{n}\n" + f"林动第{n}章的正文。" * 5 for n in numbers),
                 encoding="utf-8")
    return p


def test_cli_append(use, tmp_path):
    c = use(provider="echo")
    r = runner.invoke(cli.app, ["import", str(_zh_file(tmp_path, "a.txt", range(1, 6)))])
    assert r.exit_code == 0, r.output
    nid = c.library.list_novels()[0].id
    r = runner.invoke(cli.app, ["import", str(_zh_file(tmp_path, "b.txt", range(1, 26))),
                                "--into", str(nid)])
    assert r.exit_code == 0, r.output
    assert "sau chương 5 '第5章 标题5'" in r.output and "Đã thêm 20 chương" in r.output
    assert len(c.repo.list_chapters(nid)) == 25
    assert len(c.library.list_novels()) == 1


def test_cli_cannot_place_the_file(use, tmp_path):
    c = use(provider="echo")
    runner.invoke(cli.app, ["import", str(_zh_file(tmp_path, "a.txt", range(1, 6)))])
    nid = c.library.list_novels()[0].id
    odd = tmp_path / "odd.txt"
    odd.write_text("番外 一\n番外内容一\n番外 二\n番外内容二", encoding="utf-8")
    r = runner.invoke(cli.app, ["import", str(odd), "--into", str(nid)])
    assert r.exit_code == 1 and "web" in r.output
    assert len(c.repo.list_chapters(nid)) == 5


def test_cli_append_nothing_new_and_unknown_novel(use, tmp_path):
    c = use(provider="echo")
    f = _zh_file(tmp_path, "a.txt", range(1, 4))
    runner.invoke(cli.app, ["import", str(f)])
    nid = c.library.list_novels()[0].id
    r = runner.invoke(cli.app, ["import", str(f), "--into", str(nid)])
    assert r.exit_code == 1 and "không có chương mới" in r.output
    r = runner.invoke(cli.app, ["import", str(f), "--into", "999999"])
    assert r.exit_code == 1
    r = runner.invoke(cli.app, ["import", str(f), "--into", str(nid), "--lang", "zh"])
    assert r.exit_code == 1
