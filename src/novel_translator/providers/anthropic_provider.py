from __future__ import annotations

from ..domain.models import CompletionRequest, CompletionResult
from ..domain.ports import TranslationError


class AnthropicProvider:
    """Claude qua Anthropic SDK chính thức.

    - Streaming + get_final_message() để tránh timeout với chương dài.
    - Prompt caching tự động: system prompt (chứa glossary) lặp lại giữa các đoạn → rẻ hơn.
    - Server-side fallback "default": khi model từ chối, API tự chạy lại trên model dự phòng.
    """

    name = "anthropic"
    default_model = "claude-opus-5-5"

    def __init__(self, effort: str = "medium") -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise TranslationError("Cài thêm: pip install 'novel-translator[anthropic]'") from e
        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._effort = effort

    def complete(self, request: CompletionRequest) -> CompletionResult:
        model = request.model or self.default_model
        try:
            with self._client.beta.messages.stream(
                model=model,
                max_tokens=request.max_output_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except self._anthropic.APIError as e:
            raise TranslationError(f"Anthropic API lỗi: {e}") from e

        if message.stop_reason == "refusal":
            raise TranslationError("Model từ chối dịch đoạn này (refusal).")
        if message.stop_reason == "max_tokens":
            raise TranslationError("Bản dịch bị cắt do chạm max_tokens; giảm NT_MAX_SEGMENT_CHARS.")

        text = "".join(b.text for b in message.content if b.type == "text")
        return CompletionResult(
            text=text,
            provider=self.name,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
