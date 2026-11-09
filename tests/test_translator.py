"""ChapterTranslator: một request mỗi chương, cắt đoạn khi vượt ngưỡng, sự kiện stream,
kiểm tra độ đầy đủ (spec translation-pipeline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from novel_translator.domain.models import ChainEvent, GlossaryEntry, Novel
from novel_translator.domain.ports import (
    DailyQuotaError,
    MalformedOutputError,
    StreamingProvider,
    TruncatedError,
)
from novel_translator.pipeline.sections import NameItem, Paragraph, Title
from novel_translator.pipeline.translator import ChapterTranslator, is_possible_omission
from novel_translator.providers.chain import ChainLink, ChainProvider
from novel_translator.providers.echo import EchoProvider

NOVEL = Novel(title="Vũ Động", id=1)
GLOSSARY = [GlossaryEntry(1, "林动", "Lâm Động")]


class Scripted(StreamingProvider):
    """Trả về output cố định, chia thành các mẩu nhỏ."""

    name, default_model = "scripted", "m"

    def __init__(self, *outputs: str, chunk: int = 7):
        self.outputs = list(outputs)
        self.chunk = chunk
        self.calls = []

    def stream(self, request, policy=None, on_event=None):
        self.calls.append(request)
        text = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        return (text[i:i + self.chunk] for i in range(0, len(text), self.chunk))


def paras(n: int, size: int = 10) -> str:
    return "\n".join(f"段{i:03d}" + "字" * (size - 4) for i in range(n))


def test_normal_chapter_single_request_with_title():
    src = paras(600)  # ~6.000 ký tự
    assert 5500 < len(src) < 7000
    echo = EchoProvider()
    out = ChapterTranslator(echo, 20000).translate(NOVEL, GLOSSARY, "第一章 少年", src)
    assert len(echo.calls) == 1
    assert echo.calls[0].user.startswith("<<TITLE>>\n第一章 少年\n<<BODY>>\n")
    assert "林动 → Lâm Động" in echo.calls[0].system
    assert out.title == "[VI] 第一章 少年"
    assert len(out.text.splitlines()) == 600 and not out.possible_omission


def test_long_chapter_segmented_title_on_first_only_same_system():
    src = paras(30)  # 30 đoạn × 10 ký tự
    echo = EchoProvider()
    out = ChapterTranslator(echo, 100).translate(NOVEL, GLOSSARY, "第二章", src)
    assert len(echo.calls) > 1
    assert all(len(c.user.split("<<BODY>>\n", 1)[1].strip()) <= 100 for c in echo.calls)
    assert "<<TITLE>>" in echo.calls[0].user
    assert all("<<TITLE>>" not in c.user for c in echo.calls[1:])
    assert len({c.system for c in echo.calls}) == 1  # instructions giống hệt → cache được
    assert out.text.splitlines() == [f"[VI] {p}" for p in src.splitlines()]  # giữ thứ tự


def test_events_stream_title_then_paragraphs_in_order():
    events = []
    output = "<<TITLE>>\nChương 1\n<<BODY>>\nMột.\nHai.\nBa.\n<<NAMES>>\n苏柔 | Tô Nhu | nhân vật\n"
    ChapterTranslator(Scripted(output), 20000).translate(
        NOVEL, [], "第一章", "一\n二\n三", on_event=events.append)
    assert events == [Title("Chương 1"), Paragraph("Một."), Paragraph("Hai."), Paragraph("Ba.")]


def test_names_collected_and_deduplicated_across_segments():
    outs = ["<<TITLE>>\nT\n<<BODY>>\nA\n<<NAMES>>\n苏柔 | Tô Nhu | nhân vật\n",
            "<<BODY>>\nB\n<<NAMES>>\n苏柔 | Tô Nhụ | nhân vật\n青阳镇 | Thanh Dương | địa danh\n"]
    out = ChapterTranslator(Scripted(*outs), 3).translate(NOVEL, [], "t", "一二\n三四")
    assert out.names == [NameItem("苏柔", "Tô Nhu", "nhân vật"),
                         NameItem("青阳镇", "Thanh Dương", "địa danh")]
    assert out.text == "A\nB"


def test_no_names_section_is_fine():
    out = ChapterTranslator(Scripted("<<TITLE>>\nT\n<<BODY>>\nA\n"), 100).translate(
        NOVEL, [], "t", "一")
    assert out.names == [] and out.text == "A"


def test_truncated_output_fails():
    with pytest.raises(TruncatedError):
        ChapterTranslator(EchoProvider(end_error=TruncatedError("cắt")), 20000).translate(
            NOVEL, [], "t", "一\n二")


@pytest.mark.parametrize("output", ["<<TITLE>>\nT\n<<BODY>>\n\n\n", "<<TITLE>>\nT\nkhông có body"])
def test_empty_or_missing_body_is_malformed(output):
    with pytest.raises(MalformedOutputError):
        ChapterTranslator(Scripted(output), 20000).translate(NOVEL, [], "t", "一")


def test_paragraph_mismatch_flags_possible_omission():
    body = "\n".join(f"Đoạn {i}" for i in range(35))
    out = ChapterTranslator(Scripted(f"<<BODY>>\n{body}\n"), 20000).translate(
        NOVEL, [], "t", paras(50))
    assert out.possible_omission  # 50 → 35: lệch 30% > 20%


def test_omission_threshold():
    assert not is_possible_omission(50, 40)  # lệch đúng 20% → chưa gắn cờ
    assert is_possible_omission(50, 39)
    assert is_possible_omission(10, 13)
    assert not is_possible_omission(0, 3)


def test_chain_step_and_events_recorded():
    now = datetime.now(timezone.utc)

    class Tracker:
        def exhausted_until(self, step):
            return None

        def record_success(self, step):
            pass

        def mark_exhausted(self, step, until):
            pass

        def usage_today(self):
            return []

    chain = ChainProvider(
        [ChainLink(EchoProvider(errors=[DailyQuotaError("x", now + timedelta(hours=1))],
                                name="gemini"), "chinh"),
         ChainLink(EchoProvider(name="gemini"), "nhe")], Tracker(), sleep=lambda s: None)
    events = []
    out = ChapterTranslator(chain, 20000).translate(NOVEL, [], "t", "一", on_event=events.append)
    assert (out.provider, out.model, out.chain_step) == ("gemini", "nhe", 2)
    assert isinstance(events[0], ChainEvent) and events[0].kind == "fallback_step"
