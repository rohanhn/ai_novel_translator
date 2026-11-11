"""Chữ Hán còn sót trong bản dịch (spec translation-pipeline "Untranslated Han check").

Thuần Python, không phụ thuộc. Dùng chung cho lúc dịch, sửa tay, API (tô sáng) và đối chiếu
migration. Chữ Hán có trong bản dịch của bộ tên (glossary) không bị tính: người dùng chủ
động giữ chữ đó (design D1, loại theo chữ chứ không theo vị trí).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def is_han(c: str) -> bool:
    """CJK Unified Ideographs, Ext A, Ext B và Compatibility. Dấu câu CJK không phải chữ Hán."""
    o = ord(c)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x2A6DF
            or 0xF900 <= o <= 0xFAFF)


def kept_chars(glossary_targets: Iterable[str]) -> frozenset[str]:
    """Các chữ Hán xuất hiện trong bản dịch của bộ tên."""
    return frozenset(c for t in glossary_targets for c in t if is_han(c))


@dataclass(frozen=True)
class Residue:
    count: int  # số chữ Hán còn sót (tính cả lặp lại)
    chars: tuple[str, ...]  # chữ riêng biệt, theo thứ tự xuất hiện


NONE = Residue(0, ())


def residue(title: str | None, text: str | None,
            kept: frozenset[str] = frozenset()) -> Residue:
    """Chữ Hán còn trong tiêu đề và nội dung đã dịch, trừ các chữ thuộc `kept`."""
    count = 0
    seen: dict[str, None] = {}
    for part in (title or "", text or ""):
        for c in part:
            if is_han(c) and c not in kept:
                count += 1
                seen.setdefault(c, None)
    return Residue(count, tuple(seen))
