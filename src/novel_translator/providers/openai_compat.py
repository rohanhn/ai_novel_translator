from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..domain.models import CompletionRequest
from ..domain.ports import (
    DailyQuotaError,
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


class OpenAICompatProvider(StreamingProvider):
    """Provider cho mọi API tương thích OpenAI Chat Completions (OpenAI, Ollama, vLLM, DeepSeek...)."""

    def __init__(
        self,
        name: str = "openai",
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        client: Any = None,
    ) -> None:
        try:
            import openai
        except ImportError as e:  # pragma: no cover
            raise ProviderError("Cài thêm: pip install 'novel-translator[openai]'") from e
        self._openai = openai
        self.name = name
        self.default_model = default_model
        self._client = client or openai.OpenAI(base_url=base_url, api_key=api_key, max_retries=0)

    def stream(self, request: CompletionRequest, policy=None, on_event=None) -> Iterator[str]:
        try:
            chunks = self._client.chat.completions.create(
                model=request.model or self.default_model,
                max_tokens=request.max_output_tokens,
                stream=True,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
            )
        except self._openai.OpenAIError as e:
            raise self._classify(e) from e
        return self._iterate(chunks)

    def _iterate(self, chunks: Any) -> Iterator[str]:
        finish: str | None = None
        it = iter(chunks)
        while True:
            try:
                chunk = next(it)
            except StopIteration:
                break
            except self._openai.OpenAIError as e:
                raise self._classify(e) from e
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish = choice.finish_reason
            text = getattr(choice.delta, "content", None)
            if text:
                yield text
        if finish == "length":
            raise TruncatedError(f"{self.name}: bản dịch bị cắt do chạm max_tokens.")
        if finish == "content_filter":
            raise RefusalError(f"{self.name}: nội dung bị bộ lọc chặn.")

    def _classify(self, e: Exception) -> TranslationError:
        o = self._openai
        if isinstance(e, o.RateLimitError):
            code = getattr(e, "code", None) or (getattr(e, "body", None) or {}).get("code")
            if code == "insufficient_quota":
                return DailyQuotaError(f"{self.name} hết quota: {e}")
            return RateQuotaError(f"{self.name} giới hạn tốc độ: {e}", retry_after=_retry_after(e))
        return ProviderError(f"{self.name} API lỗi: {e}")
