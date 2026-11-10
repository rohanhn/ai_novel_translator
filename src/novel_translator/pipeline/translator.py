"""Dịch một chương bằng một request (design D1): tiêu đề + nội dung + đề xuất tên.

Chỉ cắt đoạn khi nội dung vượt `chapter_char_limit`; tiêu đề đi cùng đoạn đầu. Text được
phát dần qua `on_event` (Title / Paragraph / ChainEvent) trong lúc model sinh ra.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..domain.models import ChainEvent, ChainPolicy, CompletionRequest, GlossaryEntry, Novel
from ..domain.ports import LLMProvider, MalformedOutputError
from .prompts import build_system_prompt, build_user_prompt
from .sections import NameItem, Names, Paragraph, SectionParser, Title
from .segmenter import segment, split_paragraphs

OMISSION_TOLERANCE = 0.20
TranslatorEvent = Title | Paragraph | ChainEvent


@dataclass
class TranslationOutput:
    title: str | None
    text: str
    provider: str
    model: str
    chain_step: int | None = None
    names: list[NameItem] = field(default_factory=list)
    possible_omission: bool = False


def output_token_budget(source_chars: int) -> int:
    """Ước lượng giới hạn token output: tiếng Việt dài hơn nhiều so với chữ Hán nguồn."""
    return min(65536, max(4096, source_chars * 3))


def is_possible_omission(source_paragraphs: int, translated_paragraphs: int) -> bool:
    if source_paragraphs == 0:
        return False
    return abs(translated_paragraphs - source_paragraphs) / source_paragraphs > OMISSION_TOLERANCE


class ChapterTranslator:
    def __init__(self, provider: LLMProvider, chapter_char_limit: int, model: str | None = None):
        self.provider = provider
        self.chapter_char_limit = chapter_char_limit
        self.model = model

    def segments(self, text: str) -> list[str]:
        body = "\n".join(split_paragraphs(text))
        if len(body) <= self.chapter_char_limit:
            return [body]
        return segment(body, self.chapter_char_limit)

    def translate(
        self,
        novel: Novel,
        glossary: list[GlossaryEntry],
        title: str,
        text: str,
        policy: ChainPolicy = ChainPolicy.FOREGROUND,
        on_event: Callable[[TranslatorEvent], None] | None = None,
    ) -> TranslationOutput:
        emit = on_event or (lambda e: None)
        system = build_system_prompt(novel, glossary)  # giống hệt giữa các đoạn → cache được
        out_title: str | None = None
        paragraphs: list[str] = []
        names: list[NameItem] = []
        used_provider, used_model = self.provider.name, self.model or self.provider.default_model
        used_step: int | None = None

        for i, seg in enumerate(self.segments(text)):
            request = CompletionRequest(
                system=system,
                user=build_user_prompt(seg, title if i == 0 else None),
                model=self.model,
                max_output_tokens=output_token_budget(len(seg)),
            )
            run = self.provider.stream(request, policy=policy, on_event=emit)
            parser = SectionParser()
            for chunk in run:
                self._collect(parser.feed(chunk), emit, paragraphs, names)
            self._collect(parser.finish(), emit, paragraphs, names)
            if i == 0:
                out_title = parser.title
            used_provider = getattr(run, "provider", None) or used_provider
            used_model = getattr(run, "model", None) or request.model or used_model
            used_step = getattr(run, "step", None) or used_step

        if not paragraphs:
            raise MalformedOutputError("Bản dịch rỗng: model không trả về nội dung chương.")
        return TranslationOutput(
            title=out_title,
            text="\n".join(paragraphs),
            provider=used_provider,
            model=used_model,
            chain_step=used_step,
            names=_dedupe(names),
            possible_omission=is_possible_omission(len(split_paragraphs(text)), len(paragraphs)),
        )

    @staticmethod
    def _collect(events, emit, paragraphs: list[str], names: list[NameItem]) -> None:
        for ev in events:
            if isinstance(ev, Names):
                names.extend(ev.items)
                continue
            if isinstance(ev, Paragraph):
                paragraphs.append(ev.text)
            emit(ev)


def _dedupe(items: list[NameItem]) -> list[NameItem]:
    seen: dict[str, NameItem] = {}
    for it in items:
        seen.setdefault(it.source, it)
    return list(seen.values())
