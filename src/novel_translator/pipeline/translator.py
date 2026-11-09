from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import CompletionRequest, GlossaryEntry, Novel
from ..domain.ports import LLMProvider
from .prompts import build_system_prompt
from .segmenter import segment


@dataclass
class TranslationOutput:
    title: str
    text: str
    provider: str
    model: str


class ChapterTranslator:
    """Dịch một chương: tách đoạn → gọi provider tuần tự → ghép lại."""

    def __init__(self, provider: LLMProvider, max_segment_chars: int, model: str | None = None):
        self.provider = provider
        self.max_segment_chars = max_segment_chars
        self.model = model

    def translate(
        self, novel: Novel, glossary: list[GlossaryEntry], title: str, text: str
    ) -> TranslationOutput:
        system = build_system_prompt(novel, glossary)
        used_model = self.model or self.provider.default_model

        title_result = self.provider.complete(
            CompletionRequest(system=system, user=title, model=self.model, max_output_tokens=1000)
        )
        parts: list[str] = []
        for seg in segment(text, self.max_segment_chars):
            result = self.provider.complete(
                CompletionRequest(system=system, user=seg, model=self.model)
            )
            parts.append(result.text.strip())
            used_model = result.model

        return TranslationOutput(
            title=title_result.text.strip(),
            text="\n".join(parts),
            provider=self.provider.name,
            model=used_model,
        )
