from novel_translator.domain.models import ChapterStatus, GlossaryEntry, Novel
from novel_translator.ingest.txt_loader import TxtLoader
from novel_translator.pipeline.prompts import build_system_prompt
from novel_translator.pipeline.segmenter import segment


def test_txt_loader_splits_chapters():
    chapters = TxtLoader.parse("第一章 开始\n内容一\n第二章 继续\n内容二")
    assert [c.title for c in chapters] == ["第一章 开始", "第二章 继续"]
    assert chapters[1].text == "内容二"


def test_segment_respects_max_chars_and_paragraphs():
    text = "\n".join(["a" * 20] * 5)
    segs = segment(text, 45)
    assert all(len(s) <= 45 for s in segs)
    assert "".join(s.replace("\n", "") for s in segs) == "a" * 100


def test_segment_hard_splits_long_paragraph():
    assert segment("x" * 120, 50) == ["x" * 50, "x" * 50, "x" * 20]


def test_system_prompt_includes_glossary():
    prompt = build_system_prompt(Novel(title="t"), [GlossaryEntry(1, "林动", "Lâm Động")])
    assert "林动 → Lâm Động" in prompt


def test_import_translate_export_flow(container, sample_txt, tmp_path):
    novel, n = container.library.import_novel(sample_txt)
    assert n == 2
    container.glossary.set_term(novel.id, "林动", "Lâm Động")

    ch = container.translation.translate_chapter(novel.id, 1)
    assert ch.status == ChapterStatus.TRANSLATED
    assert ch.provider == "echo"
    assert "林动站在山上" in ch.translated_text

    out = container.exports.export(novel.id, tmp_path / "out.txt")
    content = out.read_text(encoding="utf-8")
    assert "[VI] 第一章 少年" in content
    assert "第二章" not in content  # chương 2 chưa dịch thì không xuất
