from novel_translator.domain.models import ChapterStatus, GlossaryEntry, Novel
from novel_translator.ingest.txt_loader import TxtLoader
from novel_translator.pipeline.prompts import build_system_prompt
from novel_translator.pipeline.segmenter import segment


def test_txt_loader_reads_utf8_with_bom(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("\ufeff第一章 开始\n内容一".encode())
    assert TxtLoader().read_text(p) == "第一章 开始\n内容一"


def test_txt_loader_falls_back_to_gb18030(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("第一章 开始\n林动".encode("gb18030"))
    assert TxtLoader().read_text(p) == "第一章 开始\n林动"


def test_txt_loader_explicit_encoding(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("Chương 1".encode("utf-16"))
    assert TxtLoader(encoding="utf-16").read_text(p) == "Chương 1"


def test_txt_loader_undecodable(tmp_path):
    import pytest
    p = tmp_path / "a.txt"
    p.write_bytes(b"\xff\xfe\x00\xd8\x81")
    with pytest.raises(ValueError, match="encoding"):
        TxtLoader().read_text(p)


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
    res = container.library.import_novel(sample_txt)
    novel, n = res.novel, res.chapters
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
