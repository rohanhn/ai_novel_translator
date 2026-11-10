"""Parser streaming cho output 3 phần `<<TITLE>>` / `<<BODY>>` / `<<NAMES>>` (design D1).

Nhận các mẩu text tùy ý (có thể cắt ngang dòng hoặc ngang dấu mốc) và phát sự kiện:
- `Title(text)` khi phần TITLE kết thúc,
- `Paragraph(text)` mỗi khi một dòng BODY hoàn chỉnh (dòng trống bị bỏ qua),
- `Names(items)` ở cuối luồng (có thể rỗng nếu thiếu phần NAMES).
Thiếu phần BODY → `MalformedOutputError` khi `finish()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..domain.ports import MalformedOutputError
from .prompts import BODY, NAMES, TITLE

_MARKER_RE = re.compile(r"^\s*<<\s*(TITLE|BODY|NAMES)\s*>>\s*(.*)$")


@dataclass(frozen=True)
class NameItem:
    source: str
    target: str
    category: str | None = None


@dataclass(frozen=True)
class Title:
    text: str


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class Names:
    items: list[NameItem] = field(default_factory=list)


Event = Title | Paragraph | Names


def parse_name_line(line: str) -> NameItem | None:
    parts = [p.strip() for p in re.split(r"[|｜]", line.strip().lstrip("-*• ").strip())]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    category = parts[2] if len(parts) > 2 and parts[2] else None
    return NameItem(parts[0], parts[1], category)


class SectionParser:
    def __init__(self) -> None:
        self._buf = ""
        self._section: str | None = None  # None = trước dấu mốc đầu tiên (bỏ qua)
        self._title_lines: list[str] = []
        self._title_emitted = False
        self._names: list[NameItem] = []
        self.saw_body = False
        self.title: str | None = None
        self.paragraphs: list[str] = []
        self._finished = False

    def feed(self, chunk: str) -> list[Event]:
        self._buf += chunk
        events: list[Event] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            events.extend(self._line(line))
        return events

    def finish(self) -> list[Event]:
        if self._finished:
            return []
        self._finished = True
        events: list[Event] = []
        if self._buf:
            line, self._buf = self._buf, ""
            events.extend(self._line(line))
        events.extend(self._close_title())
        if not self.saw_body:
            raise MalformedOutputError(
                f"Output của model thiếu phần {BODY} (sai định dạng)."
            )
        events.append(Names(list(self._names)))
        return events

    # --- nội bộ ---
    def _line(self, line: str) -> list[Event]:
        line = line.rstrip("\r")
        m = _MARKER_RE.match(line)
        if m:
            events = self._close_title()
            self._section = {"TITLE": TITLE, "BODY": BODY, "NAMES": NAMES}[m.group(1)]
            if self._section == BODY:
                self.saw_body = True
            rest = m.group(2)
            if rest.strip():
                events.extend(self._content(rest))
            return events
        return self._content(line)

    def _content(self, line: str) -> list[Event]:
        if self._section == TITLE:
            if line.strip():
                self._title_lines.append(line.strip())
        elif self._section == BODY:
            text = line.strip()
            if text:
                self.paragraphs.append(text)
                return [Paragraph(text)]
        elif self._section == NAMES:
            item = parse_name_line(line) if line.strip() else None
            if item:
                self._names.append(item)
        return []

    def _close_title(self) -> list[Event]:
        if self._section == TITLE and not self._title_emitted and self._title_lines:
            self._title_emitted = True
            self.title = " ".join(self._title_lines)
            return [Title(self.title)]
        return []
