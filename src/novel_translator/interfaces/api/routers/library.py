"""Thư viện: danh sách, tải lên TXT, xem, xóa truyện (spec novel-library)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from ....container import Container, get_container
from ..schemas import LibraryItem, NovelOut

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_CHUNK = 1024 * 1024

router = APIRouter(prefix="/api/novels", tags=["library"])


@router.get("", response_model=list[LibraryItem])
def library(c: Container = Depends(get_container)):
    return [LibraryItem.of_summary(s) for s in c.library.overview()]


async def read_txt_upload(file: UploadFile) -> tuple[str, bytes]:
    """Kiểm tra dùng chung cho mọi upload TXT: đuôi `.txt`, ≤50 MB, không rỗng."""
    name = Path(file.filename or "novel.txt").name
    if not name.lower().endswith(".txt"):
        raise HTTPException(400, "Chỉ nhận file .txt")
    chunks, size = [], 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File lớn hơn 50 MB.")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(400, "File rỗng.")
    return name, b"".join(chunks)


@router.post("", response_model=NovelOut, status_code=201)
async def upload(file: UploadFile, title: str | None = Form(None),
                 lang: Literal["zh", "vi"] | None = Form(None),
                 c: Container = Depends(get_container)):
    """Lưu ngay (cho script): tách chương mặc định, ngôn ngữ tự nhận diện hoặc `lang`.
    Web dùng `/api/imports` (xem trước rồi xác nhận). Không có title → lấy tên file."""
    name, data = await read_txt_upload(file)
    res = c.library.import_bytes(data, (title or "").strip() or Path(name).stem, lang)
    return NovelOut.of(res.novel)


@router.get("/{novel_id}", response_model=NovelOut)
def get_novel(novel_id: int, c: Container = Depends(get_container)):
    return NovelOut.of(c.library.get_novel(novel_id))


@router.delete("/{novel_id}", status_code=204)
def delete_novel(novel_id: int, confirm: bool = False, c: Container = Depends(get_container)):
    """Xóa vĩnh viễn. Thiếu `?confirm=true` → 409 (không xóa gì)."""
    c.library.delete_novel(novel_id, confirm=confirm)
