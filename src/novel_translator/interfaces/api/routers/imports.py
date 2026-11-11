"""Import TXT có xem trước (design D3, spec novel-library "Upload novel from the web")."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from ....container import Container, get_container
from ..schemas import (
    ImportAdjustIn,
    ImportCommitIn,
    ImportLinesOut,
    ImportPreview,
    NovelOut,
    UpdateApplyIn,
    UpdateIn,
    UpdatePreviewOut,
    UpdateResultOut,
)
from .library import read_txt_upload

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("", response_model=ImportPreview, status_code=201)
async def create(file: UploadFile, novel_id: Annotated[int | None, Form()] = None,
                 c: Container = Depends(get_container)):
    """Nhận file, tách chương, trả bản xem trước. Chưa lưu gì. `novel_id`: bản xem trước để
    cập nhật chương của truyện đó (spec `chapter-update`); truyện không tồn tại → 404."""
    name, data = await read_txt_upload(file)
    return ImportPreview.of(c.imports.create(name, data, novel_id=novel_id))


@router.get("/{draft_id}", response_model=ImportPreview)
def get(draft_id: str, c: Container = Depends(get_container)):
    return ImportPreview.of(c.imports.get(draft_id))


@router.put("/{draft_id}", response_model=ImportPreview)
def adjust(draft_id: str, body: ImportAdjustIn, c: Container = Depends(get_container)):
    """Áp ranh giới (số dòng) và lựa chọn phần mở đầu; trả bản xem trước tính lại."""
    return ImportPreview.of(c.imports.adjust(draft_id, body.boundaries, body.keep_front_matter))


@router.get("/{draft_id}/lines", response_model=ImportLinesOut)
def lines(draft_id: str, start: int = Query(0, ge=0), count: int = Query(200, ge=1, le=500),
          c: Container = Depends(get_container)):
    return ImportLinesOut(start=start, lines=c.imports.lines(draft_id, start, count))


@router.post("/{draft_id}/commit", response_model=NovelOut, status_code=201)
def commit(draft_id: str, body: ImportCommitIn, c: Container = Depends(get_container)):
    """Tạo truyện từ ranh giới gửi kèm rồi xóa bản xem trước. Hết hạn → 410."""
    res = c.imports.commit(draft_id, body.title, body.lang, body.boundaries,
                           body.keep_front_matter)
    return NovelOut.of(res.novel)


@router.delete("/{draft_id}", status_code=204)
def discard(draft_id: str, c: Container = Depends(get_container)):
    c.imports.discard(draft_id)


@router.post("/{draft_id}/update-preview", response_model=UpdatePreviewOut)
def update_preview(draft_id: str, body: UpdateIn, c: Container = Depends(get_container)):
    """Thay đổi nếu áp cập nhật với chế độ đã chọn (spec `chapter-update`). Không ghi gì."""
    return UpdatePreviewOut.of(c.chapter_updates.preview(
        draft_id, body.mode, body.boundaries, body.keep_front_matter, body.start, body.delete))


@router.post("/{draft_id}/update", response_model=UpdateResultOut)
def update(draft_id: str, body: UpdateApplyIn, c: Container = Depends(get_container)):
    """Áp cập nhật. `revision` lệch (truyện vừa đổi) → 409 `stale_preview`."""
    return UpdateResultOut.of(c.chapter_updates.apply(
        draft_id, body.mode, body.boundaries, body.keep_front_matter, body.start, body.delete,
        body.revision))
