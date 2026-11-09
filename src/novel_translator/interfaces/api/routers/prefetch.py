"""Tín hiệu đọc → dịch trước chương N+1 (spec translation-prefetch)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ....application.prefetch import ReadingSignal
from ....container import Container, get_container

router = APIRouter(prefix="/api/novels/{novel_id}", tags=["prefetch"])


class SignalIn(BaseModel):
    signal: ReadingSignal  # visible_30s | scrolled_60 | explicit


class DecisionOut(BaseModel):
    started: bool
    reason: str
    chapter_index: int | None


@router.post("/chapters/{index}/reading-signal", response_model=DecisionOut)
def reading_signal(novel_id: int, index: int, body: SignalIn,
                   c: Container = Depends(get_container)):
    """Chủ sở hữu thực sự đang đọc chương `index`: có thể bắt đầu dịch trước chương kế tiếp.
    `reason` cho biết vì sao không bắt đầu (đã dịch, đang dịch, tắt prefetch, hết quota...)."""
    d = c.prefetch.on_reading_signal(novel_id, index, body.signal)
    return DecisionOut(started=d.started, reason=d.reason, chapter_index=d.chapter_index)


@router.post("/leave")
def leave(novel_id: int, c: Container = Depends(get_container)):
    """Rời truyện: hủy prefetch chưa gửi request; cái đang chạy vẫn chạy xong và được lưu."""
    c.library.get_novel(novel_id)
    return {"cancelled": c.prefetch.on_leave(novel_id)}
