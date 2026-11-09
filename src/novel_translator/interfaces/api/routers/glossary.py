"""Bộ tên và hàng chờ đề xuất (spec glossary)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ....container import Container, get_container
from ..schemas import AcceptSuggestionIn, ChapterSummary, GlossaryIn, GlossaryOut, SuggestionOut

router = APIRouter(prefix="/api/novels/{novel_id}", tags=["glossary"])


@router.get("/glossary", response_model=list[GlossaryOut])
def list_terms(novel_id: int, c: Container = Depends(get_container)):
    c.library.get_novel(novel_id)
    return [GlossaryOut.of(g) for g in c.glossary.list_terms(novel_id)]


@router.put("/glossary", response_model=GlossaryOut)
def set_term(novel_id: int, body: GlossaryIn, c: Container = Depends(get_container)):
    """Thêm/sửa; đổi tên lan sang các chương đã dịch (chương đã biên tập chỉ gắn nhãn)."""
    c.library.get_novel(novel_id)
    return GlossaryOut.of(
        c.glossary.set_term(novel_id, body.source_term, body.target_term, body.note)
    )


@router.delete("/glossary/{source_term}", status_code=204)
def remove_term(novel_id: int, source_term: str, c: Container = Depends(get_container)):
    from ....application.services import NotFoundError

    c.library.get_novel(novel_id)
    if not c.glossary.remove_term(novel_id, source_term):
        raise NotFoundError(f"Không có thuật ngữ '{source_term}'")


@router.get("/glossary/{source_term}/chapters", response_model=list[ChapterSummary])
def affected_chapters(novel_id: int, source_term: str, c: Container = Depends(get_container)):
    """Chương đã dịch có chứa term (để chủ sở hữu chọn dịch lại)."""
    c.library.get_novel(novel_id)
    return [ChapterSummary.of(ch) for ch in c.glossary.affected_chapters(novel_id, source_term)]


@router.get("/suggestions", response_model=list[SuggestionOut])
def list_suggestions(novel_id: int, c: Container = Depends(get_container)):
    return [SuggestionOut.of(s) for s in c.glossary.list_suggestions(novel_id)]


@router.post("/suggestions/{source_term}/accept", response_model=GlossaryOut)
def accept(novel_id: int, source_term: str, body: AcceptSuggestionIn | None = None,
           c: Container = Depends(get_container)):
    target = body.target_term if body else None
    return GlossaryOut.of(c.glossary.accept_suggestion(novel_id, source_term, target))


@router.post("/suggestions/{source_term}/dismiss", status_code=204)
def dismiss(novel_id: int, source_term: str, c: Container = Depends(get_container)):
    c.glossary.dismiss_suggestion(novel_id, source_term)
