"""Fixture dùng chung. Test cần PostgreSQL local: database riêng lấy từ NT_TEST_DATABASE_URL.

- Mỗi phiên pytest: drop + tạo lại schema `public` rồi chạy migration một lần.
- Sau mỗi test dùng database: TRUNCATE ... RESTART IDENTITY CASCADE mọi bảng (trừ
  schema_migrations).
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from novel_translator.config import Settings
from novel_translator.container import build_container, get_container
from novel_translator.storage.db import DatabaseConfigError, create_pool
from novel_translator.storage.migrator import migrate

SETUP_HINT = """
Test cần PostgreSQL local với một database RIÊNG cho test (tên kết thúc bằng `_test`).
1. Tạo role + database (một lần), ví dụ trên container shared-postgres:
     docker exec -i shared-postgres psql -U postgres <<'SQL'
     CREATE ROLE ai_novel_translator LOGIN PASSWORD '<pass>';
     CREATE DATABASE ai_novel_translator_test OWNER ai_novel_translator;
     SQL
2. Thêm vào .env:
     NT_TEST_DATABASE_URL=postgresql://ai_novel_translator:<pass>@localhost:5432/ai_novel_translator_test
"""


class _TestDbSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NT_", env_file=".env", extra="ignore")
    test_database_url: str | None = None


def _check_is_test_db(url: str) -> None:
    db = urlparse(url).path.lstrip("/")
    if not db.endswith("_test"):
        pytest.exit(
            f"NT_TEST_DATABASE_URL trỏ tới database '{db}', không kết thúc bằng '_test'. "
            "Từ chối chạy vì test sẽ TRUNCATE toàn bộ bảng.\n" + SETUP_HINT,
            returncode=4,
        )


@pytest.fixture(scope="session")
def pg_pool():
    url = _TestDbSettings().test_database_url
    if not url:
        pytest.exit("Chưa cấu hình NT_TEST_DATABASE_URL.\n" + SETUP_HINT, returncode=4)
    _check_is_test_db(url)
    try:
        pool = create_pool(url, max_size=5, var_name="NT_TEST_DATABASE_URL")
    except DatabaseConfigError as e:
        pytest.exit(f"{e}\n{SETUP_HINT}", returncode=4)
    with pool.connection() as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
    migrate(pool)
    yield pool
    pool.close()


def _truncate_all(pool) -> None:
    with pool.connection() as conn:
        tables = [r["tablename"] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            " AND tablename <> 'schema_migrations'"
        ).fetchall()]
        if tables:
            conn.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")


@pytest.fixture
def db(pg_pool):
    """Pool tới database test; dữ liệu bị xóa sạch sau mỗi test."""
    yield pg_pool
    _truncate_all(pg_pool)


@pytest.fixture
def test_db_url(pg_pool) -> str:
    return _TestDbSettings().test_database_url


@pytest.fixture
def container(db):
    return build_container(Settings(provider="echo"), pool=db)


@pytest.fixture
def repo(container):
    return container.repo


@pytest.fixture
def sample_txt(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text(
        "第一章 少年\n林动站在山上。\n他看着远方。\n\n第二章 修炼\n林动开始修炼。\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def api_client(container):
    from fastapi.testclient import TestClient

    from novel_translator.interfaces.api.app import app

    app.dependency_overrides[get_container] = lambda: container
    yield TestClient(app)
    app.dependency_overrides.clear()

