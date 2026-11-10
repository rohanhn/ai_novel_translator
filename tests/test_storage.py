"""Storage PostgreSQL: cấu hình kết nối, migration, repository, reset khi khởi động."""

from __future__ import annotations

import pytest

from novel_translator.config import Settings
from novel_translator.container import build_container
from novel_translator.domain.models import (
    Chapter,
    ChapterStatus,
    GlossaryEntry,
    GlossarySuggestion,
    Novel,
    ReadingProgress,
    SuggestionStatus,
)
from novel_translator.storage.db import DatabaseConfigError, mask_url
from novel_translator.storage.migrator import (
    MIGRATIONS_DIR,
    MigrationError,
    current_version,
    discover,
    migrate,
)

# ---------- 2.2 cấu hình kết nối ----------


def test_container_bad_url_names_variable_and_hides_password():
    bad = "postgresql://someone:s3cr3t-pw@127.0.0.1:1/nope"
    with pytest.raises(DatabaseConfigError) as ei:
        build_container(Settings(provider="echo", database_url=bad))
    msg = str(ei.value)
    assert "NT_DATABASE_URL" in msg
    assert "s3cr3t-pw" not in msg


def test_container_missing_url_names_variable():
    with pytest.raises(DatabaseConfigError, match="NT_DATABASE_URL"):
        build_container(Settings(provider="echo", database_url=None, _env_file=None))


def test_mask_url():
    assert mask_url("postgresql://u:p@h:5432/d") == "postgresql://u:***@h:5432/d"


# ---------- 2.3 migration runner ----------


@pytest.fixture
def scratch_conn(db):
    """Kết nối có search_path trỏ vào một schema tạm, để migrate từ trạng thái trống."""
    with db.connection() as conn:
        conn.autocommit = True
        conn.execute("DROP SCHEMA IF EXISTS mig_scratch CASCADE")
        conn.execute("CREATE SCHEMA mig_scratch")
        conn.execute("SET search_path TO mig_scratch")
        try:
            yield conn
        finally:
            conn.execute("RESET search_path")
            conn.execute("DROP SCHEMA IF EXISTS mig_scratch CASCADE")


def _tables(conn) -> set[str]:
    return {r["tablename"] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'mig_scratch'").fetchall()}


def test_migrate_empty_database_to_latest_then_noop(scratch_conn):
    latest = discover()[-1][0]
    assert migrate(scratch_conn) == [v for v, _ in discover()]
    assert current_version(scratch_conn) == latest
    assert {"novels", "chapters", "glossary", "glossary_suggestions", "reading_progress",
            "preferences", "provider_usage", "sessions", "schema_migrations"} <= _tables(
        scratch_conn)
    # chạy lại lần hai không làm gì
    assert migrate(scratch_conn) == []
    assert current_version(scratch_conn) == latest


def test_failed_migration_rolls_back_cleanly(scratch_conn, tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE ok_table (id INT);")
    (tmp_path / "002_bad.sql").write_text(
        "CREATE TABLE half_table (id INT);\nTHIS IS NOT SQL;"
    )
    with pytest.raises(MigrationError, match="002_bad.sql"):
        migrate(scratch_conn, tmp_path)
    assert current_version(scratch_conn) == 1
    tables = _tables(scratch_conn)
    assert "ok_table" in tables
    assert "half_table" not in tables  # file lỗi rollback toàn bộ


def test_duplicate_migration_versions_rejected(tmp_path):
    (tmp_path / "001_a.sql").write_text("")
    (tmp_path / "001_b.sql").write_text("")
    with pytest.raises(MigrationError):
        discover(tmp_path)


def test_migrations_dir_ships_initial():
    assert (MIGRATIONS_DIR / "001_initial.sql").exists()


# ---------- 2.4 fixture dọn dữ liệu ----------


def test_fixture_leaves_database_clean_part1(repo):
    repo.add_novel(Novel(title="tạm"))
    assert len(repo.list_novels()) == 1


def test_fixture_leaves_database_clean_part2(repo):
    # chạy sau part1: dữ liệu đã bị TRUNCATE, id bắt đầu lại từ 1
    assert repo.list_novels() == []
    assert repo.add_novel(Novel(title="mới")).id == 1


# ---------- 2.5 repository ----------


def _novel_with_chapters(repo, n=3) -> Novel:
    novel = repo.add_novel(Novel(title="Vũ Động"))
    repo.add_chapters([
        Chapter(novel_id=novel.id, index=i, title=f"第{i}章", source_text=f"林动 第{i}章 内容")
        for i in range(1, n + 1)
    ])
    return novel


def test_chapter_new_fields_roundtrip(repo):
    novel = _novel_with_chapters(repo, 1)
    ch = repo.get_chapter(novel.id, 1)
    assert ch.status == ChapterStatus.PENDING and not ch.glossary_outdated
    ch.translated_title, ch.translated_text = "Chương 1", "Lâm Động ..."
    ch.status, ch.provider, ch.model = ChapterStatus.EDITED, "gemini", "gemini-3.5-flash"
    ch.chain_step, ch.glossary_version = 2, 3
    ch.glossary_outdated = ch.possible_omission = True
    repo.update_chapter(ch)
    got = repo.get_chapter(novel.id, 1)
    assert (got.status, got.chain_step, got.glossary_version) == (ChapterStatus.EDITED, 2, 3)
    assert got.glossary_outdated and got.possible_omission
    assert got.updated_at.tzinfo is not None


def test_novel_glossary_version_and_last_read(repo):
    novel = repo.add_novel(Novel(title="x"))
    assert novel.glossary_version == 0
    assert repo.bump_glossary_version(novel.id) == 1
    assert repo.bump_glossary_version(novel.id) == 2
    repo.touch_novel_read(novel.id)
    got = repo.get_novel(novel.id)
    assert got.glossary_version == 2 and got.last_read_at is not None


def test_glossary_upsert(repo):
    novel = repo.add_novel(Novel(title="x"))
    a = repo.upsert_glossary(GlossaryEntry(novel.id, "林动", "Lâm Động"))
    b = repo.upsert_glossary(GlossaryEntry(novel.id, "林动", "Lâm Đông", "sửa"))
    assert a.id == b.id
    assert [(g.target_term, g.note) for g in repo.list_glossary(novel.id)] == [("Lâm Đông", "sửa")]
    assert repo.delete_glossary(novel.id, "林动") and not repo.delete_glossary(novel.id, "林动")


def test_suggestions(repo):
    novel = repo.add_novel(Novel(title="x"))
    assert repo.add_suggestion(GlossarySuggestion(novel.id, "青阳镇", "Thanh Dương trấn", "địa danh"))
    # đề xuất lại cùng term không ghi đè (kể cả sau khi bị dismiss)
    assert repo.set_suggestion_status(novel.id, "青阳镇", SuggestionStatus.DISMISSED)
    assert not repo.add_suggestion(GlossarySuggestion(novel.id, "青阳镇", "khác"))
    assert repo.get_suggestion(novel.id, "青阳镇").target_term == "Thanh Dương trấn"
    repo.add_suggestion(GlossarySuggestion(novel.id, "林动", "Lâm Động"))
    pending = repo.list_suggestions(novel.id, SuggestionStatus.PENDING)
    assert [s.source_term for s in pending] == ["林动"]
    assert len(repo.list_suggestions(novel.id)) == 2
    assert repo.delete_suggestion(novel.id, "林动")
    assert repo.get_suggestion(novel.id, "林动") is None


def test_reading_progress_upsert(repo):
    novel = repo.add_novel(Novel(title="x"))
    assert repo.get_progress(novel.id) is None
    repo.save_progress(ReadingProgress(novel.id, 3, 0.25))
    repo.save_progress(ReadingProgress(novel.id, 4, 0.5))
    p = repo.get_progress(novel.id)
    assert (p.chapter_index, p.position) == (4, 0.5)


def test_preferences_jsonb(repo):
    repo.set_preference("theme", "sepia")
    repo.set_preference("font_size", 18)
    repo.set_preference("prefetch", False)
    repo.set_preference("theme", "dark")
    assert repo.get_preferences() == {"theme": "dark", "font_size": 18, "prefetch": False}


def test_chapters_with_source_term(repo):
    novel = repo.add_novel(Novel(title="x"))
    repo.add_chapters([
        Chapter(novel_id=novel.id, index=1, title="a", source_text="林动来了"),
        Chapter(novel_id=novel.id, index=2, title="b", source_text="没有他"),
        Chapter(novel_id=novel.id, index=3, title="c", source_text="又是林动"),
    ])
    assert [c.index for c in repo.chapters_with_source_term(novel.id, "林动")] == [1, 3]


def test_delete_novel_cascades_all_children(repo, db):
    novel = _novel_with_chapters(repo)
    other = _novel_with_chapters(repo, 1)
    repo.upsert_glossary(GlossaryEntry(novel.id, "林动", "Lâm Động"))
    repo.add_suggestion(GlossarySuggestion(novel.id, "青阳镇", "Thanh Dương trấn"))
    repo.save_progress(ReadingProgress(novel.id, 2, 0.3))

    assert repo.delete_novel(novel.id)
    assert not repo.delete_novel(novel.id)
    with db.connection() as conn:
        for table in ("chapters", "glossary", "glossary_suggestions", "reading_progress"):
            n = conn.execute(f"SELECT count(*) AS n FROM {table} WHERE novel_id = %s",
                             (novel.id,)).fetchone()["n"]
            assert n == 0, table
    assert len(repo.list_chapters(other.id)) == 1  # truyện khác không bị ảnh hưởng


def test_status_check_constraint(repo, db):
    novel = _novel_with_chapters(repo, 1)
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation), db.connection() as conn:
        conn.execute("UPDATE chapters SET status = 'bogus' WHERE novel_id = %s", (novel.id,))


# ---------- 2.6 reset khi khởi động ----------


def test_startup_resets_translating_to_pending(repo, db):
    novel = _novel_with_chapters(repo, 2)
    ch1 = repo.get_chapter(novel.id, 1)
    ch1.status = ChapterStatus.TRANSLATING
    repo.update_chapter(ch1)
    ch2 = repo.get_chapter(novel.id, 2)
    ch2.status, ch2.translated_text = ChapterStatus.TRANSLATED, "xong"
    repo.update_chapter(ch2)

    build_container(Settings(provider="echo"), pool=db)  # "khởi động lại"

    assert repo.get_chapter(novel.id, 1).status == ChapterStatus.PENDING
    assert repo.get_chapter(novel.id, 2).status == ChapterStatus.TRANSLATED


# ---------- edit-novel-details 1.2: thông tin truyện + ảnh bìa ----------

def test_migration_002_on_existing_data(scratch_conn, tmp_path):
    """Migrate tới 001, có dữ liệu, rồi áp 002: truyện cũ có các trường mới là NULL."""
    import shutil

    shutil.copy(MIGRATIONS_DIR / "001_initial.sql", tmp_path / "001_initial.sql")
    migrate(scratch_conn, tmp_path)
    scratch_conn.execute("INSERT INTO novels (title) VALUES ('cũ')")
    shutil.copy(MIGRATIONS_DIR / "002_novel_details.sql", tmp_path / "002_novel_details.sql")
    assert migrate(scratch_conn, tmp_path) == [2]
    row = scratch_conn.execute(
        "SELECT title, author, description, cover_updated_at FROM novels").fetchone()
    assert row == {"title": "cũ", "author": None, "description": None, "cover_updated_at": None}
    assert "novel_covers" in _tables(scratch_conn)


def test_old_novel_has_empty_details(repo):
    n = repo.add_novel(Novel(title="T"))
    got = repo.get_novel(n.id)
    assert (got.author, got.description, got.cover_updated_at, got.has_cover) == (
        None, None, None, False)


def test_update_novel_details_partial(repo):
    n = repo.add_novel(Novel(title="T"))
    got = repo.update_novel_details(n.id, {"author": "A", "description": "x\ny"})
    assert (got.title, got.author, got.description) == ("T", "A", "x\ny")
    got = repo.update_novel_details(n.id, {"title": "T2", "author": None})
    assert (got.title, got.author, got.description) == ("T2", None, "x\ny")
    assert repo.update_novel_details(n.id, {}).title == "T2"
    assert repo.update_novel_details(999_999, {"title": "x"}) is None
    # overview đọc được cột mới
    assert repo.library_overview()[0].novel.description == "x\ny"


def test_cover_set_replace_get_delete(repo):
    from novel_translator.domain.novel_details import CoverImage

    n = repo.add_novel(Novel(title="T"))
    assert repo.get_cover(n.id) is None
    a = repo.set_cover(n.id, CoverImage("image/webp", b"one", 10, 20))
    assert a.has_cover and repo.get_cover(n.id) == CoverImage("image/webp", b"one", 10, 20)
    b = repo.set_cover(n.id, CoverImage("image/webp", b"two", 30, 40))
    assert b.cover_updated_at > a.cover_updated_at
    assert repo.get_cover(n.id).data == b"two"
    assert repo.get_novel(n.id).cover_updated_at == b.cover_updated_at
    assert repo.delete_cover(n.id) is True
    assert repo.get_cover(n.id) is None and not repo.get_novel(n.id).has_cover
    assert repo.delete_cover(n.id) is False
    assert repo.set_cover(999_999, CoverImage("image/webp", b"x", 1, 1)) is None


def test_delete_novel_removes_cover(repo, db):
    from novel_translator.domain.novel_details import CoverImage

    n = repo.add_novel(Novel(title="T"))
    repo.set_cover(n.id, CoverImage("image/webp", b"one", 10, 20))
    repo.delete_novel(n.id)
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM novel_covers").fetchone()["n"] == 0
