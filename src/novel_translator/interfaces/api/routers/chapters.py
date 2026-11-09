"""Chương: danh sách, đọc, biên tập, yêu cầu dịch (spec interfaces, translation-editing)."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from ....application.jobs import JobEvent, Lane
from ....application.services import NotFoundError
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


KEEPALIVE_S = 15.0
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(seq: int, ev: JobEvent) -> str:
    data = json.dumps(ev.data, ensure_ascii=False)
    return f"id: {seq}\nevent: {ev.type}\ndata: {data}\n\n"


def _event_stream(events: Iterator[JobEvent | None]) -> Iterator[str]:
    seq = 0
    for ev in events:
        if ev is None:
            yield ": keep-alive\n\n"
            continue
        seq += 1
        yield _sse(seq, ev)


@router.get("/{index}/stream", response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}}}})
def stream(novel_id: int, index: int, c: Container = Depends(get_container)):
    """SSE của job dịch chương (design D5): phát lại sự kiện đã có (subscriber vào muộn), rồi
    `title`/`paragraph`/`waiting_for_quota`/`fallback_step`, kết thúc bằng đúng một sự kiện
    `completed`/`failed`/`quota_exhausted`/`cancelled`. Keep-alive mỗi 15 giây.

    Không có job (kể cả job vừa kết thúc): chương đã dịch → chỉ một sự kiện `completed`;
    còn lại → 404."""
    job = c.jobs.latest(novel_id, index)
    if job is not None:
        events: Iterator[JobEvent | None] = job.subscribe(heartbeat=KEEPALIVE_S)
    else:
        ch = c.library.get_chapter(novel_id, index)
        if ch.status not in (ChapterStatus.TRANSLATED, ChapterStatus.EDITED):
            raise NotFoundError(f"Chương {index} không có bản dịch nào đang chạy")
        events = iter([JobEvent("completed", {
            "status": ch.status.value, "title": ch.translated_title, "provider": ch.provider,
            "model": ch.model, "chain_step": ch.chain_step,
            "possible_omission": ch.possible_omission})])
    return StreamingResponse(_event_stream(events), media_type="text/event-stream",
                             headers=SSE_HEADERS)
