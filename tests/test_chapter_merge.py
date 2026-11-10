"""Bộ so khớp chương khi cập nhật từ TXT (spec `chapter-update`)."""

import pytest

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


# --- Helpers --------------------------------------------------------------------------------


def zh_title(n: int) -> str:
    return f"第{n}章 标题{n}"


def stored_range(lo: int, hi: int, overrides: dict | None = None) -> list[cm.StoredRef]:
    """Chương đang lưu lo..hi, index = số chương; `overrides[n] = (title, text)`."""
    out = []
    for n in range(lo, hi + 1):
        title, text = (overrides or {}).get(n, (zh_title(n), f"正文{n}。"))
        out.append(cm.StoredRef(n, title, text, "translated"))
    return out


def incoming(*items: tuple[str, str] | int) -> list[cm.Incoming]:
    """Chương trong file; số nguyên n = chương chuẩn (tiêu đề + text giống `stored_range`)."""
    out = []
    for pos, it in enumerate(items, start=1):
        title, body = (zh_title(it), f"正文{it}。") if isinstance(it, int) else it
        out.append(cm.Incoming(pos, title, body))
    return out


def positions(chs: list[cm.Incoming]) -> list[int]:
    return [c.position for c in chs]


# --- Append anchors on the last stored chapter ----------------------------------------------


def test_full_novel_re_downloaded():
    plan = cm.plan_append(stored_range(1, 500), incoming(*range(1, 521)))
    assert plan.anchor == cm.Anchor(500, 500, "content")
    assert [c.title for c in plan.to_add] == [zh_title(n) for n in range(501, 521)]
    assert not plan.needs_start and not plan.warnings and not plan.differing


def test_file_starts_mid_novel():
    plan = cm.plan_append(stored_range(1, 500), incoming(*range(480, 521)))
    assert plan.anchor.stored_index == 500
    assert len(plan.to_add) == 20 and plan.to_add[0].title == zh_title(501)


def test_last_stored_chapter_was_a_notice_dropped_from_the_file():
    stored = stored_range(1, 10) + [cm.StoredRef(11, "请假条", "今天请假一天。")]
    plan = cm.plan_append(stored, incoming(*range(1, 14)))
    assert plan.anchor == cm.Anchor(10, 10, "content")
    assert [c.title for c in plan.to_add] == [zh_title(n) for n in (11, 12, 13)]


def test_anchor_uses_last_occurrence():
    notice = ("请假条", "今天请假。")
    stored = stored_range(1, 3) + [cm.StoredRef(4, *notice)]
    plan = cm.plan_append(stored, incoming(1, notice, 2, 3, notice, 5))
    assert plan.anchor.position == 5
    assert positions(plan.to_add) == [6]


def test_anchor_by_title_when_content_changed():
    stored = stored_range(1, 5, {5: (zh_title(5), "旧的正文。")})
    plan = cm.plan_append(stored, incoming(*range(1, 8)))
    assert plan.anchor == cm.Anchor(5, 5, "title")
    assert positions(plan.to_add) == [6, 7]


def test_content_match_preferred_over_title_match():
    # Chương cuối khớp nội dung ở vị trí 3 và khớp tiêu đề (lặp lại) ở vị trí 5.
    stored = stored_range(1, 3)
    plan = cm.plan_append(stored, incoming(1, 2, 3, 4, (zh_title(3), "另一个版本。"), 6))
    assert plan.anchor == cm.Anchor(3, 3, "content")


def test_lookback_is_limited_to_five_chapters():
    # 6 chương cuối đều không có trong file, chương 1..4 có: không neo theo chương 4.
    stored = stored_range(1, 4) + [cm.StoredRef(n, f"公告{n}", f"公告内容{n}") for n in range(5, 11)]
    plan = cm.plan_append(stored, incoming(1, 2, 3, 4, 11))
    assert plan.anchor is None


# --- Append without an anchor ---------------------------------------------------------------


def test_file_contains_only_new_chapters():
    plan = cm.plan_append(stored_range(1, 500), incoming(*range(501, 521)))
    assert plan.anchor is None and not plan.needs_start and not plan.warnings
    assert len(plan.to_add) == 20


def test_gap_in_numbering():
    plan = cm.plan_append(stored_range(1, 500), incoming(*range(505, 521)))
    assert len(plan.to_add) == 16
    assert [(w.code, w.params) for w in plan.warnings] == [("gap", {"from": 501, "to": 504})]
    assert "501–504" in plan.warnings[0].message


def test_numbers_use_heading_number_of_incoming():
    inc = [cm.Incoming(1, "Tiêu đề lạ", "x", heading_number=501)]
    plan = cm.plan_append(stored_range(1, 500), inc)
    assert positions(plan.to_add) == [1]


def test_no_anchor_and_no_usable_numbers():
    stored = [cm.StoredRef(1, "Toàn văn", "abc")]
    plan = cm.plan_append(stored, incoming(("Phần hai", "def")))
    assert plan.needs_start and not plan.to_add and not plan.nothing_new


def test_no_anchor_and_lower_numbers_needs_start():
    plan = cm.plan_append(stored_range(1, 500), incoming(*[(zh_title(n), "新") for n in (3, 4)]))
    assert plan.needs_start


def test_owner_overrides_the_start_chapter():
    plan = cm.plan_append(stored_range(1, 5), incoming(*range(1, 9)), start=4)
    assert positions(plan.to_add) == [4, 5, 6, 7, 8]
    assert plan.anchor is None and not plan.needs_start


def test_start_out_of_range():
    with pytest.raises(ValueError):
        cm.plan_append(stored_range(1, 5), incoming(1, 2), start=3)


# --- Append result ---------------------------------------------------------------------------


def test_nothing_new():
    plan = cm.plan_append(stored_range(1, 10), incoming(*range(1, 11)))
    assert plan.nothing_new


def test_stored_chapters_differ_from_the_file():
    stored = stored_range(1, 10)
    file = incoming(1, 2, (zh_title(3), "作者修改过的正文。"), *range(4, 13))
    plan = cm.plan_append(stored, file)
    assert plan.anchor.stored_index == 10
    assert [s.index for s in plan.differing] == [3]


def test_differing_ignores_chapters_after_anchor():
    stored = stored_range(1, 3)
    plan = cm.plan_append(stored, incoming(1, 2, 3, (zh_title(1), "重复的标题。")))
    assert plan.differing == []
