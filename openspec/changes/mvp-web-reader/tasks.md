# Tasks

## 1. Quy ước dự án và spike Gemini

- [ ] 1.1 Cập nhật `openspec/config.yaml` theo proposal: bỏ ràng buộc ngang tính năng CLI/API, đặt Gemini là provider mặc định với một request mỗi chương, thêm ràng buộc tuân thủ (API chính thức, không xoay vòng tài khoản, không lách rate limit, không tự động hóa giao diện chat, thư viện riêng tư); kiểm tra bằng `openspec validate mvp-web-reader --strict` vẫn pass
- [ ] 1.2 Sửa `docs/raw/base-idea.md` mục 4.2: thay dòng "Tự dịch chương kế: Không" bằng quy tắc buffer N+1 (tín hiệu đọc, một chương, chỉ dùng quota bước 1); kiểm tra bằng cách đối chiếu với spec `translation-prefetch`
- [ ] 1.3 Thêm dependency `google-genai`, `argon2-cffi` vào `pyproject.toml`; kiểm tra `uv pip install -e ".[dev]"` thành công
- [ ] 1.4 Spike: script tạm trong scratchpad gọi Gemini bằng key thật, ghi lại (đã ẩn key) mẫu response stream, mẫu lỗi 429 theo phút/ngày (nếu tái hiện được) và danh sách model free tier khả dụng; lưu mẫu lỗi thành fixture `tests/fixtures/gemini_errors/*.json`; kiểm tra fixture tồn tại và chốt giá trị mặc định cho `NT_CHAIN` trong design.md

## 2. Storage: migration và schema mới

- [ ] 2.1 Viết migration runner dùng `PRAGMA user_version`, thư mục `storage/migrations/`, chuyển schema v0.1 thành `001_initial.sql`, bật WAL + `busy_timeout`; kiểm tra bằng test: DB mới lên đúng version, DB v0.1 có sẵn dữ liệu nâng cấp không mất dữ liệu
- [ ] 2.2 Viết `002_mvp_web_reader.sql` theo bảng thay đổi trong design D6 (cột mới, bảng suggestions/progress/preferences/provider_usage/sessions, FK cascade); kiểm tra bằng test xóa novel làm mất toàn bộ bản ghi con
- [ ] 2.3 Cập nhật entity domain (`Chapter` thêm `glossary_version`, `chain_step`, `glossary_outdated`, `possible_omission`, status `edited`; `GlossarySuggestion`, `ReadingProgress`) và `SqliteRepository` tương ứng; kiểm tra bằng pytest các thao tác đọc/ghi mới
- [ ] 2.4 Thêm khi khởi động: chương `translating` đặt về `pending`; kiểm tra bằng test

## 3. Lỗi provider, streaming và Gemini

- [ ] 3.1 Thêm các lớp lỗi phân loại (`RefusalError`, `TruncatedError`, `RateQuotaError`, `DailyQuotaError`, `ProviderError`) và `LLMProvider.stream()` vào `domain/ports.py`; `complete()` mặc định ghép từ `stream()`; cập nhật `echo` để stream từng dòng và giả lập được từng loại lỗi; kiểm tra bằng unit test
- [ ] 3.2 Hiện thực `providers/gemini.py` (stream, phân loại 429 theo D3, finish reason → truncated/refusal, `reset_at` = 0h Pacific ngày kế); kiểm tra bằng unit test dựa trên fixture của 1.4, không gọi mạng
- [ ] 3.3 Bổ sung `stream()` và phân loại lỗi cho `anthropic` và `openai_compat`; kiểm tra bằng unit test với client giả
- [ ] 3.4 Đăng ký `gemini` trong registry, thêm cấu hình `NT_CHAIN`, `GEMINI_API_KEY`, `NT_CHAPTER_CHAR_LIMIT`; báo lỗi cấu hình khi thiếu key mà không in giá trị key; kiểm tra bằng test spec "Missing API key" và "Default chain"

## 4. Chuỗi fallback và quota

- [ ] 4.1 Port `QuotaTracker` + adapter SQLite `provider_usage` (đếm lượt thành công, ghi `exhausted_until`, tự hết hiệu lực khi qua thời điểm reset); kiểm tra bằng unit test có điều khiển đồng hồ
- [ ] 4.2 Hiện thực `providers/chain.py` với policy FOREGROUND/BACKGROUND theo D2 (bỏ qua bước đã hết quota, chuyển bước khi hết quota ngày, backoff tối đa 3 lần khi rate limit, dừng khi gặp lỗi khác hoặc lỗi giữa stream); kiểm tra bằng test cho mọi scenario trong spec `llm-providers` (Primary exhausted, Non-quota error, Whole chain exhausted, Recovered after wait)
- [ ] 4.3 Nối `ChainProvider` trong `container.py`, giữ khả năng override provider/model từ CLI; kiểm tra bằng test spec "Model override" và "Select provider per request"

## 5. Pipeline dịch một request

- [ ] 5.1 Viết prompt 3 phần (`<<TITLE>>`/`<<BODY>>`/`<<NAMES>>`, có ví dụ ngắn, glossary trong phần hướng dẫn cố định) và `SectionParser` streaming; kiểm tra bằng unit test với input bị cắt ở mọi vị trí, thiếu NAMES, thiếu BODY
- [ ] 5.2 Viết lại `ChapterTranslator` thành dạng phát sự kiện, cắt đoạn chỉ khi vượt `NT_CHAPTER_CHAR_LIMIT` (tiêu đề đi cùng đoạn đầu), kiểm tra độ đầy đủ (rỗng, truncated → lỗi; lệch >20% số đoạn → cờ `possible_omission`); kiểm tra bằng test các scenario spec `translation-pipeline`
- [ ] 5.3 Cập nhật `TranslationService`: lưu `glossary_version`, `chain_step`; quota hết thì để `pending`; không dịch lại chương `translated`/`edited` khi không có `force`; đưa tên đề xuất vào hàng chờ (bỏ qua term đã có hoặc đã bị dismiss); kiểm tra bằng test với provider `echo`
- [ ] 5.4 Cập nhật CLI `translate` theo chuỗi mới và cập nhật test CLI/API hiện có; kiểm tra toàn bộ `pytest -q` pass

## 6. Job manager và prefetch

- [ ] 6.1 Hiện thực `application/jobs.py` theo D4 (registry một job mỗi chương, hai làn, phát lại sự kiện cho subscriber muộn, nâng job đang chờ lên làn foreground, hủy job đang chờ); kiểm tra bằng test đồng thời dùng provider `echo` có độ trễ
- [ ] 6.2 Hiện thực `PrefetchService.on_reading_signal` với đầy đủ điều kiện chặn của spec `translation-prefetch` (N+1 không tồn tại / đã dịch / đang dịch / prefetch tắt / bước 1 hết quota) và chỉ chạy policy BACKGROUND; kiểm tra bằng test cho từng scenario của spec

## 7. Bộ tên, biên tập, tiến độ, tùy chọn

- [ ] 7.1 Service hàng chờ đề xuất tên (đồng ý / đồng ý kèm sửa / bỏ qua) và tăng `glossary_version` mỗi khi bộ tên thay đổi; kiểm tra bằng test các scenario "Suggestion review queue" và "Glossary versioning"
- [ ] 7.2 Lan truyền đổi tên theo D9 (chỉ chương có raw chứa term, regex ranh giới từ Unicode, chương edited chỉ gắn cờ, một transaction); kiểm tra bằng test "Rename applied", "Unrelated chapter untouched", "Partial word not replaced", "Edited chapter labelled only"
- [ ] 7.3 Service biên tập: sửa tay → `edited`; từ chối sửa chương chưa dịch; dịch lại chương edited phải có xác nhận; dịch lại thì xóa cờ outdated; kiểm tra bằng test spec `translation-editing`
- [ ] 7.4 Service tiến độ đọc + tùy chọn đọc (lưu server-side) + `last_read_at` và thứ tự thư viện; xóa truyện cần xác nhận và hủy prefetch đang chờ; kiểm tra bằng test spec `novel-library` và "Reading progress"

## 8. API, auth và SSE

- [ ] 8.1 Auth theo D7: lệnh `novel hash-password`, kiểm tra `NT_PASSWORD_HASH` lúc khởi động, login/logout, session hash trong DB, hết hạn sau 30 ngày không dùng, khóa 15 phút sau 5 lần sai theo IP (tin `X-Forwarded-For` từ `NT_TRUSTED_PROXY`), bắt buộc header `X-Requested-With` cho request thay đổi dữ liệu; kiểm tra bằng test mọi scenario spec `access-control`
- [ ] 8.2 Middleware `X-Robots-Tag` + `/robots.txt`; kiểm tra bằng test "Crawler request"
- [ ] 8.3 Tách router `/api` theo nhóm (library, chapters, glossary, progress/preferences, settings/quota) và nối vào services mới; mã lỗi: 401, 404, 429 kèm `reset_at`, 502 kèm loại lỗi; kiểm tra bằng test TestClient cho từng nhóm
- [ ] 8.4 Endpoint dịch trả 202 và SSE stream theo D5 (sự kiện `waiting_for_quota`, `paragraph`, `fallback_step`, sự kiện kết thúc; keep-alive; `X-Accel-Buffering: no`); kiểm tra bằng test "Subscribe mid-way" và test hai client cùng nhận một job
- [ ] 8.5 Endpoint `reading-signal` gọi `PrefetchService`, endpoint quota/usage cho màn hình cài đặt; kiểm tra bằng test API

## 9. Frontend SvelteKit

- [ ] 9.1 Khởi tạo `web/` (SvelteKit, `adapter-static`, `ssr=false`, fallback `index.html`), API client có cookie + `X-Requested-With`, tự chuyển sang `/login` khi gặp 401; FastAPI phục vụ `web/build` ở `/` với fallback deep link; kiểm tra `npm run build` thành công và test spec "Deep link"
- [ ] 9.2 Trang đăng nhập và thư viện (danh sách theo lần đọc gần nhất, upload `.txt` có báo lỗi kích thước, xóa có hộp xác nhận); kiểm tra thủ công trên viewport 360px và 1280px
- [ ] 9.3 Trang danh sách chương với nhãn trạng thái (pending/translating/translated/edited/failed/glossary-outdated/fallback/possible-omission) và nút đọc tiếp; kiểm tra thủ công với dữ liệu mẫu
- [ ] 9.4 Reader: hiển thị bản đã lưu; tự dịch kèm streaming qua SSE (gắn vào job đang chạy); thông báo hết quota có giờ reset; lỗi kèm nút thử lại; chuyển chương trước/sau; xem bản gốc; nhãn nguồn gốc bản dịch; kiểm tra thủ công với provider `echo` có độ trễ
- [ ] 9.5 Reader: đếm tín hiệu đọc (30 giây chương hiển thị, tạm dừng khi tab ẩn; cuộn ≥60%; nút "chuẩn bị chương tiếp") gửi một lần mỗi chương; lưu tiến độ debounce 5 giây + `sendBeacon` khi `pagehide`; khôi phục vị trí khi mở truyện; kiểm tra thủ công: đọc 30 giây làm chương N+1 chuyển sang translated
- [ ] 9.6 Chế độ biên tập trong reader (sửa tiêu đề/nội dung, lưu, xác nhận khi dịch lại chương đã sửa); kiểm tra thủ công
- [ ] 9.7 Trang bộ tên: danh sách term, sửa/xóa (cảnh báo số chương bị ảnh hưởng), hàng chờ đề xuất có nút đồng ý / sửa / bỏ qua; kiểm tra thủ công một lần đổi tên lan sang chương đã dịch
- [ ] 9.8 Trang cài đặt: theme (sáng/sepia/tối), cỡ chữ, giãn dòng (lưu server-side), công tắc prefetch, bảng lượt dùng và trạng thái quota theo từng bước, ghi chú về dữ liệu ở free tier, nút đăng xuất; kiểm tra thủ công rằng tùy chọn áp dụng trên trình duyệt khác
- [ ] 9.9 Kiểm tra mobile-first: không có thanh cuộn ngang ở 360px, vùng chạm của điều hướng ≥44px; kiểm tra bằng DevTools device mode

## 10. Đóng gói và triển khai

- [ ] 10.1 `Dockerfile` multi-stage (Node build `web/` → Python slim, uvicorn `--workers 1`, volume `/data`) và `docker-compose.yml` mẫu; kiểm tra `docker build` thành công và container trả `/health` OK
- [ ] 10.2 Viết `docs/DEPLOY.md`: biến môi trường, tạo hash mật khẩu, cấu hình reverse proxy cho subdomain (Nginx và Caddy, tắt buffering cho SSE), sao lưu/rollback DB; kiểm tra bằng cách làm theo tài liệu trên máy local với docker compose
- [ ] 10.3 Cập nhật `docs/ARCHITECTURE.md` (sơ đồ có web/SSE/job manager/chain, bảng lớp, backlog mới) và `CLAUDE.md` (lệnh build web, env mới); kiểm tra các lệnh ghi trong tài liệu chạy được

## 11. Kiểm tra tích hợp

- [ ] 11.1 Chạy `pytest -q` và `ruff check src tests` toàn bộ; kiểm tra pass
- [ ] 11.2 Kịch bản end-to-end trên container local với provider `echo`: đăng nhập → upload → mở chương 1 (thấy streaming) → đọc 30 giây → chương 2 đã dịch sẵn → đồng ý một tên đề xuất → đổi tên đó → chương bị ảnh hưởng có nhãn → sửa tay một chương → xóa truyện; kiểm tra mọi bước đúng spec
- [ ] 11.3 Smoke test với Gemini thật (key cá nhân): dịch 2 chương, xác nhận đếm lượt và nhãn model; kiểm tra màn hình quota hiển thị đúng số lượt
- [ ] 11.4 `openspec validate mvp-web-reader --strict` pass

## Workflow follow-up

- Triển khai lên VPS theo `docs/DEPLOY.md` sau khi review.
- Archive change bằng `/opsx:archive` để gộp delta vào `openspec/specs/`.
