"""Thông tin truyện sửa được (tên, tác giả, giới thiệu) và ảnh bìa: luật thuần, không phụ thuộc gì.

Spec novel-library "Edit novel details", "Novel details validation"; design D1, D4.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

TITLE_MAX: Final = 200
AUTHOR_MAX: Final = 100
DESCRIPTION_MAX: Final = 2000

COVER_MAX_BYTES: Final = 10 * 1024 * 1024
COVER_MAX_SIZE: Final = (600, 900)  # khung tối đa (rộng, cao)
COVER_URL_MAX: Final = 2000

DETAIL_FIELDS: Final = ("title", "author", "description")


class Unset:
    """Giá trị "không gửi" (khác với gửi rỗng = xoá trường). Chỉ dùng instance `UNSET`."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Final = Unset()


class NovelDetailsError(ValueError):
    """Giá trị không hợp lệ cho một trường thông tin truyện."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


class InvalidImageError(ValueError):
    """File không phải ảnh JPG/PNG/WebP đọc được, hoặc vượt giới hạn an toàn."""


class CoverFetchError(ValueError):
    """Không lấy được ảnh từ link. `reason`: invalid_url, blocked_address, download_failed,
    too_large."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class CoverImage:
    """Ảnh bìa đã xử lý (thu nhỏ, mã hoá lại, không metadata)."""

    mime: str
    data: bytes
    width: int
    height: int


_SPACES = re.compile(r"\s+")


def _one_line(value: str) -> str:
    return _SPACES.sub(" ", unicodedata.normalize("NFC", value)).strip()


def _multi_line(value: str) -> str:
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def normalize_details(
    *,
    title: str | None | Unset = UNSET,
    author: str | None | Unset = UNSET,
    description: str | None | Unset = UNSET,
) -> dict[str, str | None]:
    """Chuẩn hoá các trường được gửi (bỏ qua `UNSET`) và kiểm tra giới hạn.

    - Tên: một dòng, bắt buộc, 1–200 ký tự.
    - Tác giả: một dòng, ≤100 ký tự; rỗng hoặc `None` → `None` (xoá).
    - Giới thiệu: giữ xuống dòng (`\\r\\n` → `\\n`), ≤2000 ký tự; rỗng hoặc `None` → `None`.

    Độ dài đếm theo ký tự Unicode sau NFC và trim. Lỗi → `NovelDetailsError(field, message)`.
    """
    out: dict[str, str | None] = {}
    if not isinstance(title, Unset):
        t = _one_line(title or "")
        if not t:
            raise NovelDetailsError("title", "Tên truyện không được để trống.")
        if len(t) > TITLE_MAX:
            raise NovelDetailsError("title", f"Tên truyện tối đa {TITLE_MAX} ký tự.")
        out["title"] = t
    if not isinstance(author, Unset):
        a = _one_line(author or "")
        if len(a) > AUTHOR_MAX:
            raise NovelDetailsError("author", f"Tên tác giả tối đa {AUTHOR_MAX} ký tự.")
        out["author"] = a or None
    if not isinstance(description, Unset):
        d = _multi_line(description or "")
        if len(d) > DESCRIPTION_MAX:
            raise NovelDetailsError(
                "description", f"Giới thiệu tối đa {DESCRIPTION_MAX} ký tự."
            )
        out["description"] = d or None
    return out
