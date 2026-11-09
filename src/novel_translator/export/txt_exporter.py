from __future__ import annotations

from pathlib import Path

from ..domain.models import Chapter, ChapterStatus, Novel


class TxtExporter:
    format = "txt"

    def export(self, novel: Novel, chapters: list[Chapter], dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        blocks = [novel.title]
        for ch in sorted(chapters, key=lambda c: c.index):
            if ch.status != ChapterStatus.TRANSLATED:
                continue
            blocks.append(f"{ch.translated_title or ch.title}\n\n{ch.translated_text}")
        dest.write_text("\n\n\n".join(blocks) + "\n", encoding="utf-8")
        return dest
