"""Composition root: nơi DUY NHẤT nối adapter cụ thể vào service. CLI và API cùng dùng."""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from functools import lru_cache

from psycopg_pool import ConnectionPool

from .application.services import ExportService, GlossaryService, LibraryService, TranslationService
from .config import Settings
from .domain.ports import LLMProvider
from .export.txt_exporter import TxtExporter
from .ingest.txt_loader import TxtLoader
from .providers import create_provider
from .storage.db import DatabaseConfigError, create_pool
from .storage.migrator import migrate
from .storage.postgres_repo import PostgresRepository


@dataclass
class Container:
    settings: Settings
    library: LibraryService
    glossary: GlossaryService
    translation: TranslationService
    exports: ExportService
    repo: PostgresRepository
    pool: ConnectionPool

    def close(self) -> None:
        self.pool.close()


__all__ = ["Container", "DatabaseConfigError", "build_container", "get_container"]


def build_container(
    settings: Settings | None = None, pool: ConnectionPool | None = None
) -> Container:
    """Nối adapter. Không có `pool` thì mở pool từ NT_DATABASE_URL (lỗi → DatabaseConfigError),
    áp dụng migration còn thiếu và đưa chương `translating` (job mất do restart) về `pending`."""
    settings = settings or Settings()
    if pool is None:
        pool = create_pool(settings.database_url, settings.db_pool_max)
    migrate(pool)
    repo = PostgresRepository(pool)
    repo.reset_translating()
    providers: dict[str, LLMProvider] = {}

    def provider_factory(name: str | None) -> LLMProvider:
        key = name or settings.provider
        if key not in providers:
            providers[key] = create_provider(key, settings)
        return providers[key]

    return Container(
        settings=settings,
        library=LibraryService(repo, TxtLoader()),
        glossary=GlossaryService(repo),
        translation=TranslationService(
            repo, provider_factory, settings.max_segment_chars, default_model=settings.model
        ),
        exports=ExportService(repo, {"txt": TxtExporter()}),
        repo=repo,
        pool=pool,
    )


@lru_cache
def get_container() -> Container:
    container = build_container()
    atexit.register(container.close)  # đóng pool trước khi interpreter tắt
    return container
