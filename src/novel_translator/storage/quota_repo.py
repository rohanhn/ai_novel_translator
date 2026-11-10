"""QuotaTracker trên bảng `provider_usage(day, step, requests, exhausted_until)`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from psycopg_pool import ConnectionPool

from ..domain.models import StepUsage

# "Ngày" tính theo giờ Pacific để khớp thời điểm Gemini (provider mặc định) reset quota ngày.
DAY_TZ = ZoneInfo("America/Los_Angeles")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresQuotaTracker:
    def __init__(self, pool: ConnectionPool, clock: Callable[[], datetime] = _utcnow,
                 day_tz: ZoneInfo = DAY_TZ):
        self.pool = pool
        self.clock = clock
        self.day_tz = day_tz

    def _today(self) -> date:
        return self.clock().astimezone(self.day_tz).date()

    def exhausted_until(self, step: int) -> datetime | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT max(exhausted_until) AS u FROM provider_usage"
                " WHERE step = %s AND exhausted_until > %s",
                (step, self.clock()),
            ).fetchone()
        return row["u"]

    def record_success(self, step: int) -> None:
        # Tăng nguyên tử trong DB: hai làn job ghi cùng lúc không mất lượt.
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO provider_usage (day, step, requests) VALUES (%s, %s, 1)"
                " ON CONFLICT (day, step) DO UPDATE"
                " SET requests = provider_usage.requests + 1",
                (self._today(), step),
            )

    def mark_exhausted(self, step: int, until: datetime) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO provider_usage (day, step, requests, exhausted_until)"
                " VALUES (%s, %s, 0, %s)"
                " ON CONFLICT (day, step) DO UPDATE SET exhausted_until ="
                " GREATEST(provider_usage.exhausted_until, EXCLUDED.exhausted_until)",
                (self._today(), step, until),
            )

    def usage_today(self) -> list[StepUsage]:
        now = self.clock()
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT step,"
                " COALESCE(max(requests) FILTER (WHERE day = %s), 0) AS requests,"
                " max(exhausted_until) FILTER (WHERE exhausted_until > %s) AS until"
                " FROM provider_usage GROUP BY step ORDER BY step",
                (self._today(), now),
            ).fetchall()
        return [StepUsage(step=r["step"], requests=r["requests"], exhausted_until=r["until"])
                for r in rows if r["requests"] or r["until"]]
