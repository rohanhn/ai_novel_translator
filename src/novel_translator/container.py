"""Composition root: nơi DUY NHẤT nối adapter cụ thể vào service. CLI và API cùng dùng."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .application.services import ExportService, GlossaryService, LibraryService, TranslationService
from .config import Settings
from .domain.ports import LLMProvider
from .export.txt_exporter import TxtExporter
from .ingest.txt_loader import TxtLoader
from .providers import create_provider
from .storage.sqlite_repo import SqliteRepository


@dataclass
class Container:
    settings: Settings
    library: LibraryService
    glossary: GlossaryService
    translation: TranslationService
    exports: ExportService


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings()
    repo = SqliteRepository(settings.db_path)
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
    )


@lru_cache
def get_container() -> Container:
    return build_container()
