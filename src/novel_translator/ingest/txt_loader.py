"""Đọc file .txt truyện và giải mã (UTF-8, rồi GB18030). Tách chương nằm ở
`domain/chapter_split.py` (spec `chapter-splitting`)."""

from __future__ import annotations

from pathlib import Path

ENCODINGS = ("utf-8", "gb18030")


def decode(data: bytes, encoding: str | None = None) -> str:
    """Giải mã bytes của file TXT. Bỏ BOM UTF-8 nếu có."""
    if encoding:
        return data.decode(encoding)
    for enc in ENCODINGS:
        try:
            return data.decode(enc).removeprefix("﻿")
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đoán được encoding của file; dùng --encoding")


class TxtLoader:
    def __init__(self, encoding: str | None = None):
        self.encoding = encoding

    def read_text(self, path: Path) -> str:
        try:
            return decode(path.read_bytes(), self.encoding)
        except ValueError as e:
            raise ValueError(f"Không đoán được encoding của {path}; dùng --encoding") from e
