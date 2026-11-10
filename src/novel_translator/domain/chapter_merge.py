"""So khớp chương đang lưu với chương trong file mới (spec `chapter-update`, design D1).

Thuần Python, không phụ thuộc: tính điểm nối (chế độ thêm), kết quả tải lại cả bộ và vị trí
đọc mới. Hai mức khớp:
- khớp nội dung: text gốc giống nhau sau khi bỏ khoảng trắng đầu/cuối dòng và dòng trống;
- khớp tiêu đề: cùng số chương và cùng phần tên (bỏ khoảng trắng, NFKC).
Khóa nằm trong `Keyer` để nguồn khác (vd. link URL) cắm thêm khóa định danh riêng.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from . import chapter_split

VOLUME_SEPARATOR = " · "  # chapter_split ghép tiêu đề quyển vào trước tiêu đề chương
_LEADING_SEPARATORS = ":：-–—.．、"
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class StoredRef:
    """Chương đang lưu (chỉ phần cần để so khớp)."""

    index: int
    title: str
    source_text: str
    status: str = "pending"


@dataclass(frozen=True)
class Incoming:
    """Chương trong file mới; `position` là thứ tự 1..n trong kết quả tách."""

    position: int
    title: str
    body: str
    heading_number: int | None = None


TitleKey = tuple[int | None, str]


def content_key(text: str) -> str:
    """Băm nội dung sau khi bỏ khoảng trắng đầu/cuối mỗi dòng, dòng trống, chuẩn hóa NFKC."""
    norm = unicodedata.normalize("NFKC", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [ln.strip() for ln in norm.split("\n")]
    joined = "\n".join(ln for ln in lines if ln)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _norm_name(s: str) -> str:
    s = _WS.sub("", unicodedata.normalize("NFKC", s))
    return s.lstrip(_LEADING_SEPARATORS).casefold()


def title_number(title: str) -> int | None:
    """Số chương đọc được từ tiêu đề (bỏ tiền tố quyển), None nếu không có."""
    parts = chapter_split.heading_parts(title.rsplit(VOLUME_SEPARATOR, 1)[-1])
    if parts and parts[0] is chapter_split.HeadingKind.CHAPTER:
        return parts[1]
    return None


def title_key(title: str) -> TitleKey:
    """(số chương, phần tên chuẩn hóa). Bỏ tiền tố quyển; không đọc được số → (None, cả tiêu đề)."""
    last = title.rsplit(VOLUME_SEPARATOR, 1)[-1]
    parts = chapter_split.heading_parts(last)
    if parts and parts[0] is chapter_split.HeadingKind.CHAPTER:
        return parts[1], _norm_name(parts[2])
    return None, _norm_name(last)


class Keyer:
    """Các khóa so khớp; lớp con có thể đổi cách tính (vd. thêm khóa URL chương)."""

    def content(self, text: str) -> str:
        return content_key(text)

    def title(self, title: str) -> TitleKey:
        return title_key(title)


DEFAULT_KEYER = Keyer()
