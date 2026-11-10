"""Kết nối PostgreSQL: tạo pool psycopg và báo lỗi cấu hình rõ ràng (không lộ mật khẩu)."""

from __future__ import annotations

import re

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

CONNECT_TIMEOUT_S = 5


class DatabaseConfigError(RuntimeError):
    """Thiếu cấu hình database hoặc không kết nối được lúc khởi động."""


def mask_url(url: str) -> str:
    """Ẩn mật khẩu trong URL dạng postgresql://user:pass@host/db."""
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1***@", url)


def _scrub(text: str, url: str) -> str:
    m = re.search(r"://[^:/@]+:([^@]*)@", url)
    return text.replace(m.group(1), "***") if m and m.group(1) else text


def ping(pool: ConnectionPool, timeout: float = 2.0) -> bool:
    """True nếu lấy được connection trong `timeout` giây và `SELECT 1` chạy được."""
    try:
        with pool.connection(timeout=timeout) as conn:
            conn.execute("SELECT 1")
        return True
    except (psycopg.Error, OSError):  # PoolTimeout là một psycopg.OperationalError
        return False


def create_pool(url: str | None, max_size: int = 5, var_name: str = "NT_DATABASE_URL"
                ) -> ConnectionPool:
    """Mở pool và kiểm tra kết nối ngay; lỗi thì ném DatabaseConfigError có tên biến môi trường."""
    if not url:
        raise DatabaseConfigError(
            f"Chưa cấu hình {var_name} (vd. postgresql://user:pass@localhost:5432/db)."
        )
    try:
        psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_S).close()
    except (psycopg.Error, ValueError) as e:
        raise DatabaseConfigError(
            f"Không kết nối được PostgreSQL qua {var_name} ({mask_url(url)}): "
            f"{_scrub(str(e).strip(), url)}"
        ) from None
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max(1, max_size),
        kwargs={"row_factory": dict_row, "connect_timeout": CONNECT_TIMEOUT_S},
        open=False,
        name="novel-translator",
    )
    pool.open(wait=True, timeout=CONNECT_TIMEOUT_S * 2)
    return pool
