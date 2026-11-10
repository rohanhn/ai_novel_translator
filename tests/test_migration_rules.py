"""Migration chỉ thêm (spec deployment "Rollback-safe migrations", "Older release runs on a
newer schema"; design D8).

Kiểm tra tĩnh từng file `migrations/*.sql`. Được phép: tạo bảng mới (kèm mọi constraint), thêm
cột nullable hoặc có DEFAULT, tạo index (không UNIQUE trên bảng đã có), `UPDATE` để backfill.
Cấm mọi thứ làm image cũ hỏng khi chạy trên schema mới: xoá, đổi tên, đổi kiểu, `NOT NULL` mới,
xoá dòng, hay constraint mới trên bảng đã có.
"""

from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from urllib.parse import quote

import psycopg
import pytest

from novel_translator.storage import migrator

# ---------------------------------------------------------------- bộ kiểm tra


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _split_top_level(text: str, sep: str) -> list[str]:
    """Tách theo `sep` ở ngoài ngoặc đơn và ngoài chuỗi '...'."""
    parts, depth, quote_open, buf = [], 0, False, []
    for ch in text:
        if ch == "'":
            quote_open = not quote_open
        elif not quote_open and ch == "(":
            depth += 1
        elif not quote_open and ch == ")":
            depth -= 1
        if ch == sep and depth == 0 and not quote_open:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _table_name(raw: str) -> str:
    name = raw.strip().strip('"').lower()
    return name.split(".")[-1].strip('"')


_IDENT = r'((?:"[^"]+"|[\w]+)(?:\.(?:"[^"]+"|[\w]+))?)'
_ALWAYS_FORBIDDEN = [
    # `DROP NOT NULL` (nới lỏng, bản cũ vẫn ghi được) không khớp mẫu này nên được phép.
    (r"\bDROP\s+(TABLE|COLUMN|INDEX|CONSTRAINT|TYPE|SCHEMA|VIEW|DEFAULT)\b", "DROP"),
    (r"\bRENAME\b", "RENAME"),
    (r"\bALTER\s+COLUMN\s+\S+\s+(SET\s+DATA\s+)?TYPE\b", "đổi kiểu cột"),
    (r"\bALTER\s+COLUMN\s+\S+\s+SET\s+NOT\s+NULL\b", "SET NOT NULL"),
    (r"\bTRUNCATE\b", "TRUNCATE"),
    (r"\bDELETE\s+FROM\b", "DELETE FROM"),
]


def violations(sql: str) -> list[str]:
    """Danh sách câu vi phạm (đã gọn khoảng trắng) kèm lý do."""
    statements = [re.sub(r"\s+", " ", s) for s in _split_top_level(_strip_comments(sql), ";")]
    created = {
        _table_name(m.group(1))
        for s in statements
        if (m := re.match(rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT}", s, re.IGNORECASE))
    }
    found: list[str] = []
    for stmt in statements:
        up = stmt.upper()
        found += [f"{reason}: {stmt}" for pattern, reason in _ALWAYS_FORBIDDEN
                  if re.search(pattern, up)]
        m = re.match(rf"CREATE\s+UNIQUE\s+INDEX\s+.*?\bON\s+(?:ONLY\s+)?{_IDENT}", stmt, re.IGNORECASE)
        if m and _table_name(m.group(1)) not in created:
            found.append(f"UNIQUE INDEX trên bảng đã có: {stmt}")
        m = re.match(rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?{_IDENT}\s+(.*)$",
                     stmt, re.IGNORECASE | re.DOTALL)
        if not m or _table_name(m.group(1)) in created:
            continue
        for action in _split_top_level(m.group(2), ","):
            a = action.upper()
            if re.match(r"ADD\s+(CONSTRAINT\b|PRIMARY\s+KEY|UNIQUE|CHECK|FOREIGN\s+KEY)", a):
                found.append(f"constraint mới trên bảng đã có: {stmt}")
            elif re.match(r"ADD\b", a):  # ADD [COLUMN] ...
                if re.search(r"\bNOT\s+NULL\b", a) and not re.search(r"\bDEFAULT\b", a):
                    found.append(f"cột NOT NULL không có DEFAULT: {stmt}")
                if re.search(r"\b(UNIQUE|CHECK|REFERENCES|PRIMARY\s+KEY)\b", a):
                    found.append(f"constraint mới trên bảng đã có: {stmt}")
    return found


# ---------------------------------------------------------------- file thật


@pytest.mark.parametrize("path", [p for _, p in migrator.discover()], ids=lambda p: p.name)
def test_repository_migrations_are_additive(path: Path):
    bad = violations(path.read_text(encoding="utf-8"))
    assert not bad, f"{path.name} vi phạm quy tắc migration chỉ thêm:\n" + "\n".join(bad)


# ---------------------------------------------------------------- bộ kiểm tra bắt đúng

FORBIDDEN = {
    "drop_column": "ALTER TABLE novels DROP COLUMN author;",
    "drop_table": "DROP TABLE glossary;",
    "rename_column": "ALTER TABLE novels RENAME COLUMN title TO name;",
    "rename_table": "ALTER TABLE novels RENAME TO books;",
    "change_type": "ALTER TABLE chapters ALTER COLUMN idx TYPE BIGINT;",
    "set_data_type": "ALTER TABLE chapters ALTER COLUMN idx SET DATA TYPE BIGINT;",
    "set_not_null": "ALTER TABLE novels ALTER COLUMN author SET NOT NULL;",
    "not_null_no_default": "ALTER TABLE novels ADD COLUMN x INT NOT NULL;",
    "not_null_no_default_no_column_kw": "ALTER TABLE novels ADD x INT NOT NULL;",
    "truncate": "TRUNCATE sessions;",
    "delete": "DELETE FROM sessions WHERE true;",
    "add_unique_constraint": "ALTER TABLE novels ADD CONSTRAINT novels_title_uq UNIQUE (title);",
    "add_check": "ALTER TABLE novels ADD CHECK (length(title) > 0);",
    "add_fk_column": "ALTER TABLE chapters ADD COLUMN owner BIGINT REFERENCES novels(id);",
    "unique_column": "ALTER TABLE novels ADD COLUMN slug TEXT UNIQUE;",
    "unique_index_existing": "CREATE UNIQUE INDEX novels_title_idx ON novels (title);",
    "drop_default": "ALTER TABLE novels ALTER COLUMN created_at DROP DEFAULT;",
    "second_clause": "ALTER TABLE novels ADD COLUMN a TEXT, DROP COLUMN author;",
}

ALLOWED = {
    "new_table_with_constraints": """
        CREATE TABLE bookmarks (
            id       BIGSERIAL PRIMARY KEY,
            novel_id BIGINT NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
            label    TEXT NOT NULL,
            UNIQUE (novel_id, label)
        );
        ALTER TABLE bookmarks ADD CONSTRAINT label_len CHECK (length(label) < 100);
        CREATE UNIQUE INDEX bookmarks_label_idx ON bookmarks (label);
    """,
    "nullable_columns": "ALTER TABLE novels ADD COLUMN a TEXT, ADD COLUMN b TIMESTAMPTZ;",
    "not_null_with_default": "ALTER TABLE novels ADD COLUMN rating INT NOT NULL DEFAULT 0;",
    "plain_index": "CREATE INDEX IF NOT EXISTS chapters_status_idx ON chapters (status);",
    "backfill": "UPDATE novels SET author = '' WHERE author IS NULL;",
    "drop_not_null": "ALTER TABLE novels ALTER COLUMN title DROP NOT NULL;",
    "comment_mentions_drop": "-- không DROP COLUMN gì cả\n/* RENAME */ ALTER TABLE novels ADD c TEXT;",
    "on_delete_in_new_table": "CREATE TABLE t (n BIGINT REFERENCES novels(id) ON DELETE CASCADE);",
}


@pytest.mark.parametrize("sql", FORBIDDEN.values(), ids=FORBIDDEN.keys())
def test_forbidden_statement_is_reported(sql, tmp_path):
    f = tmp_path / "003_xau.sql"
    f.write_text(sql, encoding="utf-8")
    bad = violations(f.read_text(encoding="utf-8"))
    assert bad, f"không bắt được: {sql}"


@pytest.mark.parametrize("sql", ALLOWED.values(), ids=ALLOWED.keys())
def test_additive_statement_is_accepted(sql):
    assert violations(sql) == []


def test_report_names_file_and_statement(tmp_path):
    """Spec "Forbidden statement": thông báo nêu tên file và câu vi phạm."""
    f = tmp_path / "003_xau.sql"
    f.write_text("ALTER TABLE novels DROP COLUMN author;", encoding="utf-8")
    with pytest.raises(AssertionError) as e:
        test_repository_migrations_are_additive(f)
    assert "003_xau.sql" in str(e.value)
    assert "ALTER TABLE novels DROP COLUMN author" in str(e.value)


# ---------------------------------------------------------------- hành vi của migrator


@pytest.fixture
def fresh_url(db, test_db_url):
    """URL tới một schema trống riêng (search_path), xoá sau test."""
    schema = f"mig_{uuid.uuid4().hex[:8]}"
    with db.connection() as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in test_db_url else "?"
    yield f"{test_db_url}{sep}options={quote(f'-csearch_path={schema}')}"
    with db.connection() as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")


def test_older_release_ignores_newer_versions(fresh_url):
    """Spec "Older release on a newer schema": DB có version mới hơn → không áp dụng gì."""
    with psycopg.connect(fresh_url) as conn:
        migrator.migrate(conn)
        conn.execute("INSERT INTO schema_migrations (version, name) VALUES (999, '999_moi.sql')")
        conn.commit()
        assert migrator.migrate(conn) == []
        assert migrator.current_version(conn) == 999


def test_concurrent_migrate_applies_each_once(fresh_url):
    """Spec "Two starts at once": advisory lock → mỗi migration chỉ áp dụng một lần."""
    results: list[list[int]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def run():
        try:
            with psycopg.connect(fresh_url) as conn:
                barrier.wait()
                results.append(migrator.migrate(conn))
        except BaseException as e:  # noqa: BLE001 - chuyển lỗi của thread về test
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors
    expected = [v for v, _ in migrator.discover()]
    assert sorted(results[0] + results[1]) == expected
    with psycopg.connect(fresh_url) as conn:
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert [r[0] for r in rows] == expected
