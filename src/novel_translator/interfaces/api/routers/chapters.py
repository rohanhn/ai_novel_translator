"""Chương: danh sách, đọc, biên tập, yêu cầu dịch (spec interfaces, translation-editing)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ....application.jobs import Lane
from ....container import Container, get_container
from ....domain.models import ChapterStatus
from ..schemas import ChapterEditIn, ChapterOut, ChapterSummary, TranslateAccepted, TranslateIn

router = APIRouter(prefix="/api/novels/{novel_id}/chapters", tags=["chapters"])


@router.get("", response_model=list[ChapterSummary])
def list_chapters(novel_id: int, c: Container = Depends(get_container)):
    return [ChapterSummary.of(ch) for ch in c.library.list_chapters(novel_id)]


@router.get("/{index}", response_model=ChapterOut)
def get_chapter(novel_id: int, index: int, c: Container = Depends(get_container)):
    return ChapterOut.of(c.library.get_chapter(novel_id, index))


@router.put("/{index}", response_model=ChapterOut)
def edit_chapter(novel_id: int, index: int, body: ChapterEditIn,
                 c: Container = Depends(get_container)):
    return ChapterOut.of(
        c.editing.edit_chapter(novel_id, index, body.translated_title, body.translated_text)
    )


def stream_url(novel_id: int, index: int) -> str:
    return f"/api/novels/{novel_id}/chapters/{index}/stream"


@router.post("/{index}/translate", status_code=202,
             responses={200: {"model": ChapterOut}, 202: {"model": TranslateAccepted}})
def translate(novel_id: int, index: int, body: TranslateIn,
              c: Container = Depends(get_container)):
    """Kiểm tra trước (404/409/400/429/502), rồi tạo job foreground hoặc gắn vào job đang có
    và trả 202 kèm URL stream. Chương đã có bản dịch và không `force` → 200 kèm chương."""
    job = c.jobs.get(novel_id, index)
    if job is None:
        ch = c.translation.preflight(
            novel_id, index, provider=body.provider, model=body.model, force=body.force,
            confirm_discard_edits=body.confirm_discard_edits,
        )
        if ch.status in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED) and not body.force:
            return JSONResponse(ChapterOut.of(ch).model_dump(mode="json"), status_code=200)
    job = c.jobs.submit(novel_id, index, Lane.FOREGROUND, force=body.force,
                        confirm_discard_edits=body.confirm_discard_edits,
                        provider=body.provider, model=body.model)
    return TranslateAccepted(state=job.state.value, lane=job.lane.value,
                             stream_url=stream_url(novel_id, index))
