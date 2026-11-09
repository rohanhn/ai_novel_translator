# Fixture lỗi / stream Gemini

Ghi từ API thật ngày 2026-11-09 (google-genai 3.0.0, `api_version=v1beta`, key free tier). Key đã được ẩn.

| File | Nguồn | Ý nghĩa |
|---|---|---|
| `gemini_errors/daily_quota_429.json` | `gemini-3.1-pro-preview` (free tier limit 0) | 429 `RESOURCE_EXHAUSTED`; `QuotaFailure` có cả quotaId `...PerDay...` lẫn `...PerMinute...`, kèm `RetryInfo.retryDelay` (~20 giờ). Phải phân loại là **quota ngày** (kiểm tra `PerDay` trước `RetryInfo`). |
| `gemini_errors/model_retired_404.json` | `gemini-2.5-pro` | 404 `NOT_FOUND` "no longer available to new users" → lỗi cấu hình model, không phải quota. |
| `gemini_stream/ok_three_sections.json` | `gemini-3.1-flash-lite` | Stream thành công theo định dạng `<<TITLE>>/<<BODY>>/<<NAMES>>`; chunk cuối có `text=""` và `finish_reason=STOP`. |
| `gemini_stream/max_tokens.json` | `gemini-3.1-flash-lite`, `max_output_tokens=8` | Chunk cuối `finish_reason=MAX_TOKENS` → `TruncatedError`. |

Chưa tái hiện được 429 **chỉ theo phút** (cần gửi dồn request để vượt RPM; không làm để tránh đốt quota). Lỗi mạng/timeout không đi qua `APIError` mà là `httpx2.ReadTimeout`; 503 `UNAVAILABLE` cũng đã gặp khi gọi `gemini-3.7-flash`.
