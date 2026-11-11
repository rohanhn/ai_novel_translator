"""Ánh xạ lỗi application/provider → mã HTTP (spec interfaces)."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.chapter_update import (
    LanguageMismatchError,
    NothingNewError,
    StalePreviewError,
    StartRequiredError,
)
from ...application.imports import DraftExpiredError
from ...application.services import (
    ConfirmationRequiredError,
    InvalidOperationError,
    NotFoundError,
    NovelBusyError,
    PreTranslatedError,
)
from ...domain.novel_details import CoverFetchError, InvalidImageError, NovelDetailsError
from ...domain.ports import DailyQuotaError, RateQuotaError, TranslationError


def _json(status: int, detail: str, **extra) -> JSONResponse:
    headers = extra.pop("headers", None)
    return JSONResponse(status_code=status, content={"detail": detail, **extra}, headers=headers)


async def _not_found(_: Request, e: NotFoundError):
    return _json(404, str(e))


async def _confirmation(_: Request, e: ConfirmationRequiredError):
    return _json(409, str(e), code="confirmation_required")


async def _pretranslated(_: Request, e: PreTranslatedError):
    return _json(409, str(e), code="pretranslated")


async def _draft_expired(_: Request, e: DraftExpiredError):
    return _json(410, str(e), code="draft_expired")


async def _language_mismatch(_: Request, e: LanguageMismatchError):
    return _json(422, str(e), code="language_mismatch")


async def _start_required(_: Request, e: StartRequiredError):
    return _json(422, str(e), code="start_required")


async def _nothing_new(_: Request, e: NothingNewError):
    return _json(409, str(e), code="nothing_new")


async def _stale_preview(_: Request, e: StalePreviewError):
    return _json(409, str(e), code="stale_preview")


async def _novel_busy(_: Request, e: NovelBusyError):
    return _json(409, str(e), code="novel_busy")


async def _invalid(_: Request, e: InvalidOperationError):
    return _json(409, str(e), code="invalid_operation")


async def _novel_details(_: Request, e: NovelDetailsError):
    return _json(400, str(e), field=e.field)


async def _invalid_image(_: Request, e: InvalidImageError):
    return _json(400, str(e), field="cover")


async def _cover_fetch(_: Request, e: CoverFetchError):
    return _json(400, str(e), field="cover_url", reason=e.reason)


async def _bad_request(_: Request, e: ValueError):
    return _json(400, str(e))


async def _daily_quota(_: Request, e: DailyQuotaError):
    reset = e.reset_at
    headers = None
    if reset is not None:
        wait = (reset - datetime.now(timezone.utc)).total_seconds()
        headers = {"Retry-After": str(max(1, math.ceil(wait)))}
    return _json(429, str(e), category=e.category,
                 reset_at=reset.isoformat() if reset else None, headers=headers)


async def _rate_quota(_: Request, e: RateQuotaError):
    headers = {"Retry-After": str(math.ceil(e.retry_after))} if e.retry_after else None
    return _json(429, str(e), category=e.category, retry_after=e.retry_after, headers=headers)


async def _provider(_: Request, e: TranslationError):
    return _json(502, str(e), category=e.category)


def install(app: FastAPI) -> None:
    # Starlette chọn handler theo MRO nên lớp con cụ thể hơn được ưu tiên.
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(ConfirmationRequiredError, _confirmation)
    app.add_exception_handler(PreTranslatedError, _pretranslated)
    app.add_exception_handler(LanguageMismatchError, _language_mismatch)
    app.add_exception_handler(StartRequiredError, _start_required)
    app.add_exception_handler(NothingNewError, _nothing_new)
    app.add_exception_handler(StalePreviewError, _stale_preview)
    app.add_exception_handler(NovelBusyError, _novel_busy)
    app.add_exception_handler(InvalidOperationError, _invalid)
    app.add_exception_handler(DraftExpiredError, _draft_expired)
    app.add_exception_handler(NovelDetailsError, _novel_details)
    app.add_exception_handler(InvalidImageError, _invalid_image)
    app.add_exception_handler(CoverFetchError, _cover_fetch)
    app.add_exception_handler(ValueError, _bad_request)
    app.add_exception_handler(DailyQuotaError, _daily_quota)
    app.add_exception_handler(RateQuotaError, _rate_quota)
    app.add_exception_handler(TranslationError, _provider)
