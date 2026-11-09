"""Migration runner: áp dụng tuần tự các file `migrations/NNN_*.sql` chưa chạy.

- Bảng `schema_migrations(version, name, applied_at)` ghi file đã áp dụng.
- `pg_advisory_lock` bảo đảm không có hai process cùng migrate.
- Mỗi file chạy trong một transaction; file lỗi được rollback sạch (Postgres hỗ trợ DDL
  trong transaction).
"""

from __future__ import annotations

import re
from pathlib import Path

from psycopg import Connection
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Hằng số tùy ý, chỉ cần không trùng khóa advisory của app khác trên cùng database.
LOCK_KEY = 0x4E54_4D49  # "NTMI"
_FILE_RE = re.compile(r"^(\d+)_[\w-]+\.sql$")


class MigrationError(RuntimeError):
    pass


def discover(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for p in directory.iterdir():
        m = _FILE_RE.match(p.name)
        if m:
            files.append((int(m.group(1)), p))
    files.sort()
    versions = [v for v, _ in files]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"Trùng số version migration trong {directory}")
    return files


def migrate(pool_or_conn: ConnectionPool | Connection, directory: Path = MIGRATIONS_DIR
            ) -> list[int]:
    """Áp dụng các migration còn thiếu. Trả về danh sách version vừa áp dụng."""
    if isinstance(pool_or_conn, ConnectionPool):
        with pool_or_conn.connection() as conn:
            return _migrate(conn, directory)
    return _migrate(pool_or_conn, directory)


def _migrate(conn: Connection, directory: Path) -> list[int]:
    files = discover(directory)
    prev_autocommit = conn.autocommit
    conn.commit()
    conn.autocommit = True
    try:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version INT PRIMARY KEY,"
                " name TEXT NOT NULL,"
                " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            done = {r[0] if isinstance(r, tuple) else r["version"]
                    for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
            applied: list[int] = []
            for version, path in files:
                if version in done:
                    continue
                sql = path.read_text(encoding="utf-8")
                try:
                    with conn.transaction():
                        conn.execute(sql)
                        conn.execute(
                            "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                            (version, path.name),
                        )
                except Exception as e:
                    raise MigrationError(f"Migration {path.name} lỗi, đã rollback: {e}") from e
                applied.append(version)
            return applied
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    finally:
        conn.autocommit = prev_autocommit


def current_version(pool_or_conn: ConnectionPool | Connection) -> int:
    def _q(conn: Connection) -> int:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations"
                           ).fetchone()
        return row[0] if isinstance(row, tuple) else row["v"]

    if isinstance(pool_or_conn, ConnectionPool):
        with pool_or_conn.connection() as conn:
            return _q(conn)
    return _q(pool_or_conn)
