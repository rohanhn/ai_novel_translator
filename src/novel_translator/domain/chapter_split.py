"""Tách chương cho file truyện dạng văn bản (spec `chapter-splitting`, design D1).

Thuần Python, không phụ thuộc: dùng chung cho CLI, API và màn xem trước. Đơn vị ranh giới là
số dòng (0-based) của văn bản sau khi chuẩn hóa xuống dòng về `\\n`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

MAX_HEADING_CHARS = 80

# Dấu kết câu: dòng kết thúc bằng các dấu này không phải tiêu đề (trừ khi dấu đứng ngay sau số).
_SENTENCE_END = "。！？.!?…"
_SEPARATORS = ":：-–—.．、"


class HeadingKind(str, Enum):
    CHAPTER = "chapter"  # có số chương, tham gia kiểm tra dãy số
    SPECIAL = "special"  # mở đầu, phiên ngoại...: không có số
    VOLUME = "volume"  # quyển/tập


@dataclass(frozen=True)
class Heading:
    line: int
    kind: HeadingKind
    number: int | None
    text: str


def split_lines(text: str) -> list[str]:
    """Chuẩn hóa xuống dòng (`\\r\\n`, `\\r` → `\\n`) rồi tách dòng."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


# --- Số --------------------------------------------------------------------------------------

_ZH_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
              "七": 7, "八": 8, "九": 9}
_ZH_UNITS = {"十": 10, "百": 100, "千": 1000}
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ROMAN_RE = re.compile(r"^C{0,3}(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def _zh_number(s: str) -> int | None:
    """Số Hán: 一千零二十, 两百, 十二, 一〇二 (đọc từng chữ số khi không có đơn vị)."""
    if not any(c in _ZH_UNITS or c == "万" for c in s):
        if all(c in _ZH_DIGITS for c in s):
            return int("".join(str(_ZH_DIGITS[c]) for c in s))
        return None
    total, section, digit = 0, 0, None
    for c in s:
        if c in _ZH_DIGITS:
            digit = _ZH_DIGITS[c]
        elif c in _ZH_UNITS:
            section += (1 if digit is None else digit) * _ZH_UNITS[c]
            digit = None
        elif c == "万":
            total += (section + (digit or 0)) * 10000
            section, digit = 0, None
        else:
            return None
    return total + section + (digit or 0)


def _roman_number(s: str) -> int | None:
    """Số La Mã viết hoa, tối đa 399 (không nhận D/M để tránh nhầm chữ thường như 'di')."""
    if not s or not _ROMAN_RE.match(s):
        return None
    value = 0
    for i, c in enumerate(s):
        v = _ROMAN[c]
        value += -v if i + 1 < len(s) and _ROMAN[s[i + 1]] > v else v
    return value


def parse_number(s: str) -> int | None:
    """Chữ số Ả Rập (half/full-width), số Hán hoặc số La Mã viết hoa → int."""
    s = s.strip()
    ascii_digits = unicodedata.normalize("NFKC", s)
    if ascii_digits.isdigit() and ascii_digits.isascii():
        return int(ascii_digits)
    return _zh_number(s) if s else None


# --- Mẫu tiêu đề ----------------------------------------------------------------------------

_NUM_ZH = r"[0-9０-９零〇一二三四五六七八九十百千万两]+"
_ROMAN_CHARS = r"[IVXLC]+"

_ZH_CHAPTER = re.compile(rf"^第\s*(?P<num>{_NUM_ZH})\s*[章回节话節話](?P<rest>.*)$")
_ZH_VOLUME = re.compile(rf"^第\s*(?P<num>{_NUM_ZH})\s*[卷部](?P<rest>.*)$")
_EN_CHAPTER = re.compile(r"^chapter\s+(?P<num>\d+)(?P<rest>(?:[\s:：\-–—.].*)?)$", re.IGNORECASE)
_ZH_SPECIAL = re.compile(r"^(?:序章|序言|楔子|引子|尾声|后记|番外)(?P<rest>.*)$")

# Tiếng Việt: từ khóa không phân biệt hoa thường; số La Mã phải viết hoa.
_VI_NUM = rf"(?P<num>\d+|{_ROMAN_CHARS})"
_VI_REST = r"(?P<rest>(?:[\s:：\-–—.].*)?)"
_VI_CHAPTER = re.compile(rf"^(?i:chương|hồi)\s+{_VI_NUM}{_VI_REST}$")
_VI_VOLUME = re.compile(rf"^(?:(?i:quyển|tập)\s+{_VI_NUM}|Q\.?\s*(?P<qnum>\d+)){_VI_REST}$")
_VI_SPECIAL = re.compile(
    r"^(?i:lời mở đầu|mở đầu|tiết tử|phiên ngoại|ngoại truyện|vĩ thanh)(?P<rest>.*)$"
)


def _zh_special_rest_ok(rest: str) -> bool:
    """Sau 序章/番外...: trống, khoảng trắng hoặc dấu phân cách + tiêu đề, hoặc viết liền 篇/số
    (番外篇, 番外一). Văn xuôi tiếng Trung không có khoảng trắng, nên "尾声渐近" bị loại."""
    if not rest.strip() or rest[0].isspace() or rest[0] in _SEPARATORS:
        return True
    return bool(re.match(r"[篇0-9０-９零〇一二三四五六七八九十百两]", rest))


def _vi_special_rest_ok(rest: str) -> bool:
    """Sau "Mở đầu"/"Phiên ngoại"...: trống, dấu phân cách + tiêu đề, hoặc số. Tránh nhận câu
    văn như "Mở đầu câu chuyện là..." làm tiêu đề."""
    stripped = rest.strip()
    if not stripped:
        return True
    if not rest[0].isspace() and rest[0] not in _SEPARATORS:
        return False  # dính liền chữ phía sau
    return stripped[0] in _SEPARATORS or bool(re.match(rf"(?:\d|{_ROMAN_CHARS}\b)", stripped))


def _ends_like_sentence(rest: str) -> bool:
    """Kết thúc bằng dấu câu, trừ trường hợp dấu đứng ngay sau số (vd. "Chương 1.", "第一章。")."""
    tail = rest.rstrip()
    if not tail or tail[-1] not in _SENTENCE_END:
        return False
    return bool(tail.strip(_SENTENCE_END + " "))


def _vi_number(m: re.Match) -> int | None:
    raw = m.group("qnum") if "qnum" in m.re.groupindex and m.group("qnum") else m.group("num")
    return int(raw) if raw.isdigit() else _roman_number(raw)


def classify_line(line: str) -> tuple[HeadingKind, int | None] | None:
    """Trả về (loại, số) nếu dòng là tiêu đề đứng riêng, ngược lại None."""
    text = unicodedata.normalize("NFC", line.strip())
    if not text or len(text) > MAX_HEADING_CHARS:
        return None
    for pattern, kind, numbered in (
        (_ZH_CHAPTER, HeadingKind.CHAPTER, "zh"),
        (_ZH_VOLUME, HeadingKind.VOLUME, "zh"),
        (_EN_CHAPTER, HeadingKind.CHAPTER, "ar"),
        (_VI_CHAPTER, HeadingKind.CHAPTER, "vi"),
        (_VI_VOLUME, HeadingKind.VOLUME, "vi"),
        (_ZH_SPECIAL, HeadingKind.SPECIAL, "zh"),
        (_VI_SPECIAL, HeadingKind.SPECIAL, "vi"),
    ):
        m = pattern.match(text)
        if not m:
            continue
        rest = m.group("rest") or ""
        if kind is HeadingKind.SPECIAL:
            rest_ok = _zh_special_rest_ok if numbered == "zh" else _vi_special_rest_ok
            if not rest_ok(rest) or _ends_like_sentence(rest):
                return None
            return kind, None
        if _ends_like_sentence(rest):
            return None
        if numbered == "vi":
            number = _vi_number(m)
        else:
            number = parse_number(m.group("num"))
        if number is None:
            return None
        return kind, number
    return None


def find_headings(lines: list[str]) -> list[Heading]:
    """Mọi dòng tiêu đề (chương, đặc biệt, quyển) theo thứ tự xuất hiện."""
    found: list[Heading] = []
    for i, line in enumerate(lines):
        result = classify_line(line)
        if result:
            kind, number = result
            found.append(Heading(i, kind, number, unicodedata.normalize("NFC", line.strip())))
    return found


# --- Ngôn ngữ --------------------------------------------------------------------------------

LANG_SAMPLE_CHARS = 200_000
ZH_HAN_RATIO = 0.3
# Chữ cái chỉ có trong tiếng Việt (sau NFC): ă â đ ê ô ơ ư và các nguyên âm mang dấu thanh.
_VI_LETTERS = set(
    "ăâđêôơư"
    "àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
)


def _is_han(c: str) -> bool:
    o = ord(c)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x2A6DF
            or 0xF900 <= o <= 0xFAFF)


def detect_language(text: str) -> str:
    """`zh` khi chữ Hán ≥30% số chữ cái; không thì `vi` nếu có chữ cái đặc trưng tiếng Việt;
    còn lại `unknown`. Chỉ xét 200.000 ký tự đầu."""
    sample = unicodedata.normalize("NFC", text[:LANG_SAMPLE_CHARS])
    han = latin = 0
    vi = False
    for c in sample:
        if _is_han(c):
            han += 1
        elif c.isalpha():
            latin += 1
            if not vi and c.lower() in _VI_LETTERS:
                vi = True
    letters = han + latin
    if letters and han / letters >= ZH_HAN_RATIO:
        return "zh"
    return "vi" if vi else "unknown"
