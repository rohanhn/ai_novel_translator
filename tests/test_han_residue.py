"""Đếm chữ Hán còn sót trong bản dịch (spec translation-pipeline "Untranslated Han check")."""

from novel_translator.domain import chapter_split
from novel_translator.domain.han_residue import Residue, is_han, kept_chars, residue


def test_han_characters_left_in_the_translation():
    text = "hoảng đ蕩 hoàn nhiệt.\nThê quang sái hạ thảm đạm 幽 lục, chiếu lượng một 瞬."
    assert residue(None, text) == Residue(3, ("蕩", "幽", "瞬"))


def test_repeated_characters_count_each_time_but_listed_once():
    assert residue(None, "幽 và 幽 lại 幽") == Residue(3, ("幽",))


def test_clean_translation():
    assert residue("Chương 1: Hiểu mộng", "Hắn ngẩng đầu.\nGió nổi lên.") == Residue(0, ())


def test_title_is_counted():
    assert residue("Chương 2: Mộc 鸢", "Không có chữ Hán.").count == 1


def test_han_character_kept_on_purpose_by_the_glossary():
    kept = kept_chars(["Đan (丹)", "Lâm Động"])
    assert kept == frozenset({"丹"})
    assert residue(None, "Viên Đan (丹) này, 幽", kept) == Residue(1, ("幽",))


def test_chinese_punctuation_is_not_counted():
    assert residue("《Sơn Hải Kinh》", "Hắn nói，「được」。…") == Residue(0, ())


def test_extension_b_and_compatibility_characters():
    assert is_han("𠀀") and is_han("豈") and is_han("㐀")
    assert not is_han("《") and not is_han("ă") and not is_han("A")


def test_empty_inputs():
    assert residue(None, None) == Residue(0, ())


def test_language_detection_still_uses_han():
    assert chapter_split.detect_language("第一章 少年\n林动站在山顶，望着远方。" * 10) == "zh"
