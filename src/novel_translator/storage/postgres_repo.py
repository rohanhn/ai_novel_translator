"""Repository PostgreSQL. Mỗi thao tác mượn một kết nối từ pool, chạy trong một transaction."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..domain.models import (
    Chapter,
    ChapterStatus,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    NovelSummary,
    ReadingProgress,
    SuggestionStatus,
)
from ..domain.novel_details import DETAIL_FIELDS, CoverImage


class PostgresRepository:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self._local = threading.local()

    @contextmanager
    def unit_of_work(self) -> Iterator[None]:
        """Gom mọi thao tác trong khối (cùng thread) vào một kết nối + một transaction."""
        if getattr(self._local, "conn", None) is not None:
            yield  # lồng nhau: dùng transaction ngoài
            return
        with self.pool.connection() as conn, conn.transaction():
            self._local.conn = conn
            try:
                yield
            finally:
                self._local.conn = None

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            yield conn
        else:
            with self.pool.connection() as conn:
                yield conn

    def _one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self._connection() as conn:
            return conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._connection() as conn:
            return conn.execute(sql, params).fetchall()

    def _rowcount(self, sql: str, params: tuple = ()) -> int:
        with self._connection() as conn:
            return conn.execute(sql, params).rowcount

    # --- novels ---
    def add_novel(self, novel: Novel) -> Novel:
        row = self._one(
            "INSERT INTO novels (title, source_lang, target_lang, created_at, author, description)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, glossary_version",
            (novel.title, novel.source_lang, novel.target_lang, novel.created_at,
             novel.author, novel.description),
        )
        novel.id, novel.glossary_version = row["id"], row["glossary_version"]
        return novel

    def get_novel(self, novel_id: int) -> Novel | None:
        row = self._one("SELECT * FROM novels WHERE id = %s", (novel_id,))
        return _novel(row) if row else None

    def list_novels(self) -> list[Novel]:
        return [_novel(r) for r in self._all("SELECT * FROM novels ORDER BY id")]

    def library_overview(self) -> list[NovelSummary]:
        """Thư viện: đọc gần nhất lên đầu; truyện chưa đọc xếp sau, mới thêm trước."""
        rows = self._all(
            "SELECT n.*,"
            " (SELECT count(*) FROM chapters c WHERE c.novel_id = n.id) AS chapter_count,"
            " (SELECT count(*) FROM chapters c WHERE c.novel_id = n.id"
            "   AND c.status IN ('translated', 'edited')) AS translated_count,"
            " p.chapter_index AS last_read_chapter"
            " FROM novels n LEFT JOIN reading_progress p ON p.novel_id = n.id"
            " ORDER BY n.last_read_at DESC NULLS LAST, n.created_at DESC, n.id DESC"
        )
        return [NovelSummary(_novel(r), r["chapter_count"], r["translated_count"],
                             r["last_read_chapter"]) for r in rows]

    def delete_novel(self, novel_id: int) -> bool:
        """Xóa truyện; FK ON DELETE CASCADE xóa sạch chương, bộ tên, đề xuất, tiến độ."""
        return self._rowcount("DELETE FROM novels WHERE id = %s", (novel_id,)) > 0

    def touch_novel_read(self, novel_id: int) -> None:
        self._rowcount("UPDATE novels SET last_read_at = now() WHERE id = %s", (novel_id,))

    def bump_glossary_version(self, novel_id: int) -> int:
        row = self._one(
            "UPDATE novels SET glossary_version = glossary_version + 1 WHERE id = %s"
            " RETURNING glossary_version",
            (novel_id,),
        )
        if not row:
            raise LookupError(f"Không có truyện id={novel_id}")
        return row["glossary_version"]

    # --- chapters ---
    def add_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        with self._connection() as conn:
            _insert_chapters(conn, chapters)
        return chapters

    def replace_chapters(self, novel_id: int, chapters: list[Chapter]) -> list[Chapter]:
        """Thay toàn bộ chương của truyện (xóa rồi chèn lại) trong một transaction. Không bảng
        nào tham chiếu `chapters.id` nên đổi id không ảnh hưởng dữ liệu khác."""
        if any(ch.novel_id != novel_id for ch in chapters):
            raise ValueError("Mọi chương phải thuộc truyện đang thay.")
        with self.unit_of_work(), self._connection() as conn:
            conn.execute("DELETE FROM chapters WHERE novel_id = %s", (novel_id,))
            _insert_chapters(conn, chapters)
        return chapters

    def get_chapter(self, novel_id: int, index: int) -> Chapter | None:
        row = self._one(
            "SELECT * FROM chapters WHERE novel_id = %s AND idx = %s", (novel_id, index)
        )
        return _chapter(row) if row else None

    def list_chapters(self, novel_id: int) -> list[Chapter]:
        rows = self._all("SELECT * FROM chapters WHERE novel_id = %s ORDER BY idx", (novel_id,))
        return [_chapter(r) for r in rows]

    def update_chapter(self, chapter: Chapter) -> None:
        row = self._one(
            "UPDATE chapters SET translated_title = %s, translated_text = %s, status = %s,"
            " provider = %s, model = %s, chain_step = %s, glossary_version = %s,"
            " glossary_outdated = %s, possible_omission = %s, updated_at = now()"
            " WHERE id = %s RETURNING updated_at",
            (chapter.translated_title, chapter.translated_text, chapter.status.value,
             chapter.provider, chapter.model, chapter.chain_step, chapter.glossary_version,
             chapter.glossary_outdated, chapter.possible_omission, chapter.id),
        )
        if row:
            chapter.updated_at = row["updated_at"]

    def chapters_with_source_term(self, novel_id: int, term: str) -> list[Chapter]:
        rows = self._all(
            "SELECT * FROM chapters WHERE novel_id = %s AND strpos(source_text, %s) > 0"
            " ORDER BY idx",
            (novel_id, term),
        )
        return [_chapter(r) for r in rows]

    def reset_translating(self) -> int:
        """Lúc khởi động: job trong bộ nhớ đã mất, đưa chương `translating` về `pending`."""
        return self._rowcount(
            "UPDATE chapters SET status = 'pending', updated_at = now()"
            " WHERE status = 'translating'"
        )

    # --- glossary ---
    def upsert_glossary(self, entry: GlossaryEntry) -> GlossaryEntry:
        row = self._one(
            "INSERT INTO glossary (novel_id, source_term, target_term, note)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (novel_id, source_term) DO UPDATE SET"
            " target_term = EXCLUDED.target_term, note = EXCLUDED.note"
            " RETURNING id",
            (entry.novel_id, entry.source_term, entry.target_term, entry.note),
        )
        entry.id = row["id"]
        return entry

    def list_glossary(self, novel_id: int) -> list[GlossaryEntry]:
        rows = self._all(
            "SELECT * FROM glossary WHERE novel_id = %s ORDER BY source_term", (novel_id,)
        )
        return [
            GlossaryEntry(id=r["id"], novel_id=r["novel_id"], source_term=r["source_term"],
                          target_term=r["target_term"], note=r["note"])
            for r in rows
        ]

    def delete_glossary(self, novel_id: int, source_term: str) -> bool:
        return self._rowcount(
            "DELETE FROM glossary WHERE novel_id = %s AND source_term = %s",
            (novel_id, source_term),
        ) > 0

    # --- glossary suggestions ---
    def add_suggestion(self, suggestion: GlossarySuggestion) -> bool:
        """Thêm đề xuất; đã có (kể cả đã dismiss) thì giữ nguyên. Trả True nếu thêm mới."""
        return self._rowcount(
            "INSERT INTO glossary_suggestions (novel_id, source_term, target_term, category,"
            " status, created_at) VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (novel_id, source_term) DO NOTHING",
            (suggestion.novel_id, suggestion.source_term, suggestion.target_term,
             suggestion.category, suggestion.status.value, suggestion.created_at),
        ) > 0

    def list_suggestions(
        self, novel_id: int, status: SuggestionStatus | None = None
    ) -> list[GlossarySuggestion]:
        if status is None:
            rows = self._all(
                "SELECT * FROM glossary_suggestions WHERE novel_id = %s"
                " ORDER BY created_at, source_term",
                (novel_id,),
            )
        else:
            rows = self._all(
                "SELECT * FROM glossary_suggestions WHERE novel_id = %s AND status = %s"
                " ORDER BY created_at, source_term",
                (novel_id, status.value),
            )
        return [_suggestion(r) for r in rows]

    def get_suggestion(self, novel_id: int, source_term: str) -> GlossarySuggestion | None:
        row = self._one(
            "SELECT * FROM glossary_suggestions WHERE novel_id = %s AND source_term = %s",
            (novel_id, source_term),
        )
        return _suggestion(row) if row else None

    def set_suggestion_status(
        self, novel_id: int, source_term: str, status: SuggestionStatus
    ) -> bool:
        return self._rowcount(
            "UPDATE glossary_suggestions SET status = %s WHERE novel_id = %s AND source_term = %s",
            (status.value, novel_id, source_term),
        ) > 0

    def delete_suggestion(self, novel_id: int, source_term: str) -> bool:
        return self._rowcount(
            "DELETE FROM glossary_suggestions WHERE novel_id = %s AND source_term = %s",
            (novel_id, source_term),
        ) > 0

    # --- reading progress ---
    def get_progress(self, novel_id: int) -> ReadingProgress | None:
        row = self._one("SELECT * FROM reading_progress WHERE novel_id = %s", (novel_id,))
        if not row:
            return None
        return ReadingProgress(novel_id=row["novel_id"], chapter_index=row["chapter_index"],
                               position=row["position"], updated_at=row["updated_at"])

    def save_progress(self, progress: ReadingProgress) -> None:
        row = self._one(
            "INSERT INTO reading_progress (novel_id, chapter_index, position, updated_at)"
            " VALUES (%s, %s, %s, now())"
            " ON CONFLICT (novel_id) DO UPDATE SET chapter_index = EXCLUDED.chapter_index,"
            " position = EXCLUDED.position, updated_at = EXCLUDED.updated_at"
            " RETURNING updated_at",
            (progress.novel_id, progress.chapter_index, progress.position),
        )
        progress.updated_at = row["updated_at"]

    # --- sessions ---
    def create_session(self, token_hash: str, now) -> None:
        self._rowcount(
            "INSERT INTO sessions (token_hash, created_at, last_seen_at) VALUES (%s, %s, %s)",
            (token_hash, now, now),
        )

    def touch_session(self, token_hash: str, now, idle_after) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "UPDATE sessions SET last_seen_at = %s"
                " WHERE token_hash = %s AND last_seen_at > %s RETURNING token_hash",
                (now, token_hash, idle_after),
            ).fetchone()
            if row is None:
                conn.execute("DELETE FROM sessions WHERE token_hash = %s AND last_seen_at <= %s",
                             (token_hash, idle_after))
            return row is not None

    def delete_session(self, token_hash: str) -> None:
        self._rowcount("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    # --- thông tin truyện + ảnh bìa ---
    def update_novel_details(self, novel_id: int, fields: dict[str, str | None]) -> Novel | None:
        cols = [k for k in DETAIL_FIELDS if k in fields]  # tên cột lấy từ danh sách cố định
        if not cols:
            return self.get_novel(novel_id)
        sets = ", ".join(f"{c} = %s" for c in cols)
        row = self._one(f"UPDATE novels SET {sets} WHERE id = %s RETURNING *",
                        (*[fields[c] for c in cols], novel_id))
        return _novel(row) if row else None

    def set_cover(self, novel_id: int, image: CoverImage) -> Novel | None:
        with self.unit_of_work():
            row = self._one(
                "UPDATE novels SET cover_updated_at = clock_timestamp() WHERE id = %s"
                " RETURNING *", (novel_id,))
            if not row:
                return None
            self._rowcount(
                "INSERT INTO novel_covers (novel_id, mime, data, width, height)"
                " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (novel_id) DO UPDATE SET"
                " mime = EXCLUDED.mime, data = EXCLUDED.data,"
                " width = EXCLUDED.width, height = EXCLUDED.height",
                (novel_id, image.mime, image.data, image.width, image.height))
            return _novel(row)

    def get_cover(self, novel_id: int) -> CoverImage | None:
        row = self._one("SELECT mime, data, width, height FROM novel_covers WHERE novel_id = %s",
                        (novel_id,))
        return CoverImage(row["mime"], bytes(row["data"]), row["width"], row["height"]) \
            if row else None

    def delete_cover(self, novel_id: int) -> bool:
        with self.unit_of_work():
            self._rowcount("UPDATE novels SET cover_updated_at = NULL WHERE id = %s", (novel_id,))
            return self._rowcount("DELETE FROM novel_covers WHERE novel_id = %s",
                                  (novel_id,)) > 0

    # --- preferences ---
    def get_preferences(self) -> dict[str, object]:
        return {r["key"]: r["value"] for r in self._all("SELECT key, value FROM preferences")}

    def set_preference(self, key: str, value: object) -> None:
        self._rowcount(
            "INSERT INTO preferences (key, value) VALUES (%s, %s)"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, Jsonb(value)),
        )


def _novel(r: dict[str, Any]) -> Novel:
    return Novel(id=r["id"], title=r["title"], source_lang=r["source_lang"],
                 target_lang=r["target_lang"], glossary_version=r["glossary_version"],
                 created_at=r["created_at"], last_read_at=r["last_read_at"],
                 author=r["author"], description=r["description"],
                 cover_updated_at=r["cover_updated_at"])


_INSERT_CHAPTER = (
    "INSERT INTO chapters (novel_id, idx, title, source_text, translated_title, translated_text,"
    " status, provider, model, chain_step, glossary_version, glossary_outdated, possible_omission,"
    " updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
)


def _insert_chapters(conn: Connection, chapters: list[Chapter]) -> None:
    """Chèn theo lô (một round-trip pipeline) và gán lại id cho từng chương."""
    if not chapters:
        return
    with conn.cursor() as cur:
        cur.executemany(_INSERT_CHAPTER, [
            (ch.novel_id, ch.index, ch.title, ch.source_text, ch.translated_title,
             ch.translated_text, ch.status.value, ch.provider, ch.model, ch.chain_step,
             ch.glossary_version, ch.glossary_outdated, ch.possible_omission, ch.updated_at)
            for ch in chapters
        ], returning=True)
        for ch in chapters:
            ch.id = cur.fetchone()["id"]
            cur.nextset()


def _chapter(r: dict[str, Any]) -> Chapter:
    return Chapter(
        id=r["id"], novel_id=r["novel_id"], index=r["idx"], title=r["title"],
        source_text=r["source_text"], translated_title=r["translated_title"],
        translated_text=r["translated_text"], status=ChapterStatus(r["status"]),
        provider=r["provider"], model=r["model"], chain_step=r["chain_step"],
        glossary_version=r["glossary_version"], glossary_outdated=r["glossary_outdated"],
        possible_omission=r["possible_omission"], updated_at=r["updated_at"],
    )


def _suggestion(r: dict[str, Any]) -> GlossarySuggestion:
    return GlossarySuggestion(
        novel_id=r["novel_id"], source_term=r["source_term"], target_term=r["target_term"],
        category=r["category"], status=SuggestionStatus(r["status"]), created_at=r["created_at"],
    )
