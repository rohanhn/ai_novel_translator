"""Bộ so khớp chương khi cập nhật từ TXT (spec `chapter-update`)."""

from novel_translator.domain import chapter_merge as cm

# --- Chapter matching -----------------------------------------------------------------------


def test_whitespace_only_difference_is_content_match():
    stored = "　　他抬起头。\n\n　　风起了。\n"
    incoming = "他抬起头。\n风起了。"
    assert cm.content_key(stored) == cm.content_key(incoming)


def test_full_width_and_crlf_are_content_match():
    assert cm.content_key("ＡＢＣ１２\r\nx") == cm.content_key("ABC12\nx")


def test_different_text_is_not_content_match():
    assert cm.content_key("他抬起头。") != cm.content_key("他低下头。")


def test_numeral_style_difference_in_title_is_title_match():
    assert cm.title_key("第五百章 风起") == cm.title_key("第500章  风起") == (500, "风起")


def test_title_key_ignores_volume_prefix_and_separators():
    assert cm.title_key("第一卷 初入 · 第三章：拜师") == cm.title_key("第3章 拜师")


def test_vietnamese_title_key():
    assert cm.title_key("Chương 12: Mở cửa") == cm.title_key("chương 12 - mở cửa") == (12, "mởcửa")


def test_title_without_number():
    assert cm.title_key("番外 雪夜") == (None, "番外雪夜")
    assert cm.title_number("番外 雪夜") is None
    assert cm.title_number("第一卷 · 第七章 x") == 7


def test_different_names_same_number_are_not_title_match():
    assert cm.title_key("第五百章 风起") != cm.title_key("第五百章 云涌")
