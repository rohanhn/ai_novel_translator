"""Đọc file .txt truyện Trung, tách chương theo tiêu đề kiểu 第X章 / 第X回."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CHAPTER_RE = re.compile(r"^\s*(第[0-9零一二三四五六七八九十百千万两]+[章回节卷].*)$", re.MULTILINE)


@dataclass
class TxtChapter:
    title: str
    text: str


class TxtLoader:
    def __init__(self, encoding: str | None = None):
        self.encoding = encoding

    def _read(self, path: Path) -> str:
        if self.encoding:
            return path.read_text(encoding=self.encoding)
        for enc in ("utf-8", "gb18030"):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Không đoán được encoding của {path}; dùng --encoding")

    def load(self, path: Path) -> list[TxtChapter]:
        return self.parse(self._read(path))

    @staticmethod
    def parse(content: str) -> list[TxtChapter]:
        matches = list(CHAPTER_RE.finditer(content))
        if not matches:
            return [TxtChapter(title="Chương 1", text=content.strip())] if content.strip() else []
        chapters = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            chapters.append(TxtChapter(title=m.group(1).strip(), text=content[m.end() : end].strip()))
        return chapters
