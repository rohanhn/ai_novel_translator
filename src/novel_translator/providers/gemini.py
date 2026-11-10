"""Google Gemini qua SDK chính thức `google-genai` (BYOK: GEMINI_API_KEY của chủ sở hữu).

Theo kết quả spike (design D3):
- Dùng API `v1beta` (một số model chỉ có ở đây).
- Tắt retry bên trong SDK (attempts=1): chỉ ChainProvider được quyết định thử lại.
- Có timeout cho request; lỗi mạng/timeout → ProviderError.
- 429: quotaId chứa `PerDay` → DailyQuotaError (reset 0h Pacific ngày kế), kiểm tra TRƯỚC
  RetryInfo; còn lại → RateQuotaError (retry_after từ RetryInfo nếu có).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..domain.models import CompletionRequest
from ..domain.ports import (
    DailyQuotaError,
    ProviderError,
    RateQuotaError,
    RefusalError,
    StreamingProvider,
    TranslationError,
    TruncatedError,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
_REFUSAL_FINISH = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION",
                   "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT"}


def next_pacific_midnight(now: datetime | None = None) -> datetime:
    """Thời điểm Gemini reset quota ngày: 0h giờ Pacific của ngày kế tiếp (trả về UTC)."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(PACIFIC)
    reset = datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=PACIFIC)
    return reset.astimezone(timezone.utc)


def _duration_s(value: str | None) -> float | None:
    """'72913s' / '1.5s' → giây."""
    if not value:
        return None
    m = re.fullmatch(r"\s*([\d.]+)s\s*", str(value))
    return float(m.group(1)) if m else None


def _error_details(details: Any) -> list[dict]:
    if isinstance(details, dict):
        details = details.get("error", details).get("details", [])
    return [d for d in details or [] if isinstance(d, dict)]


def classify_api_error(code: int | None, status: str | None, message: str | None,
                       details: Any, now: datetime | None = None) -> TranslationError:
    """Chuyển lỗi API của Gemini (đã bóc từ SDK) thành lỗi phân loại của domain."""
    msg = (message or "").strip()
    if code == 429:
        items = _error_details(details)
        quota_ids = [
            v.get("quotaId", "")
            for d in items if d.get("@type", "").endswith("google.rpc.QuotaFailure")
            for v in d.get("violations", [])
        ]
        if any("PerDay" in q for q in quota_ids):
            return DailyQuotaError(f"Gemini hết quota ngày: {_first_line(msg)}",
                                   reset_at=next_pacific_midnight(now))
        retry = next((_duration_s(d.get("retryDelay")) for d in items
                      if d.get("@type", "").endswith("google.rpc.RetryInfo")), None)
        # Không phân loại được → coi là quota phút (an toàn hơn: backoff có giới hạn).
        return RateQuotaError(f"Gemini giới hạn tốc độ: {_first_line(msg)}", retry_after=retry)
    if code == 404:
        return ProviderError(f"Gemini 404 {status}: {_first_line(msg)} "
                             "→ kiểm tra tên model trong NT_CHAIN.")
    if code in (401, 403):
        return ProviderError(f"Gemini {code} {status}: API key không hợp lệ hoặc không có quyền "
                             "(kiểm tra GEMINI_API_KEY).")
    return ProviderError(f"Gemini {code} {status}: {_first_line(msg)}")


def _first_line(msg: str) -> str:
    return msg.splitlines()[0] if msg else ""


def _name(enum_value: Any) -> str | None:
    if enum_value is None:
        return None
    return getattr(enum_value, "name", None) or str(enum_value).rsplit(".", 1)[-1]


class GeminiProvider(StreamingProvider):
    name = "gemini"
    default_model = "gemini-3.5-flash"

    def __init__(self, api_key: str, timeout_s: float = 120.0,
                 thinking_level: str | None = "low", client: Any = None) -> None:
        from google.genai import errors, types

        self._errors = errors
        self._types = types
        self._thinking_level = thinking_level
        if client is None:
            from google import genai

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    timeout=int(timeout_s * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        self._client = client

    def _config(self, request: CompletionRequest):
        t = self._types
        return t.GenerateContentConfig(
            system_instruction=request.system or None,
            max_output_tokens=request.max_output_tokens,
            thinking_config=(t.ThinkingConfig(thinking_level=self._thinking_level)
                             if self._thinking_level else None),
        )

    def stream(self, request: CompletionRequest, policy=None, on_event=None) -> Iterator[str]:
        model = request.model or self.default_model
        try:
            chunks = self._client.models.generate_content_stream(
                model=model, contents=request.user, config=self._config(request)
            )
        except Exception as e:
            raise self._wrap(e) from e
        return self._iterate(chunks)

    def _iterate(self, chunks: Any) -> Iterator[str]:
        finish: str | None = None
        it = iter(chunks)
        while True:
            try:
                chunk = next(it)
            except StopIteration:
                break
            except Exception as e:
                raise self._wrap(e) from e
            feedback = getattr(chunk, "prompt_feedback", None)
            if feedback is not None and getattr(feedback, "block_reason", None):
                raise RefusalError(
                    f"Gemini chặn yêu cầu ({_name(feedback.block_reason)})."
                )
            candidates = getattr(chunk, "candidates", None) or []
            if candidates and getattr(candidates[0], "finish_reason", None):
                finish = _name(candidates[0].finish_reason)
            text = _chunk_text(chunk)
            if text:
                yield text
        if finish == "MAX_TOKENS":
            raise TruncatedError("Bản dịch bị cắt do chạm giới hạn token output (MAX_TOKENS).")
        if finish in _REFUSAL_FINISH:
            raise RefusalError(f"Gemini từ chối dịch ({finish}).")

    def _wrap(self, e: Exception) -> TranslationError:
        if isinstance(e, TranslationError):
            return e
        if isinstance(e, self._errors.APIError):
            return classify_api_error(e.code, e.status, e.message, e.details)
        # Lỗi mạng/timeout (httpx...) không đi qua APIError.
        return ProviderError(f"Gemini lỗi kết nối: {type(e).__name__}: {e}")


def _chunk_text(chunk: Any) -> str:
    """Lấy phần text (bỏ phần 'thought') của một chunk mà không gây warning của SDK."""
    candidates = getattr(chunk, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        if parts:
            return "".join(p.text for p in parts
                           if getattr(p, "text", None) and not getattr(p, "thought", False))
    return getattr(chunk, "text", None) or ""
