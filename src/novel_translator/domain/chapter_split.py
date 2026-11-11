"""Tách chương cho file truyện dạng văn bản (spec `chapter-splitting`, design D1).

Thuần Python, không phụ thuộc: dùng chung cho CLI, API và màn xem trước. Đơn vị ranh giới là
số dòng (0-based) của văn bản sau khi chuẩn hóa xuống dòng về `\\n`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from .han_residue import is_han

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
    parts = heading_parts(line)
    return (parts[0], parts[1]) if parts else None


def heading_parts(line: str) -> tuple[HeadingKind, int | None, str] | None:
    """Như `classify_line`, kèm phần tên sau số/từ khóa (vd. "第五百章 风起" → "风起" có
    khoảng trắng/dấu phân cách đầu). Dùng để so khớp tiêu đề khi cập nhật chương."""
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
            return kind, None, rest
        if _ends_like_sentence(rest):
            return None
        if numbered == "vi":
            number = _vi_number(m)
        else:
            number = parse_number(m.group("num"))
        if number is None:
            return None
        return kind, number, rest
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


def detect_language(text: str) -> str:
    """`zh` khi chữ Hán ≥30% số chữ cái; không thì `vi` nếu có chữ cái đặc trưng tiếng Việt;
    còn lại `unknown`. Chỉ xét 200.000 ký tự đầu."""
    sample = unicodedata.normalize("NFC", text[:LANG_SAMPLE_CHARS])
    han = latin = 0
    vi = False
    for c in sample:
        if is_han(c):
            han += 1
        elif c.isalpha():
            latin += 1
            if not vi and c.lower() in _VI_LETTERS:
                vi = True
    letters = han + latin
    if letters and han / letters >= ZH_HAN_RATIO:
        return "zh"
    return "vi" if vi else "unknown"


# --- Kế hoạch tách ---------------------------------------------------------------------------

FRONT_MATTER_KEEP_CHARS = 200
SHORT_CHAPTER_CHARS = 100
LONG_CHAPTER_CHARS = 20_000
LONG_CHAPTER_MEDIAN_FACTOR = 3
FRONT_MATTER_TITLE = "Mở đầu"
FALLBACK_TITLE = "Chương 1"


@dataclass
class SplitWarning:
    code: str
    message: str
    params: dict


@dataclass
class SplitChapter:
    number: int  # thứ tự 1..n trong kết quả
    start_line: int
    end_line: int  # không bao gồm
    title: str
    body: str
    kind: HeadingKind | None  # None: phần mở đầu, fallback, hoặc ranh giới người dùng thêm
    heading_number: int | None  # số đọc được từ tiêu đề (để kiểm tra dãy số)
    warnings: list[SplitWarning]

    @property
    def chars(self) -> int:
        return len(self.body)


@dataclass
class FrontMatter:
    start_line: int
    end_line: int
    text: str
    keep: bool

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class SplitPlan:
    line_count: int
    boundaries: list[int]
    front_matter: FrontMatter | None
    chapters: list[SplitChapter]
    warnings: list[SplitWarning]  # cấp file


def _join(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def default_boundaries(lines: list[str]) -> list[int]:
    """Ranh giới mặc định: dòng tiêu đề chương/đặc biệt; chỉ dùng quyển khi không có chúng."""
    headings = find_headings(lines)
    chapter_like = [h.line for h in headings if h.kind is not HeadingKind.VOLUME]
    if chapter_like:
        return chapter_like
    return [h.line for h in headings]


def plan(text: str) -> SplitPlan:
    """Kết quả tách mặc định của một file."""
    lines = split_lines(text)
    return _build(lines, default_boundaries(lines), None)


def apply(text: str, boundaries: list[int], keep_front_matter: bool | None = None) -> SplitPlan:
    """Dựng lại chương từ một tập ranh giới bất kỳ (số dòng). `keep_front_matter=None` dùng
    lựa chọn mặc định (giữ khi phần mở đầu ≥200 ký tự)."""
    lines = split_lines(text)
    cleaned = sorted(set(boundaries))
    for b in cleaned:
        if not 0 <= b < len(lines):
            raise ValueError(f"Ranh giới dòng {b} nằm ngoài file ({len(lines)} dòng).")
        if not lines[b].strip():
            raise ValueError(f"Dòng {b} trống, không thể làm tiêu đề chương.")
    return _build(lines, cleaned, keep_front_matter)


def _build(lines: list[str], boundaries: list[int], keep_front: bool | None) -> SplitPlan:
    warnings: list[SplitWarning] = []
    if not boundaries:
        body = _join(lines)
        chapters = [SplitChapter(1, 0, len(lines), FALLBACK_TITLE, body, None, None, [])]
        if body:
            warnings.append(SplitWarning(
                "no_headings", "Không tìm thấy tiêu đề chương nào; cả file là một chương.", {}))
        return SplitPlan(len(lines), [], None, chapters if body else [], warnings)

    headings = {h.line: h for h in find_headings(lines)}
    has_chapter_headings = any(h.kind is not HeadingKind.VOLUME for h in headings.values())
    boundary_set = set(boundaries)
    # Dòng quyển không phải ranh giới → ghép vào tiêu đề chương kế, không nằm trong thân chương.
    volume_lines = {
        ln for ln, h in headings.items()
        if h.kind is HeadingKind.VOLUME and has_chapter_headings and ln not in boundary_set
    }

    def body_of(start: int, end: int) -> str:
        return _join([lines[i] for i in range(start, end) if i not in volume_lines])

    def volumes_in(start: int, end: int) -> list[str]:
        return [headings[i].text for i in range(start, end) if i in volume_lines]

    front = None
    front_text = body_of(0, boundaries[0])
    if front_text:
        first = next(i for i in range(boundaries[0]) if lines[i].strip() and i not in volume_lines)
        keep = len(front_text) >= FRONT_MATTER_KEEP_CHARS if keep_front is None else keep_front
        front = FrontMatter(first, boundaries[0], front_text, keep)

    chapters: list[SplitChapter] = []
    if front and front.keep:
        chapters.append(SplitChapter(1, front.start_line, front.end_line, FRONT_MATTER_TITLE,
                                     front.text, None, None, []))
    prev_end = 0
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(lines)
        title = unicodedata.normalize("NFC", lines[start].strip())
        prefix = volumes_in(prev_end, start)
        if prefix:
            title = " · ".join([*prefix, title])
        h = headings.get(start)
        chapters.append(SplitChapter(
            len(chapters) + 1, start, end, title, body_of(start + 1, end),
            h.kind if h else None, h.number if h else None, [],
        ))
        prev_end = start + 1
    if front:
        what = f'giữ làm chương "{FRONT_MATTER_TITLE}"' if front.keep else "bỏ đi"
        warnings.append(SplitWarning(
            "front_matter",
            f"Có {front.chars} ký tự trước tiêu đề đầu tiên; phần này sẽ được {what}.",
            {"chars": front.chars, "keep": front.keep},
        ))
    _sequence_warnings(chapters)
    _length_warnings(chapters)
    return SplitPlan(len(lines), boundaries, front, chapters, warnings)


def _sequence_warnings(chapters: list[SplitChapter]) -> None:
    """Số chương không bằng số trước + 1: nhảy cóc, trùng, lùi. Bỏ qua tiêu đề đặc biệt, quyển
    và ranh giới người dùng thêm (không có số)."""
    prev: int | None = None
    for ch in chapters:
        if ch.kind is not HeadingKind.CHAPTER or ch.heading_number is None:
            continue
        n = ch.heading_number
        if prev is not None:
            if n == prev:
                ch.warnings.append(SplitWarning(
                    "number_repeat", f"Trùng số chương {n} với chương trước.", {"number": n}))
            elif n < prev:
                ch.warnings.append(SplitWarning(
                    "number_decrease", f"Số chương lùi từ {prev} xuống {n}.",
                    {"previous": prev, "number": n}))
            elif n > prev + 1:
                first, last = prev + 1, n - 1
                missing = f"chương {first}" if first == last else f"các chương {first}–{last}"
                ch.warnings.append(SplitWarning(
                    "number_gap", f"Thiếu {missing} (số chương nhảy từ {prev} lên {n}).",
                    {"previous": prev, "number": n, "missing_from": first, "missing_to": last}))
        prev = n


def _length_warnings(chapters: list[SplitChapter]) -> None:
    if not chapters:
        return
    sizes = sorted(c.chars for c in chapters)
    mid = len(sizes) // 2
    median = sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2
    for ch in chapters:
        if ch.chars < SHORT_CHAPTER_CHARS:
            ch.warnings.append(SplitWarning(
                "too_short",
                f"Chương rất ngắn ({ch.chars} ký tự), có thể là dòng bị nhận nhầm thành tiêu đề.",
                {"chars": ch.chars}))
        elif ch.chars > LONG_CHAPTER_CHARS and ch.chars > LONG_CHAPTER_MEDIAN_FACTOR * median:
            ch.warnings.append(SplitWarning(
                "too_long",
                f"Chương rất dài ({ch.chars} ký tự), có thể còn tiêu đề chưa được nhận ra.",
                {"chars": ch.chars, "median": int(median)}))
