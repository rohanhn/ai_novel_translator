"""LibraryService: sửa thông tin truyện và ảnh bìa (spec novel-library "Edit novel details",
"Novel cover upload")."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from novel_translator.application.services import NotFoundError
from novel_translator.domain.novel_details import InvalidImageError, NovelDetailsError


def _png(w=300, h=450) -> bytes:
    out = BytesIO()
    Image.new("RGB", (w, h), "teal").save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def novel(container, tmp_path):
    p = tmp_path / "kiem-lai-full.txt"
    p.write_text("第1章 甲\n内容一\n第2章 乙\n内容二\n", encoding="utf-8")
    n = container.library.import_novel(p).novel
    container.glossary.set_term(n.id, "陈平安", "Trần Bình An")
    container.reader.save_progress(n.id, 2, 0.5)
    return n


def _snapshot(c, nid):
    return ([(ch.index, ch.title, ch.source_text, ch.status) for ch in
             c.library.list_chapters(nid)],
            [(g.source_term, g.target_term) for g in c.glossary.list_terms(nid)],
            c.reader.get_progress(nid))


def test_rename_and_add_author_keeps_everything_else(container, novel):
    before = _snapshot(container, novel.id)
    n = container.library.update_details(novel.id, title=" Kiếm Lai ",
                                         author="Phong Hỏa Hí Chư Hầu")
    assert (n.title, n.author, n.description) == ("Kiếm Lai", "Phong Hỏa Hí Chư Hầu", None)
    assert container.library.get_novel(novel.id).title == "Kiếm Lai"
    assert _snapshot(container, novel.id) == before
    assert container.provider_factory(None).calls == []


def test_partial_update_and_clear(container, novel):
    container.library.update_details(novel.id, author="A", description="Dòng 1\nDòng 2")
    n = container.library.update_details(novel.id, description="Mới")
    assert (n.title, n.author, n.description) == ("kiem-lai-full", "A", "Mới")
    n = container.library.update_details(novel.id, author="")
    assert n.author is None and n.description == "Mới"


def test_invalid_changes_nothing(container, novel):
    with pytest.raises(NovelDetailsError) as e:
        container.library.update_details(novel.id, author="B", title="   ")
    assert e.value.field == "title"
    assert container.library.get_novel(novel.id).author is None
    with pytest.raises(ValueError, match="ít nhất một trường"):
        container.library.update_details(novel.id)
    with pytest.raises(NotFoundError):
        container.library.update_details(999_999, title="x")


def test_export_uses_new_title(container, novel, tmp_path):
    container.library.update_details(novel.id, title="Kiếm Lai")
    for ch in container.library.list_chapters(novel.id):  # cần chương đã dịch để xuất
        ch.translated_text = "Bản dịch."
        ch.status = ch.status.TRANSLATED
        container.repo.update_chapter(ch)
    out = container.exports.export(novel.id, tmp_path / "out.txt")
    assert out.read_text(encoding="utf-8").startswith("Kiếm Lai")


def test_cover_set_replace_remove(container, novel):
    n1 = container.library.set_cover(novel.id, _png())
    assert n1.has_cover
    img = container.library.get_cover(novel.id)
    assert (img.mime, img.width, img.height) == ("image/webp", 300, 450)
    n2 = container.library.set_cover(novel.id, _png(1200, 1800))
    assert n2.cover_updated_at > n1.cover_updated_at
    assert container.library.get_cover(novel.id).width == 600
    n3 = container.library.remove_cover(novel.id)
    assert not n3.has_cover
    with pytest.raises(NotFoundError):
        container.library.get_cover(novel.id)
    assert not container.library.remove_cover(novel.id).has_cover  # gỡ lần hai vẫn được


def test_invalid_cover_keeps_previous(container, novel):
    container.library.set_cover(novel.id, _png())
    with pytest.raises(InvalidImageError):
        container.library.set_cover(novel.id, b"not an image")
    assert container.library.get_cover(novel.id).width == 300
    with pytest.raises(NotFoundError):
        container.library.set_cover(999_999, _png())
