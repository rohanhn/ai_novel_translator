"""Tiến độ đọc theo truyện và tùy chọn đọc dùng chung mọi thiết bị (spec web-reader)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Response

from ....container import Container, get_container
from ..schemas import ProgressIn, ProgressOut

router = APIRouter(prefix="/api", tags=["reading"])


@router.get("/novels/{novel_id}/progress", response_model=ProgressOut | None)
def get_progress(novel_id: int, response: Response, c: Container = Depends(get_container)):
    p = c.reader.get_progress(novel_id)
    if p is None:
        response.status_code = 204
        return None
    return ProgressOut.of(p)


@router.put("/novels/{novel_id}/progress", response_model=ProgressOut)
def save_progress(novel_id: int, body: ProgressIn, c: Container = Depends(get_container)):
    return ProgressOut.of(c.reader.save_progress(novel_id, body.chapter_index, body.position))


@router.get("/preferences")
def get_preferences(c: Container = Depends(get_container)) -> dict[str, Any]:
    return c.reader.get_preferences()


@router.patch("/preferences")
def set_preferences(changes: Annotated[dict[str, Any], Body()],
                    c: Container = Depends(get_container)) -> dict[str, Any]:
    """Chỉ đổi các khóa được gửi; giá trị sai → 400, không lưu gì."""
    return c.reader.set_preferences(changes)
