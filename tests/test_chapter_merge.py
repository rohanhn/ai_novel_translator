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
    assert plan.anchor == cm.Anchor(500, 500, "content", zh_title(500))
    assert [c.title for c in plan.to_add] == [zh_title(n) for n in range(501, 521)]
    assert not plan.needs_start and not plan.warnings and not plan.differing


def test_file_starts_mid_novel():
    plan = cm.plan_append(stored_range(1, 500), incoming(*range(480, 521)))
    assert plan.anchor.stored_index == 500
    assert len(plan.to_add) == 20 and plan.to_add[0].title == zh_title(501)


def test_last_stored_chapter_was_a_notice_dropped_from_the_file():
    stored = stored_range(1, 10) + [cm.StoredRef(11, "请假条", "今天请假一天。")]
    plan = cm.plan_append(stored, incoming(*range(1, 14)))
    assert plan.anchor == cm.Anchor(10, 10, "content", zh_title(10))
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
    assert plan.anchor == cm.Anchor(5, 5, "title", zh_title(5))
    assert positions(plan.to_add) == [6, 7]


def test_content_match_preferred_over_title_match():
    # Chương cuối khớp nội dung ở vị trí 3 và khớp tiêu đề (lặp lại) ở vị trí 5.
    stored = stored_range(1, 3)
    plan = cm.plan_append(stored, incoming(1, 2, 3, 4, (zh_title(3), "另一个版本。"), 6))
    assert plan.anchor == cm.Anchor(3, 3, "content", zh_title(3))


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


def stored_numbers(*numbers: int) -> list[cm.StoredRef]:
    """Chương đang lưu có số chương `numbers`, index 1..n (truyện bị thiếu chương ở giữa)."""
    return [cm.StoredRef(i, zh_title(n), f"正文{n}。", "translated")
            for i, n in enumerate(numbers, start=1)]


def test_file_has_chapters_missing_from_the_middle_of_the_novel():
    plan = cm.plan_append(stored_numbers(1, 2, 3, 6, 7), incoming(*range(1, 9)))
    assert plan.anchor.stored_index == 5
    assert positions(plan.to_add) == [8]
    assert [c.title for c in plan.middle] == [zh_title(4), zh_title(5)]


def test_middle_lists_unplaced_chapters_when_start_is_needed():
    plan = cm.plan_append(stored_numbers(1, 2, 3, 6, 7), incoming(4, 5))
    assert plan.needs_start and plan.to_add == []
    assert positions(plan.middle) == [1, 2]


def test_middle_excludes_chapters_to_add_and_matched_chapters():
    plan = cm.plan_append(stored_range(1, 3), incoming(1, (zh_title(2), "改过的。"), 3, 4))
    assert positions(plan.to_add) == [4]
    assert plan.middle == []  # chương 2 khớp tiêu đề (differing), không phải chương thiếu
    assert cm.plan_append([], incoming(1, 2)).middle == []


# --- Replace ----------------------------------------------------------------------------------


def layout(plan: cm.ReplacePlan) -> list[str]:
    """Mô tả ngắn từng mục theo thứ tự mới: `reuse:3`, `changed:5`, `new@4` (vị trí file), `kept:7`."""
    out = []
    for e in plan.entries:
        if e.kind is cm.EntryKind.NEW:
            out.append(f"new@{e.incoming.position}")
        else:
            out.append(f"{e.kind.value}:{e.stored.index}")
    return out


def test_replace_identical_file_reuses_everything():
    plan = cm.plan_replace(stored_range(1, 4), incoming(1, 2, 3, 4))
    assert layout(plan) == ["reuse:1", "reuse:2", "reuse:3", "reuse:4"]
    assert plan.missing == [] and plan.count(cm.EntryKind.REUSE) == 4


def test_chapter_inserted_in_the_middle():
    side = ("番外 雪夜", "番外正文。")
    plan = cm.plan_replace(stored_range(1, 5), incoming(1, 2, 3, side, 4, 5))
    assert layout(plan) == ["reuse:1", "reuse:2", "reuse:3", "new@4", "reuse:4", "reuse:5"]
    assert plan.new_index(4) == 5


def test_author_revised_a_chapter_and_new_chapters():
    plan = cm.plan_replace(stored_range(1, 3), incoming(1, (zh_title(2), "改过的。"), 3, 4))
    assert layout(plan) == ["reuse:1", "changed:2", "reuse:3", "new@4"]
    assert plan.count(cm.EntryKind.CHANGED) == 1 and plan.count(cm.EntryKind.NEW) == 1


def test_edited_lost_counts_changed_edited_chapters_only():
    stored = [cm.StoredRef(1, zh_title(1), "正文1。", "edited"),
              cm.StoredRef(2, zh_title(2), "正文2。", "edited"),
              cm.StoredRef(3, zh_title(3), "正文3。", "translated")]
    plan = cm.plan_replace(stored, incoming(1, (zh_title(2), "新"), (zh_title(3), "新")))
    assert [s.index for s in plan.edited_lost] == [2]


def test_missing_chapter_kept_by_default_after_its_predecessor():
    stored = stored_range(1, 3) + [cm.StoredRef(4, "公告", "公告内容")] + [
        cm.StoredRef(5, zh_title(4), "正文4。")]
    plan = cm.plan_replace(stored, incoming(1, 2, 3, 4, 5))
    assert layout(plan) == ["reuse:1", "reuse:2", "reuse:3", "kept:4", "reuse:5", "new@5"]
    assert [s.index for s in plan.missing] == [4] and plan.deleted == []


def test_missing_chapter_deleted():
    stored = stored_range(1, 3) + [cm.StoredRef(4, "公告", "公告内容")]
    plan = cm.plan_replace(stored, incoming(1, 2, 3), delete={4})
    assert layout(plan) == ["reuse:1", "reuse:2", "reuse:3"]
    assert [s.index for s in plan.deleted] == [4]


def test_delete_only_accepts_missing_chapters():
    with pytest.raises(ValueError):
        cm.plan_replace(stored_range(1, 3), incoming(1, 2, 3), delete={2})


def test_kept_chapter_at_start_and_consecutive_kept():
    stored = [cm.StoredRef(1, "序", "序言"), cm.StoredRef(2, "公告", "公告")] + [
        cm.StoredRef(n + 2, zh_title(n), f"正文{n}。") for n in (1, 2)] + [
        cm.StoredRef(5, "后记A", "a"), cm.StoredRef(6, "后记B", "b")]
    plan = cm.plan_replace(stored, incoming(1, 2, 3))
    assert layout(plan) == ["kept:1", "kept:2", "reuse:3", "reuse:4", "kept:5", "kept:6", "new@3"]


def test_file_contains_only_the_missing_chapters():
    plan = cm.plan_replace(stored_numbers(1, 2, 3, 6, 7), incoming(4, 5))
    assert layout(plan) == ["kept:1", "kept:2", "kept:3", "new@1", "new@2", "kept:4", "kept:5"]
    assert plan.count(cm.EntryKind.NEW) == 2 and plan.deleted == []


def test_partial_file_around_the_gap():
    plan = cm.plan_replace(stored_numbers(1, 2, 3, 6, 7), incoming(3, 4, 5, 6))
    assert layout(plan) == ["kept:1", "kept:2", "reuse:3", "new@2", "new@3", "reuse:4", "kept:5"]


def test_missing_chapters_filled_after_the_last_match():
    plan = cm.plan_replace(stored_numbers(1, 2, 5, 6), incoming(1, 3, 4))
    assert layout(plan) == ["reuse:1", "kept:2", "new@2", "new@3", "kept:3", "kept:4"]


def test_kept_chapters_without_numbers_stay_before_new_chapters():
    stored = [cm.StoredRef(1, zh_title(1), "正文1。"), cm.StoredRef(2, "公告", "公告内容"),
              cm.StoredRef(3, "后记", "后记内容")]
    plan = cm.plan_replace(stored, incoming(1, 2, 3))
    assert layout(plan) == ["reuse:1", "kept:2", "kept:3", "new@2", "new@3"]


def test_numbering_restarts_per_volume_keeps_old_placement():
    # Chỗ sau chương 1: giữ lại 99 rồi 1 (quyển sau đánh lại số) và chương mới 50.
    stored = [cm.StoredRef(1, zh_title(1), "正文1。"), cm.StoredRef(2, zh_title(99), "卷一99"),
              cm.StoredRef(3, zh_title(1), "卷二1")]
    plan = cm.plan_replace(stored, incoming(1, (zh_title(50), "新的50")))
    assert layout(plan) == ["reuse:1", "kept:2", "kept:3", "new@2"]


def test_kept_numbers_increasing_are_merged_with_new():
    stored = stored_numbers(1) + [cm.StoredRef(2, zh_title(3), "正文3。"),
                                  cm.StoredRef(3, zh_title(5), "正文5。")]
    plan = cm.plan_replace(stored, incoming(1, 2, 4))
    assert layout(plan) == ["reuse:1", "new@2", "kept:2", "new@3", "kept:3"]


def test_reading_progress_follows_kept_chapter_after_fill():
    plan = cm.plan_replace(stored_numbers(1, 2, 3, 6, 7), incoming(4, 5))
    assert plan.remap_progress(4, 0.4) == (6, 0.4)  # đang đọc chương 6 (index cũ 4)


def test_kept_chapter_follows_predecessor_moved_elsewhere():
    # Chương 2 bị chuyển xuống cuối trong file; chương thiếu X (index 3) đi theo chương 2.
    stored = stored_range(1, 2) + [cm.StoredRef(3, "公告", "x")] + [cm.StoredRef(4, zh_title(3), "正文3。")]
    plan = cm.plan_replace(stored, incoming(1, 3, 2))
    assert layout(plan) == ["reuse:1", "reuse:4", "reuse:2", "kept:3"]


def test_two_chapters_swapped():
    plan = cm.plan_replace(stored_range(1, 3), incoming(1, 3, 2))
    assert layout(plan) == ["reuse:1", "reuse:3", "reuse:2"]


def test_duplicate_titles_in_two_volumes_match_in_order():
    stored = [cm.StoredRef(1, "第一卷 · 第1章 起", "旧A"), cm.StoredRef(2, "第2章 承", "B"),
              cm.StoredRef(3, "第二卷 · 第1章 起", "旧C")]
    plan = cm.plan_replace(stored, incoming(("第1章 起", "新A"), ("第2章 承", "B"), ("第1章 起", "新C")))
    assert layout(plan) == ["changed:1", "reuse:2", "changed:3"]


def test_duplicate_content_matches_in_order():
    notice = ("请假条", "今天请假。")
    stored = [cm.StoredRef(1, *notice), *stored_range(2, 3), cm.StoredRef(4, *notice), cm.StoredRef(5, zh_title(4), "正文4。")]
    plan = cm.plan_replace(stored, incoming(notice, 2, 3, notice, 4))
    assert layout(plan) == ["reuse:1", "reuse:2", "reuse:3", "reuse:4", "reuse:5"]


def test_content_match_wins_over_title_match():
    # File có hai chương cùng tiêu đề 2: bản đúng nội dung phải lấy chương cũ 2.
    plan = cm.plan_replace(stored_range(1, 2), incoming(1, (zh_title(2), "草稿"), 2))
    assert layout(plan) == ["reuse:1", "new@2", "reuse:2"]


# --- Reading progress follows chapters ------------------------------------------------------


def test_reading_chapter_shifted_keeps_position():
    side = ("番外 雪夜", "番外正文。")
    plan = cm.plan_replace(stored_range(1, 400), incoming(*range(1, 312), side, *range(312, 401)))
    assert plan.remap_progress(312, 0.4) == (313, 0.4)


def test_reading_chapter_deleted_moves_to_preceding_kept_chapter():
    stored = stored_range(1, 3) + [cm.StoredRef(4, "公告", "x")]
    plan = cm.plan_replace(stored, incoming(1, 2, 3), delete={4})
    assert plan.remap_progress(4, 0.7) == (3, 0.0)


def test_reading_chapter_kept_keeps_position():
    stored = stored_range(1, 2) + [cm.StoredRef(3, "公告", "x")]
    plan = cm.plan_replace(stored, incoming(1, 2, 4))
    assert plan.remap_progress(3, 0.5) == (3, 0.5)


def test_reading_chapter_changed_moves_to_previous_intact_chapter():
    plan = cm.plan_replace(stored_range(1, 3), incoming(1, (zh_title(2), "新的"), 3))
    assert plan.remap_progress(2, 0.6) == (1, 0.0)


def test_reading_first_chapter_changed_goes_to_chapter_one():
    plan = cm.plan_replace(stored_range(1, 2), incoming((zh_title(1), "新的"), 2))
    assert plan.remap_progress(1, 0.6) == (1, 0.0)


def test_reading_deleted_with_nothing_before_goes_to_chapter_one():
    stored = [cm.StoredRef(1, "公告", "x"), *[cm.StoredRef(n + 1, zh_title(n), f"正文{n}。")
                                             for n in (1, 2)]]
    plan = cm.plan_replace(stored, incoming(1, 2), delete={1})
    assert plan.remap_progress(1, 0.3) == (1, 0.0)


# --- Hiệu năng --------------------------------------------------------------------------------


def test_replace_2000_chapters_of_20kb_is_fast():
    import time

    def big(n: int) -> str:
        return (f"第{n}章的正文。" * 2500)[:20_000]

    stored = [cm.StoredRef(n, zh_title(n), big(n)) for n in range(1, 2001)]
    inc = [cm.Incoming(n, zh_title(n), big(n) if n % 50 else big(n) + "改") for n in range(1, 2011)]
    t0 = time.perf_counter()
    plan = cm.plan_replace(stored, inc)
    elapsed = time.perf_counter() - t0
    assert plan.count(cm.EntryKind.REUSE) == 1960 and plan.count(cm.EntryKind.CHANGED) == 40
    assert elapsed < 2.0, elapsed


# --- Chương có thân giống nhau, chỉ khác tiêu đề -----------------------------------------------


def _same_body(numbers, body="相同的正文。") -> list[cm.StoredRef]:
    return [cm.StoredRef(n, zh_title(n), body) for n in numbers]


def test_append_identical_bodies_anchor_by_content_and_title():
    stored = _same_body(range(1, 4))
    file = incoming(*[(zh_title(n), "相同的正文。") for n in range(1, 6)])
    plan = cm.plan_append(stored, file)
    assert plan.anchor == cm.Anchor(3, 3, "content", zh_title(3))
    assert positions(plan.to_add) == [4, 5]


def test_replace_identical_bodies_reordered_match_by_title():
    stored = _same_body(range(1, 4))
    file = incoming(*[(zh_title(n), "相同的正文。") for n in (3, 1, 2)])
    plan = cm.plan_replace(stored, file)
    assert layout(plan) == ["reuse:3", "reuse:1", "reuse:2"]
