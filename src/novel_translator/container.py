"""Composition root: nơi DUY NHẤT nối adapter cụ thể vào service. CLI và API cùng dùng."""

from __future__ import annotations

import atexit
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from psycopg_pool import ConnectionPool

from .application.services import ExportService, GlossaryService, LibraryService, TranslationService
from .config import Settings
from .domain.ports import LLMProvider
from .export.txt_exporter import TxtExporter
from .ingest.txt_loader import TxtLoader
from .providers import create_provider
from .providers.chain import ChainLink, ChainProvider
from .storage.db import DatabaseConfigError, create_pool
from .storage.migrator import migrate
from .storage.postgres_repo import PostgresRepository
from .storage.quota_repo import PostgresQuotaTracker


@dataclass
class Container:
    settings: Settings
    library: LibraryService
    glossary: GlossaryService
    translation: TranslationService
    exports: ExportService
    repo: PostgresRepository
    quota: PostgresQuotaTracker
    provider_factory: Callable[[str | None, str | None], LLMProvider]
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
    quota = PostgresQuotaTracker(pool)
    providers: dict[str, LLMProvider] = {}
    chain: list[ChainProvider] = []

    def single(name: str) -> LLMProvider:
        # Một instance (một key) cho mỗi provider, dùng chung giữa các bước của chuỗi.
        if name not in providers:
            providers[name] = create_provider(name, settings)
        return providers[name]

    def get_chain() -> ChainProvider:
        if not chain:
            steps = settings.chain_steps()
            chain.append(ChainProvider(
                [ChainLink(single(s.provider), s.model) for s in steps], quota
            ))
        return chain[0]

    def provider_factory(name: str | None, model: str | None = None) -> LLMProvider:
        """- provider chỉ định (CLI --provider / NT_PROVIDER) → dùng thẳng, bỏ qua chuỗi.
        - chỉ có model (--model / NT_MODEL) → provider của bước 1 với model đó.
        - không chỉ định gì → chuỗi fallback."""
        name = name or settings.provider
        if name:
            return single(name)
        if model:
            return single(settings.chain_steps()[0].provider)
        return get_chain()

    return Container(
        settings=settings,
        library=LibraryService(repo, TxtLoader()),
        glossary=GlossaryService(repo),
        translation=TranslationService(
            repo, provider_factory, settings.max_segment_chars, default_model=settings.model
        ),
        exports=ExportService(repo, {"txt": TxtExporter()}),
        repo=repo,
        quota=quota,
        provider_factory=provider_factory,
        pool=pool,
    )


@lru_cache
def get_container() -> Container:
    container = build_container()
    atexit.register(container.close)  # đóng pool trước khi interpreter tắt
    return container
