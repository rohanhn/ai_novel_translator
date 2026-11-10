"""`novel migrate` (spec interfaces "CLI commands"; deployment "Migrate before serving").

Mỗi test chạy migration vào một schema riêng (qua `search_path` trong URL) để có "database
trống" mà không đụng schema `public` của các test khác.
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

import pytest
from typer.testing import CliRunner

from novel_translator.interfaces.cli import main as cli
from novel_translator.storage import migrator

runner = CliRunner()


@pytest.fixture
def fresh_db_url(db, test_db_url, monkeypatch, tmp_path):
    schema = f"mig_{uuid.uuid4().hex[:8]}"
    with db.connection() as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in test_db_url else "?"
    url = f"{test_db_url}{sep}options={quote(f'-csearch_path={schema}')}"
    # Không đọc .env của repo, không có key LLM hay mật khẩu: lệnh vẫn phải chạy được.
    monkeypatch.chdir(tmp_path)
    for var in ("GEMINI_API_KEY", "NT_PASSWORD_HASH", "NT_PROVIDER", "NT_CHAIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NT_DATABASE_URL", url)
    yield schema
    with db.connection() as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")


def _all_versions() -> list[int]:
    return [v for v, _ in migrator.discover()]


def test_migrate_fresh_database_then_up_to_date(fresh_db_url, db):
    versions = _all_versions()
    r = runner.invoke(cli.app, ["migrate"])
    assert r.exit_code == 0, r.output
    assert "Đã áp dụng migration: " + ", ".join(map(str, versions)) in r.output
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT version FROM {fresh_db_url}.schema_migrations ORDER BY version").fetchall()
    assert [row["version"] for row in rows] == versions

    r = runner.invoke(cli.app, ["migrate"])
    assert r.exit_code == 0, r.output
    assert f"Database đã cập nhật (version {versions[-1]})" in r.output


def test_failed_migration_exits_nonzero_naming_file(fresh_db_url, tmp_path, monkeypatch):
    mig = tmp_path / "migs"
    mig.mkdir()
    (mig / "001_ok.sql").write_text("CREATE TABLE a (id INT);", encoding="utf-8")
    (mig / "002_hong.sql").write_text("CREATE TABLE b (id KHONG_CO_KIEU);", encoding="utf-8")
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", mig)
    r = runner.invoke(cli.app, ["migrate"])
    assert r.exit_code != 0
    assert "002_hong.sql" in r.output


def test_missing_database_url_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NT_DATABASE_URL", raising=False)
    r = runner.invoke(cli.app, ["migrate"])
    assert r.exit_code == 1
    assert "NT_DATABASE_URL" in r.output
