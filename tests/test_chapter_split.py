"""Tách chương (spec chapter-splitting, design D1). Thuần Python, không cần DB."""

from __future__ import annotations

import pytest

from novel_translator.domain.chapter_split import (
    HeadingKind,
    classify_line,
    find_headings,
    parse_number,
    split_lines,
)

C, S, V = HeadingKind.CHAPTER, HeadingKind.SPECIAL, HeadingKind.VOLUME


@pytest.mark.parametrize("raw, value", [
    ("12", 12), ("１０", 10), ("一", 1), ("十", 10), ("十二", 12), ("二十", 20), ("两百", 200),
    ("一千零二十", 1020), ("一〇二", 102), ("三万五千", 35000), ("abc", None), ("", None),
])
def test_parse_number(raw, value):
    assert parse_number(raw) == value


def test_split_lines_normalizes_newlines():
    assert split_lines("a\r\nb\rc\nd") == ["a", "b", "c", "d"]


# --- Requirement: Chinese chapter headings ---------------------------------------------------

@pytest.mark.parametrize("line, expected", [
    ("第一章 少年", (C, 1)),
    ("第2章 修炼", (C, 2)),
    ("第１０章 突破", (C, 10)),
    ("  第一百二十回 大战  ", (C, 120)),
    ("第三节", (C, 3)),
    ("第5话 相遇", (C, 5)),
    ("Chapter 7: The Gate", (C, 7)),
    ("CHAPTER 8", (C, 8)),
    ("第一章。", (C, 1)),  # dấu câu ngay sau số
    ("楔子", (S, None)),
    ("序章 少年时", (S, None)),
    ("番外篇", (S, None)),
    ("番外一 回忆", (S, None)),
    ("尾声", (S, None)),
])
def test_chinese_headings(line, expected):
    assert classify_line(line) == expected


def test_mixed_numeral_styles_scenario():
    lines = ["第一章 少年", "正文。", "第2章 修炼", "正文。", "第１０章 突破", "正文。"]
    hs = find_headings(lines)
    assert [(h.line, h.text, h.number) for h in hs] == [
        (0, "第一章 少年", 1), (2, "第2章 修炼", 2), (4, "第１０章 突破", 10)]


def test_special_heading_scenario():
    hs = find_headings(["楔子", "很久以前。", "第一章 开始", "正文。"])
    assert [(h.line, h.kind, h.number) for h in hs] == [(0, S, None), (2, C, 1)]


# --- Requirement: Vietnamese chapter headings ------------------------------------------------

@pytest.mark.parametrize("line, expected", [
    ("Chương 1: Rồng ngẩng đầu", (C, 1)),
    ("Chương 2 - Mở cửa", (C, 2)),
    ("CHƯƠNG 3. Đi xa", (C, 3)),
    ("chương 12 — Gió nổi", (C, 12)),
    ("Chương 4", (C, 4)),
    ("Chương 5.", (C, 5)),
    ("Hồi 7: Ra núi", (C, 7)),
    ("Chương XII: Kiếm", (C, 12)),
    ("Hồi IV", (C, 4)),
    ("Mở đầu", (S, None)),
    ("Lời mở đầu", (S, None)),
    ("Phiên ngoại 2: Thời niên thiếu", (S, None)),
    ("Ngoại truyện - Tề Tĩnh Xuân", (S, None)),
    ("Vĩ thanh", (S, None)),
    ("Tiết tử", (S, None)),
])
def test_vietnamese_headings(line, expected):
    assert classify_line(line) == expected


def test_vietnamese_headings_decomposed_unicode():
    import unicodedata
    assert classify_line(unicodedata.normalize("NFD", "Chương 9: Đi xa")) == (C, 9)


def test_vietnamese_separators_scenario():
    lines = ["Chương 1: Rồng ngẩng đầu", "x", "Chương 2 - Mở cửa", "y", "CHƯƠNG 3. Đi xa", "z"]
    hs = find_headings(lines)
    assert [(h.text, h.number) for h in hs] == [
        ("Chương 1: Rồng ngẩng đầu", 1), ("Chương 2 - Mở cửa", 2), ("CHƯƠNG 3. Đi xa", 3)]


def test_chapter_end_notes_in_middle_of_file():
    lines = [
        "Chương 1: Rồng ngẩng đầu",
        "Ngày mùng hai tháng hai, dân gian gọi là “rồng ngẩng đầu”.",
        "",
        ("(3) Vỡ vỡ bình an: câu nói thường dùng khi lỡ tay làm rơi vỡ đồ vật, "
         "nhằm cầu xin đây là một điềm lành."),
        "",
        "Chương 2: Mở cửa",
        "",
        "Trời vừa tảng sáng, gà còn chưa gáy thì Trần Bình An đã rời giường.",
    ]
    assert [h.line for h in find_headings(lines)] == [0, 5]


# --- Requirement: Heading lines must stand alone ---------------------------------------------

@pytest.mark.parametrize("line", [
    "Chương này kể về việc Trần Bình An học nghề nung gốm ở trấn nhỏ.",
    "Chương mười hai",  # số bằng chữ: không hỗ trợ
    "Chương di chuyển rất nhanh",  # 'di' không phải số La Mã viết hoa
    "(3) Vỡ vỡ bình an: câu nói thường dùng khi lỡ tay làm rơi vỡ đồ vật.",
    "[3] Chú thích.",
    "3. Chú thích về tên gọi",
    "Hồi 3 rồi mà hắn vẫn chưa về.",
    "Mở đầu câu chuyện là một buổi sáng",
    "Đọc tiếp Chương 3: Ra đi",  # marker không ở đầu dòng
    "第五章" + "他" * 197,  # 200 ký tự
    "第三章写得真好。",
    "尾声渐近，众人散去",
    "序言中提到的那个人",
    "Tập luyện mỗi ngày",
    "",
    "   ",
])
def test_not_headings(line):
    assert classify_line(line) is None


# --- Volumes are recognised as their own kind ------------------------------------------------

@pytest.mark.parametrize("line, expected", [
    ("第一卷 潜龙", (V, 1)),
    ("第二部", (V, 2)),
    ("Quyển 1: Kiếm khí", (V, 1)),
    ("Tập 3", (V, 3)),
    ("Q2 - Ra biển", (V, 2)),
    ("Q.4", (V, 4)),
])
def test_volume_headings(line, expected):
    assert classify_line(line) == expected
