from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..domain.models import CompletionRequest, CompletionResult
from ..domain.ports import (
    ProviderError,
    RateQuotaError,
    RefusalError,
    StreamingProvider,
    TranslationError,
    TruncatedError,
)


def _retry_after(e: Any) -> float | None:
    headers = getattr(getattr(e, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


class AnthropicProvider(StreamingProvider):
    """Claude qua Anthropic SDK chính thức.

    - Streaming: phát text ngay khi có; stop_reason kiểm tra ở cuối luồng.
    - Prompt caching tự động: system prompt (chứa glossary) lặp lại giữa các chương → rẻ hơn.
    - Server-side fallback "default": khi model từ chối, API tự chạy lại trên model dự phòng.
    """

    name = "anthropic"
    default_model = "claude-opus-5-5"

    def __init__(self, effort: str = "medium", client: Any = None) -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise ProviderError("Cài thêm: pip install 'novel-translator[anthropic]'") from e
        self._anthropic = anthropic
        self._client = client or anthropic.Anthropic(max_retries=0)
        self._effort = effort

    def _open(self, request: CompletionRequest):
        return self._client.beta.messages.stream(
            model=request.model or self.default_model,
            max_tokens=request.max_output_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
            thinking={"type": "adaptive"},
            output_config={"effort": self._effort},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    def stream(self, request: CompletionRequest) -> Iterator[str]:
        return self._run(request, sink=None)

    def _run(self, request: CompletionRequest, sink: list | None) -> Iterator[str]:
        try:
            with self._open(request) as stream:
                yield from stream.text_stream
                message = stream.get_final_message()
        except TranslationError:
            raise
        except self._anthropic.APIError as e:
            raise self._classify(e) from e
        if sink is not None:
            sink.append(message)
        if message.stop_reason == "refusal":
            raise RefusalError("Model từ chối dịch (refusal).")
        if message.stop_reason == "max_tokens":
            raise TruncatedError("Bản dịch bị cắt do chạm max_tokens.")

    def _classify(self, e: Exception) -> TranslationError:
        a = self._anthropic
        if isinstance(e, a.RateLimitError):
            return RateQuotaError(f"Anthropic giới hạn tốc độ: {e}", retry_after=_retry_after(e))
        return ProviderError(f"Anthropic API lỗi: {e}")

    def complete(self, request: CompletionRequest) -> CompletionResult:
        sink: list = []
        text = "".join(self._run(request, sink))
        message = sink[0]
        return CompletionResult(
            text=text,
            provider=self.name,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
