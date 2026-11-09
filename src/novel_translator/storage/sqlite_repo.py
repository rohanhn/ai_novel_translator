from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import Chapter, ChapterStatus, GlossaryEntry, Novel

SCHEMA = """
CREATE TABLE IF NOT EXISTS novels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    title TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_title TEXT,
    translated_text TEXT,
    status TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (novel_id, idx)
);
CREATE TABLE IF NOT EXISTS glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    note TEXT,
    UNIQUE (novel_id, source_term)
);
"""


class SqliteRepository:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    # --- novels ---
    def add_novel(self, novel: Novel) -> Novel:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO novels (title, source_lang, target_lang, created_at) VALUES (?,?,?,?)",
                (novel.title, novel.source_lang, novel.target_lang, novel.created_at.isoformat()),
            )
        novel.id = cur.lastrowid
        return novel

    def get_novel(self, novel_id: int) -> Novel | None:
        row = self._conn.execute("SELECT * FROM novels WHERE id=?", (novel_id,)).fetchone()
        return _novel(row) if row else None

    def list_novels(self) -> list[Novel]:
        return [_novel(r) for r in self._conn.execute("SELECT * FROM novels ORDER BY id")]

    # --- chapters ---
    def add_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        with self._lock, self._conn:
            for ch in chapters:
                cur = self._conn.execute(
                    "INSERT INTO chapters (novel_id, idx, title, source_text, status, updated_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (ch.novel_id, ch.index, ch.title, ch.source_text, ch.status.value,
                     ch.updated_at.isoformat()),
                )
                ch.id = cur.lastrowid
        return chapters

    def get_chapter(self, novel_id: int, index: int) -> Chapter | None:
        row = self._conn.execute(
            "SELECT * FROM chapters WHERE novel_id=? AND idx=?", (novel_id, index)
        ).fetchone()
        return _chapter(row) if row else None

    def list_chapters(self, novel_id: int) -> list[Chapter]:
        rows = self._conn.execute(
            "SELECT * FROM chapters WHERE novel_id=? ORDER BY idx", (novel_id,)
        )
        return [_chapter(r) for r in rows]

    def update_chapter(self, chapter: Chapter) -> None:
        chapter.updated_at = datetime.now(timezone.utc)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE chapters SET translated_title=?, translated_text=?, status=?, provider=?,"
                " model=?, updated_at=? WHERE id=?",
                (chapter.translated_title, chapter.translated_text, chapter.status.value,
                 chapter.provider, chapter.model, chapter.updated_at.isoformat(), chapter.id),
            )

    # --- glossary ---
    def upsert_glossary(self, entry: GlossaryEntry) -> GlossaryEntry:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO glossary (novel_id, source_term, target_term, note) VALUES (?,?,?,?)"
                " ON CONFLICT(novel_id, source_term) DO UPDATE SET"
                " target_term=excluded.target_term, note=excluded.note",
                (entry.novel_id, entry.source_term, entry.target_term, entry.note),
            )
        row = self._conn.execute(
            "SELECT id FROM glossary WHERE novel_id=? AND source_term=?",
            (entry.novel_id, entry.source_term),
        ).fetchone()
        entry.id = row["id"]
        return entry

    def list_glossary(self, novel_id: int) -> list[GlossaryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM glossary WHERE novel_id=? ORDER BY source_term", (novel_id,)
        )
        return [
            GlossaryEntry(id=r["id"], novel_id=r["novel_id"], source_term=r["source_term"],
                          target_term=r["target_term"], note=r["note"])
            for r in rows
        ]

    def delete_glossary(self, novel_id: int, source_term: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM glossary WHERE novel_id=? AND source_term=?", (novel_id, source_term)
            )
        return cur.rowcount > 0


def _novel(r: sqlite3.Row) -> Novel:
    return Novel(id=r["id"], title=r["title"], source_lang=r["source_lang"],
                 target_lang=r["target_lang"], created_at=datetime.fromisoformat(r["created_at"]))


def _chapter(r: sqlite3.Row) -> Chapter:
    return Chapter(
        id=r["id"], novel_id=r["novel_id"], index=r["idx"], title=r["title"],
        source_text=r["source_text"], translated_title=r["translated_title"],
        translated_text=r["translated_text"], status=ChapterStatus(r["status"]),
        provider=r["provider"], model=r["model"],
        updated_at=datetime.fromisoformat(r["updated_at"]),
    )
