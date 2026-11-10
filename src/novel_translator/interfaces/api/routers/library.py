"""Thư viện: danh sách, tải lên TXT, xem, xóa truyện (spec novel-library)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from ....container import Container, get_container
from ..schemas import LibraryItem, NovelOut

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_CHUNK = 1024 * 1024

router = APIRouter(prefix="/api/novels", tags=["library"])


@router.get("", response_model=list[LibraryItem])
def library(c: Container = Depends(get_container)):
    return [LibraryItem.of_summary(s) for s in c.library.overview()]


@router.post("", response_model=NovelOut, status_code=201)
async def upload(file: UploadFile, title: str | None = Form(None),
                 c: Container = Depends(get_container)):
    """Nhận file `.txt` (≤50 MB). Ghi ra file tạm để dùng đúng quy tắc tách chương và đoán
    encoding của lệnh import. Không có title → lấy tên file."""
    name = Path(file.filename or "novel.txt").name
    if not name.lower().endswith(".txt"):
        raise HTTPException(400, "Chỉ nhận file .txt")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        size = 0
        with path.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "File lớn hơn 50 MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "File rỗng.")
        novel = c.library.import_novel(path, (title or "").strip() or None).novel
    return NovelOut.of(novel)


@router.get("/{novel_id}", response_model=NovelOut)
def get_novel(novel_id: int, c: Container = Depends(get_container)):
    return NovelOut.of(c.library.get_novel(novel_id))


@router.delete("/{novel_id}", status_code=204)
def delete_novel(novel_id: int, confirm: bool = False, c: Container = Depends(get_container)):
    """Xóa vĩnh viễn. Thiếu `?confirm=true` → 409 (không xóa gì)."""
    c.library.delete_novel(novel_id, confirm=confirm)
