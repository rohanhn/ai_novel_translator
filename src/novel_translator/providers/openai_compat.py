from __future__ import annotations

from ..domain.models import CompletionRequest, CompletionResult
from ..domain.ports import TranslationError


class OpenAICompatProvider:
    """Provider cho mọi API tương thích OpenAI Chat Completions (OpenAI, Ollama, vLLM, DeepSeek...)."""

    def __init__(
        self,
        name: str = "openai",
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
    ) -> None:
        try:
            import openai
        except ImportError as e:  # pragma: no cover
            raise TranslationError("Cài thêm: pip install 'novel-translator[openai]'") from e
        self._openai = openai
        self.name = name
        self.default_model = default_model
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, request: CompletionRequest) -> CompletionResult:
        model = request.model or self.default_model
        try:
            resp = self._client.chat.completions.create(
                model=model,
                max_tokens=request.max_output_tokens,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
            )
        except self._openai.OpenAIError as e:
            raise TranslationError(f"{self.name} API lỗi: {e}") from e

        choice = resp.choices[0]
        usage = resp.usage
        return CompletionResult(
            text=choice.message.content or "",
            provider=self.name,
            model=resp.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
