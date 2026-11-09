"""Thay thế bản dịch của một tên theo ranh giới từ (design D9). Thuần Python, không phụ thuộc."""

from __future__ import annotations

import re


def replace_whole_word(text: str, old: str, new: str) -> tuple[str, int]:
    """Thay `old` bằng `new` khi không có chữ cái/chữ số đứng liền trước hoặc sau (Unicode),
    phân biệt hoa thường. "Tô Nhu" trong "Tô Nhuận" không bị thay."""
    if not old or old == new:
        return text, 0
    pattern = re.compile(rf"(?<![^\W_]){re.escape(old)}(?![^\W_])")
    return pattern.subn(lambda _: new, text)
