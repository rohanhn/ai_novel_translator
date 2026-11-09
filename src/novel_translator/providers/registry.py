"""Registry provider: thêm provider mới = viết 1 class + gọi register_provider()."""

from __future__ import annotations

from collections.abc import Callable

from ..config import Settings
from ..domain.ports import LLMProvider

ProviderFactory = Callable[[Settings], LLMProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    _REGISTRY[name] = factory


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def create_provider(name: str, settings: Settings) -> LLMProvider:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Provider '{name}' không tồn tại. Có sẵn: {', '.join(available_providers())}"
        ) from None
    return factory(settings)


def _anthropic(settings: Settings) -> LLMProvider:
    from .anthropic_provider import AnthropicProvider

    return AnthropicProvider()


def _openai(settings: Settings) -> LLMProvider:
    from .openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(name="openai", base_url=settings.openai_base_url)


def _ollama(settings: Settings) -> LLMProvider:
    from .openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(
        name="ollama", base_url=settings.ollama_base_url, api_key="ollama", default_model="qwen2.5:14b"
    )


def _echo(settings: Settings) -> LLMProvider:
    from .echo import EchoProvider

    return EchoProvider()


register_provider("anthropic", _anthropic)
register_provider("openai", _openai)
register_provider("ollama", _ollama)
register_provider("echo", _echo)
