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


# --- Requirement: Language detection ---------------------------------------------------------

def test_detect_chinese():
    from novel_translator.domain.chapter_split import detect_language
    assert detect_language("第一章 少年\n林动站在山上，看着远方的青阳镇，心中暗暗发誓一定要变强。") == "zh"


def test_detect_vietnamese():
    from novel_translator.domain.chapter_split import detect_language
    text = "Chương 2: Mở cửa\nTrời vừa tảng sáng, gà còn chưa gáy thì Trần Bình An đã rời giường."
    assert detect_language(text) == "vi"


def test_detect_vietnamese_decomposed():
    import unicodedata

    from novel_translator.domain.chapter_split import detect_language
    assert detect_language(unicodedata.normalize("NFD", "Đi đâu đấy?")) == "vi"


def test_detect_unknown_plain_latin():
    from novel_translator.domain.chapter_split import detect_language
    assert detect_language("Chapter 1\nThe quick brown fox jumps over the lazy dog.") == "unknown"
    assert detect_language("") == "unknown"
    assert detect_language("12345 ... !!!") == "unknown"


def test_detect_vietnamese_convert_with_few_han():
    """Bản convert lẫn ít chữ Hán (chú thích tên) vẫn là tiếng Việt."""
    from novel_translator.domain.chapter_split import detect_language
    text = ("Lâm Động (林动) đứng trên núi nhìn về phía trấn Thanh Dương (青阳镇), "
            "trong lòng thầm thề nhất định phải trở nên mạnh mẽ hơn bất cứ ai.")
    assert detect_language(text) == "vi"


def test_detect_uses_only_leading_sample():
    from novel_translator.domain.chapter_split import LANG_SAMPLE_CHARS, detect_language
    text = "林" * LANG_SAMPLE_CHARS + "Trần Bình An đã rời giường. " * 50_000
    assert detect_language(text) == "zh"


# --- plan()/apply() --------------------------------------------------------------------------

def _plan(text):
    from novel_translator.domain.chapter_split import plan
    return plan(text)


def _titles(p):
    return [c.title for c in p.chapters]


def test_plan_chinese_produces_chapters_in_order():
    p = _plan("第一章 少年\n正文一。\n第2章 修炼\n正文二。\n第１０章 突破\n正文三。")
    assert _titles(p) == ["第一章 少年", "第2章 修炼", "第１０章 突破"]
    assert [c.number for c in p.chapters] == [1, 2, 3]
    assert [c.heading_number for c in p.chapters] == [1, 2, 10]
    assert [c.body for c in p.chapters] == ["正文一。", "正文二。", "正文三。"]
    assert p.front_matter is None and p.warnings == []


def test_plan_special_then_chapter():
    p = _plan("楔子\n很久以前。\n第一章 开始\n正文。")
    assert _titles(p) == ["楔子", "第一章 开始"]
    assert p.chapters[0].kind is S


def test_plan_vietnamese_chapter_end_notes():
    lines = [
        "Chương 1: Rồng ngẩng đầu",
        "Ngày mùng hai tháng hai, dân gian gọi là “rồng ngẩng đầu”.",
        "",
        "(3) Vỡ vỡ bình an: câu nói thường dùng khi lỡ tay làm rơi vỡ đồ vật.",
        "",
        "Chương 2: Mở cửa",
        "",
        "Trời vừa tảng sáng, gà còn chưa gáy thì Trần Bình An đã rời giường.",
    ]
    p = _plan("\n".join(lines))
    assert _titles(p) == ["Chương 1: Rồng ngẩng đầu", "Chương 2: Mở cửa"]
    assert p.chapters[0].body.endswith("(3) Vỡ vỡ bình an: câu nói thường dùng khi lỡ tay làm rơi vỡ đồ vật.")
    assert p.chapters[1].body.startswith("Trời vừa tảng sáng")


# --- Requirement: Volume headings ------------------------------------------------------------

def test_volume_above_chapters():
    p = _plan("Quyển 1: Kiếm khí\nChương 1: Rồng ngẩng đầu\nThân chương.\nChương 2: Mở cửa\nB.")
    assert _titles(p) == ["Quyển 1: Kiếm khí · Chương 1: Rồng ngẩng đầu", "Chương 2: Mở cửa"]
    assert p.front_matter is None
    assert all("Quyển" not in c.body for c in p.chapters)


def test_volume_between_chapters_not_in_body():
    p = _plan("第一章 甲\n正文一。\n第二卷 风云\n第二章 乙\n正文二。")
    assert _titles(p) == ["第一章 甲", "第二卷 风云 · 第二章 乙"]
    assert p.chapters[0].body == "正文一。"


def test_volumes_only():
    p = _plan("第一卷\n正文一。\n第二卷\n正文二。")
    assert _titles(p) == ["第一卷", "第二卷"]
    assert [c.kind for c in p.chapters] == [V, V]


# --- Requirement: Front matter before the first heading --------------------------------------

def test_short_book_header_discarded_by_default():
    p = _plan("Kiếm Lai\nTác giả: Phong Hỏa Hí Chư Hầu\n\nChương 1: Rồng ngẩng đầu\nThân.")
    assert p.front_matter is not None and p.front_matter.keep is False
    assert p.front_matter.text == "Kiếm Lai\nTác giả: Phong Hỏa Hí Chư Hầu"
    assert _titles(p) == ["Chương 1: Rồng ngẩng đầu"]


def test_long_prologue_kept_by_default():
    prologue = "Trời đất mờ mịt, núi sông lặng im. " * 45  # ~1.500 ký tự
    p = _plan(prologue + "\nChương 1: Bắt đầu\nThân.")
    assert p.front_matter.keep is True
    assert _titles(p) == ["Mở đầu", "Chương 1: Bắt đầu"]
    assert p.chapters[0].body == prologue.strip()
    assert [c.number for c in p.chapters] == [1, 2]


def test_front_matter_override():
    from novel_translator.domain.chapter_split import apply
    text = "Kiếm Lai\nChương 1: A\nThân."
    assert _titles(apply(text, [1], keep_front_matter=True)) == ["Mở đầu", "Chương 1: A"]
    long = "x" * 300 + "\nChương 1: A\nThân."
    assert _titles(apply(long, [1], keep_front_matter=False)) == ["Chương 1: A"]


# --- Requirement: Fallback when no heading is found ------------------------------------------

def test_fallback_single_chapter_with_warning():
    p = _plan("Một đoạn văn không có tiêu đề.\nĐoạn thứ hai.")
    assert _titles(p) == ["Chương 1"]
    assert p.chapters[0].body == "Một đoạn văn không có tiêu đề.\nĐoạn thứ hai."
    assert [w.code for w in p.warnings] == ["no_headings"]


def test_empty_text_has_no_chapters():
    p = _plan("  \n\n ")
    assert p.chapters == [] and p.warnings == []


# --- Requirement: Adjustable split -----------------------------------------------------------

def _numbered(n):
    """Văn bản n dòng; dòng 1, 40, 90 là tiêu đề."""
    lines = [f"dòng {i}" for i in range(n)]
    lines[1], lines[40], lines[90] = "Chương 1: A", "Chương 2: B", "Chương 3: C"
    return "\n".join(lines)


def test_merge_by_removing_heading():
    from novel_translator.domain.chapter_split import apply
    text = _numbered(120)
    assert _plan(text).boundaries == [1, 40, 90]
    p = apply(text, [1, 90])
    assert _titles(p) == ["Chương 1: A", "Chương 3: C"]
    assert "Chương 2: B\ndòng 41" in p.chapters[0].body


def test_split_at_arbitrary_line():
    from novel_translator.domain.chapter_split import apply
    p = apply(_numbered(120), [1, 40, 60, 90])
    assert _titles(p) == ["Chương 1: A", "Chương 2: B", "dòng 60", "Chương 3: C"]
    assert p.chapters[2].kind is None and p.chapters[2].heading_number is None
    assert p.chapters[1].end_line == 60 and p.chapters[2].body.startswith("dòng 61")


@pytest.mark.parametrize("bad", [[500], [-1], [0, 2]])
def test_apply_rejects_invalid_boundaries(bad):
    from novel_translator.domain.chapter_split import apply
    with pytest.raises(ValueError):
        apply("Chương 1: A\nthân\n\nChương 2: B", bad)


def test_apply_dedupes_and_sorts():
    from novel_translator.domain.chapter_split import apply
    p = apply(_numbered(100), [90, 1, 40, 40])
    assert p.boundaries == [1, 40, 90]


# --- Cảnh báo (Requirement: Chapter number sequence / length warnings) -----------------------

def _codes(ch):
    return [w.code for w in ch.warnings]


def _body(n=150):
    return "Thân chương đủ dài. " * (n // 20 + 1)


def test_number_gap_warning():
    p = _plan(f"Chương 1\n{_body()}\nChương 2\n{_body()}\nChương 5\n{_body()}")
    assert [_codes(c) for c in p.chapters] == [[], [], ["number_gap"]]
    w = p.chapters[2].warnings[0]
    assert w.params["missing_from"] == 3 and w.params["missing_to"] == 4
    assert "3–4" in w.message


def test_number_repeat_and_decrease():
    body = "正文。" * 40
    p = _plan(f"第九章\n{body}\n第十章\n{body}\n第十章\n{body}\n第八章\n{body}")
    assert [_codes(c) for c in p.chapters] == [[], [], ["number_repeat"], ["number_decrease"]]


def test_sequence_ignores_special_volume_and_user_boundaries():
    from novel_translator.domain.chapter_split import apply
    text = f"Chương 1\n{_body()}\nPhiên ngoại 1\n{_body()}\nChương 2\n{_body()}\ndòng thường\n{_body()}"
    p = _plan(text)
    assert all(_codes(c) == [] for c in p.chapters)
    p2 = apply(text, p.boundaries + [6])  # tách tại "dòng thường": không có số → không cảnh báo
    assert all("number" not in " ".join(_codes(c)) for c in p2.chapters)


def test_too_short_warning():
    p = _plan(f"Chương 1\n{_body()}\nChương 2\nNgắn quá, chỉ ba mươi ký tự.\nChương 3\n{_body()}")
    assert [_codes(c) for c in p.chapters] == [[], ["too_short"], []]


def test_too_long_warning():
    normal = "a" * 6000
    p = _plan(f"Chương 1\n{normal}\nChương 2\n{normal}\nChương 3\n{'b' * 45000}\nChương 4\n{normal}")
    assert _codes(p.chapters[2]) == ["too_long"]
    assert p.chapters[2].warnings[0].params == {"chars": 45000, "median": 6000}
    # dài hơn 3× trung vị nhưng chưa tới 20.000 ký tự → không cảnh báo
    q = _plan(f"Chương 1\n{'a' * 2000}\nChương 2\n{'a' * 2000}\nChương 3\n{'b' * 9000}")
    assert _codes(q.chapters[2]) == []


def test_front_matter_warning_reflects_choice():
    from novel_translator.domain.chapter_split import apply
    text = f"Kiếm Lai\nChương 1\n{_body()}"
    assert [w.code for w in _plan(text).warnings] == ["front_matter"]
    assert "bỏ đi" in _plan(text).warnings[0].message
    assert "Mở đầu" in apply(text, [1], keep_front_matter=True).warnings[0].message


def test_warnings_do_not_change_split():
    p = _plan("Chương 1\nx\nChương 3\nx")
    assert len(p.chapters) == 2 and p.boundaries == [0, 2]


# --- Fixture từ file thật ---------------------------------------------------------------------

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures" / "split"


def test_fixture_vietnamese_excerpt_mid_file():
    from novel_translator.domain.chapter_split import detect_language
    text = (FIXTURES / "kiem-lai-vi.txt").read_text(encoding="utf-8")
    p = _plan(text)
    assert detect_language(text) == "vi"
    assert _titles(p) == ["Chương 1: Kinh trập", "Chương 2: Mở cửa", "Chương 3: Ngõ nhỏ"]
    assert p.front_matter is None and p.warnings == []
    ch1, ch2, ch3 = p.chapters
    assert "gọi là “rồng ngẩng đầu”." in ch1.body
    assert ch1.body.endswith("nhằm cầu xin đây là một điềm lành.")
    assert ch2.body.startswith("Trời vừa tảng sáng")
    assert "Chương này của đời hắn" in ch3.body  # câu nhắc tới "chương" không bị tách
    assert all(c.warnings == [] for c in p.chapters)


def test_fixture_chinese_raw():
    from novel_translator.domain.chapter_split import detect_language
    text = (FIXTURES / "lin-dong-zh.txt").read_text(encoding="utf-8")
    p = _plan(text)
    assert detect_language(text) == "zh"
    assert _titles(p) == ["楔子", "第一卷 潜龙 · 第一章 林动", "第二章 修炼", "第三章 石符"]
    assert p.front_matter.text == "武动乾坤\n作者：天蚕土豆" and p.front_matter.keep is False
    assert [w.code for w in p.warnings] == ["front_matter"]
    assert all(c.warnings == [] for c in p.chapters)
    assert all("第一卷" not in c.body for c in p.chapters)


# --- Hiệu năng --------------------------------------------------------------------------------

def test_plan_50mb_under_10_seconds():
    import time
    para = "Trời vừa tảng sáng, gà còn chưa gáy thì Trần Bình An đã rời giường. " * 3 + "\n"
    chapter = "Chương {n}: Tên chương\n" + para * 30
    one = len(chapter.format(n=1).encode())
    n = 50 * 1024 * 1024 // one + 1
    text = "".join(chapter.format(n=i) for i in range(1, n + 1))
    assert len(text.encode()) >= 50 * 1024 * 1024
    t0 = time.perf_counter()
    p = _plan(text)
    elapsed = time.perf_counter() - t0
    assert len(p.chapters) == n
    assert elapsed < 10, f"plan() mất {elapsed:.1f}s"
