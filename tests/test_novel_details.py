"""Luật thông tin truyện (spec novel-library "Novel details validation")."""

from __future__ import annotations

import pytest

from novel_translator.domain.models import Novel
from novel_translator.domain.novel_details import (
    UNSET,
    NovelDetailsError,
    normalize_details,
)


def test_only_supplied_fields():
    assert normalize_details() == {}
    assert normalize_details(description="Mô tả") == {"description": "Mô tả"}


def test_title_trimmed_and_single_line():
    assert normalize_details(title="  Kiếm\n Lai  ") == {"title": "Kiếm Lai"}


@pytest.mark.parametrize("title", ["", "   ", "\n\t", None])
def test_blank_title_rejected(title):
    with pytest.raises(NovelDetailsError) as e:
        normalize_details(title=title)
    assert e.value.field == "title" and "không được để trống" in str(e.value)


def test_length_limits():
    assert normalize_details(title="a" * 200)["title"] == "a" * 200
    with pytest.raises(NovelDetailsError) as e:
        normalize_details(title="a" * 201)
    assert e.value.field == "title"
    with pytest.raises(NovelDetailsError) as e:
        normalize_details(author="b" * 101)
    assert e.value.field == "author"
    assert normalize_details(description="c" * 2000)["description"] == "c" * 2000
    with pytest.raises(NovelDetailsError) as e:
        normalize_details(description="c" * 2001)
    assert e.value.field == "description" and "2000" in str(e.value)


def test_length_counted_after_nfc():
    decomposed = "é" * 200  # "é" tách dấu: 400 code point, 200 ký tự sau NFC
    assert len(normalize_details(title=decomposed)["title"]) == 200


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_author_and_description_clear(value):
    assert normalize_details(author=value, description=value) == {
        "author": None, "description": None}


def test_description_keeps_line_breaks():
    out = normalize_details(description="  Dòng một  \r\nDòng hai\rDòng ba\n\n")
    assert out["description"] == "Dòng một\nDòng hai\nDòng ba"


def test_error_is_value_error_and_unset_is_falsy():
    assert issubclass(NovelDetailsError, ValueError)
    assert not UNSET and repr(UNSET) == "UNSET"


def test_new_novel_has_no_details():
    n = Novel(title="x")
    assert (n.author, n.description, n.has_cover) == (None, None, False)
