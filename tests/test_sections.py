"""Prompt 3 phần + SectionParser streaming."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_translator.domain.models import GlossaryEntry, Novel
from novel_translator.domain.ports import MalformedOutputError
from novel_translator.pipeline.prompts import (
    BODY,
    NAMES,
    TITLE,
    build_system_prompt,
    build_user_prompt,
)
from novel_translator.pipeline.sections import (
    NameItem,
    Names,
    Paragraph,
    SectionParser,
    Title,
    parse_name_line,
)

FULL = (
    "<<TITLE>>\nChương 1: Lâm Động\n\n<<BODY>>\n"
    "Lâm Động đứng trên đỉnh núi.\n\nHắn siết chặt nắm đấm.\n"
    "<<NAMES>>\n林动 | Lâm Động | nhân vật\n青阳镇 | trấn Thanh Dương | địa danh"
)
EXPECTED = [
    Title("Chương 1: Lâm Động"),
    Paragraph("Lâm Động đứng trên đỉnh núi."),
    Paragraph("Hắn siết chặt nắm đấm."),
    Names([NameItem("林动", "Lâm Động", "nhân vật"),
           NameItem("青阳镇", "trấn Thanh Dương", "địa danh")]),
]


def parse(chunks) -> list:
    p = SectionParser()
    events = []
    for c in chunks:
        events.extend(p.feed(c))
    events.extend(p.finish())
    return events


def test_parse_whole_text():
    assert parse([FULL]) == EXPECTED


def test_cut_at_every_position_gives_same_events():
    for i in range(len(FULL) + 1):
        assert parse([FULL[:i], FULL[i:]]) == EXPECTED, f"cắt tại {i}"


def test_char_by_char_and_paragraphs_emitted_incrementally():
    p = SectionParser()
    seen = []
    for ch in FULL:
        seen.extend(p.feed(ch))
    # đoạn văn được phát ngay khi dòng hoàn chỉnh, trước khi luồng kết thúc
    assert [e for e in seen if isinstance(e, Paragraph)] == EXPECTED[1:3]
    seen.extend(p.finish())
    assert seen == EXPECTED


def test_missing_names_section():
    text = "<<TITLE>>\nTiêu đề\n<<BODY>>\nĐoạn một.\nĐoạn hai."
    for i in range(len(text) + 1):
        assert parse([text[:i], text[i:]]) == [
            Title("Tiêu đề"), Paragraph("Đoạn một."), Paragraph("Đoạn hai."), Names([])]


def test_missing_body_is_malformed():
    for text in ("<<TITLE>>\nChỉ có tiêu đề", "Không theo định dạng gì cả", ""):
        with pytest.raises(MalformedOutputError):
            parse([text])


def test_cut_inside_marker_without_body_still_malformed():
    with pytest.raises(MalformedOutputError):
        parse(["<<TITLE>>\nT\n<<BO"])  # luồng đứt giữa dấu mốc


def test_body_without_title_and_preamble_ignored():
    text = "Đây là bản dịch:\n<<BODY>>\nMột.\r\nHai.\r\n"
    assert parse([text]) == [Paragraph("Một."), Paragraph("Hai."), Names([])]


def test_marker_with_inline_content_and_spaces():
    text = "<< TITLE >> Chương 2\n<<BODY>>Đoạn A\nĐoạn B\n<<NAMES>>\n苏柔｜Tô Nhu｜nhân vật\n"
    assert parse([text]) == [
        Title("Chương 2"), Paragraph("Đoạn A"), Paragraph("Đoạn B"),
        Names([NameItem("苏柔", "Tô Nhu", "nhân vật")])]


def test_name_line_parsing():
    assert parse_name_line("- 苏柔 | Tô Nhu") == NameItem("苏柔", "Tô Nhu", None)
    assert parse_name_line("chỉ một cột") is None
    assert parse_name_line(" | Tô Nhu | x") is None


def test_parser_on_real_gemini_stream_fixture():
    chunks = [c["text"] for c in json.loads(
        (Path(__file__).parent / "fixtures/gemini_stream/ok_three_sections.json").read_text())]
    events = parse(chunks)
    assert isinstance(events[0], Title)
    assert any(isinstance(e, Paragraph) for e in events)
    assert events[-1].items and events[-1].items[0].source == "林动"


# ---------- prompt ----------


def test_system_prompt_format_example_and_glossary():
    novel = Novel(title="t")
    glossary = [GlossaryEntry(1, "青阳镇", "Thanh Dương trấn"), GlossaryEntry(1, "林动", "Lâm Động")]
    system = build_system_prompt(novel, glossary)
    for marker in (TITLE, BODY, NAMES):
        assert marker in system
    assert "林动 → Lâm Động" in system and "Ví dụ" in system
    # ổn định (không phụ thuộc thứ tự glossary) để provider cache được
    assert system == build_system_prompt(novel, list(reversed(glossary)))


def test_user_prompt_title_only_on_first_segment():
    assert build_user_prompt("内容", "第一章") == "<<TITLE>>\n第一章\n<<BODY>>\n内容\n"
    assert build_user_prompt("内容") == "<<BODY>>\n内容\n"
