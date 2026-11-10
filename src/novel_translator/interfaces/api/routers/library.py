"""Thư viện: danh sách, tải lên TXT, xem, xóa truyện (spec novel-library)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from ....container import Container, get_container
from ....domain.novel_details import COVER_MAX_BYTES
from ..schemas import CoverFetchIn, LibraryItem, NovelDetailsIn, NovelOut

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_CHUNK = 1024 * 1024

router = APIRouter(prefix="/api/novels", tags=["library"])
covers_router = APIRouter(prefix="/api/covers", tags=["library"])


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


# --- thông tin truyện + ảnh bìa (spec novel-library "Edit novel details", "Novel cover …") ---

@router.patch("/{novel_id}", response_model=NovelOut)
def update_details(novel_id: int, body: NovelDetailsIn, c: Container = Depends(get_container)):
    """Chỉ đổi trường có trong body. `author`/`description` rỗng hoặc null = xoá."""
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    return NovelOut.of(c.library.update_details(novel_id, **fields))


async def _read_image(file: UploadFile) -> bytes:
    chunks, size = [], 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > COVER_MAX_BYTES:
            raise HTTPException(413, "Ảnh lớn hơn 10 MB.")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(400, "File rỗng.")
    return b"".join(chunks)


@router.put("/{novel_id}/cover", response_model=NovelOut)
async def put_cover(novel_id: int, file: UploadFile, c: Container = Depends(get_container)):
    """Thay ảnh bìa (JPG/PNG/WebP ≤10 MB). Xử lý ảnh chạy trong threadpool."""
    data = await _read_image(file)
    return NovelOut.of(await run_in_threadpool(c.library.set_cover, novel_id, data))


@router.delete("/{novel_id}/cover", status_code=204)
def delete_cover(novel_id: int, c: Container = Depends(get_container)):
    c.library.remove_cover(novel_id)


@router.get("/{novel_id}/cover")
def get_cover(novel_id: int, c: Container = Depends(get_container)):
    """Ảnh bìa đã lưu. URL có `?v=` nên cache lâu được; chỉ cache riêng (private)."""
    img = c.library.get_cover(novel_id)
    return Response(img.data, media_type=img.mime,
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


@covers_router.post("/fetch")
def fetch_cover(body: CoverFetchIn, c: Container = Depends(get_container)):
    """Tải ảnh từ link (server tải, chặn địa chỉ nội bộ) rồi trả ảnh đã xử lý để XEM TRƯỚC.
    Không lưu gì; lưu bằng `PUT /api/novels/{id}/cover` với chính ảnh này."""
    img = c.library.preview_cover_from_url(body.url)
    return Response(img.data, media_type=img.mime, headers={
        "Cache-Control": "no-store", "X-Cover-Width": str(img.width),
        "X-Cover-Height": str(img.height)})
