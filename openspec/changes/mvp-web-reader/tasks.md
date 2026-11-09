# Tasks

## 1. Quy ước dự án và spike Gemini

- [x] 1.1 Cập nhật `openspec/config.yaml` theo proposal: bỏ ràng buộc ngang tính năng CLI/API, đặt Gemini là provider mặc định với một request mỗi chương, đổi stack từ SQLite sang PostgreSQL (test cần Postgres local), thêm ràng buộc tuân thủ (API chính thức, không xoay vòng tài khoản, không lách rate limit, không tự động hóa giao diện chat, thư viện riêng tư); kiểm tra bằng `openspec validate mvp-web-reader --strict` vẫn pass
- [x] 1.2 Sửa `docs/raw/base-idea.md` mục 4.2: thay dòng "Tự dịch chương kế: Không" bằng quy tắc buffer N+1 (tín hiệu đọc, một chương, chỉ dùng quota bước 1); kiểm tra bằng cách đối chiếu với spec `translation-prefetch`
- [x] 1.3 Thêm dependency `google-genai`, `argon2-cffi`, `psycopg[binary,pool]` vào `pyproject.toml`; kiểm tra `uv pip install -e ".[dev]"` thành công
- [x] 1.4 Spike: script tạm trong scratchpad gọi Gemini bằng key thật, ghi lại (đã ẩn key) mẫu response stream, mẫu lỗi 429 theo phút/ngày (nếu tái hiện được) và danh sách model free tier khả dụng; lưu mẫu lỗi thành fixture `tests/fixtures/gemini_errors/*.json`; kiểm tra fixture tồn tại và chốt giá trị mặc định cho `NT_CHAIN` trong design.md

## 2. Storage: PostgreSQL, migration và schema mới

- [x] 2.1 Chuẩn bị Postgres local: tạo role + database `ai_novel_translator` và `ai_novel_translator_test` trên container `shared-postgres` (chạy SQL qua `docker exec shared-postgres psql`), ghi `NT_DATABASE_URL` và `NT_TEST_DATABASE_URL` vào `.env`; cập nhật `.env.example` (bỏ `NT_DB_PATH`); kiểm tra kết nối được tới cả hai database bằng một lệnh Python ngắn dùng psycopg
- [x] 2.2 Thêm cấu hình `NT_DATABASE_URL`, `NT_DB_POOL_MAX` vào `config.py`; tạo pool `psycopg_pool` trong `container.py`, app thoát với lỗi rõ ràng khi không kết nối được; kiểm tra bằng test khởi tạo container với URL sai báo lỗi có tên biến
- [x] 2.3 Viết migration runner (bảng `schema_migrations`, `pg_advisory_lock`, mỗi file một transaction) và `storage/migrations/001_initial.sql` theo bảng schema ở design D6 (kiểu Postgres, CHECK status, FK `ON DELETE CASCADE`); kiểm tra bằng test: database trống lên đúng version, chạy lại lần hai không làm gì, file lỗi được rollback sạch
- [x] 2.4 Fixture pytest theo D6 (đọc `NT_TEST_DATABASE_URL`, dừng sớm kèm hướng dẫn nếu thiếu hoặc không kết nối được, dựng schema một lần mỗi phiên, `TRUNCATE ... RESTART IDENTITY CASCADE` sau mỗi test); kiểm tra test migration của 2.3 chạy qua fixture này và database test sạch sau mỗi test
- [x] 2.5 Cập nhật entity domain (`Chapter` thêm `glossary_version`, `chain_step`, `glossary_outdated`, `possible_omission`, status `edited`; `GlossarySuggestion`, `ReadingProgress`) và viết `storage/postgres_repo.py` thay cho `sqlite_repo.py` (xóa file SQLite), upsert bằng `ON CONFLICT`; chuyển `tests/conftest.py` sang fixture Postgres của 2.4; kiểm tra 8 test hiện có pass trên Postgres, cộng test các thao tác đọc/ghi mới và test xóa novel làm mất toàn bộ bản ghi con
- [x] 2.6 Thêm khi khởi động: chương `translating` đặt về `pending`; kiểm tra bằng test

## 3. Lỗi provider, streaming và Gemini

- [x] 3.1 Thêm các lớp lỗi phân loại (`RefusalError`, `TruncatedError`, `RateQuotaError`, `DailyQuotaError`, `ProviderError`) và `LLMProvider.stream()` vào `domain/ports.py`; `complete()` mặc định ghép từ `stream()`; cập nhật `echo` để stream từng dòng và giả lập được từng loại lỗi; kiểm tra bằng unit test
- [x] 3.2 Hiện thực `providers/gemini.py` (stream, phân loại 429 theo D3, finish reason → truncated/refusal, `reset_at` = 0h Pacific ngày kế); kiểm tra bằng unit test dựa trên fixture của 1.4, không gọi mạng
- [x] 3.3 Bổ sung `stream()` và phân loại lỗi cho `anthropic` và `openai_compat`; kiểm tra bằng unit test với client giả
- [x] 3.4 Đăng ký `gemini` trong registry, thêm cấu hình `NT_CHAIN`, `GEMINI_API_KEY`, `NT_CHAPTER_CHAR_LIMIT`; báo lỗi cấu hình khi thiếu key mà không in giá trị key; kiểm tra bằng test spec "Missing API key" và "Default chain"

## 4. Chuỗi fallback và quota

- [x] 4.1 Port `QuotaTracker` + adapter PostgreSQL `provider_usage` (đếm lượt thành công bằng `UPDATE ... requests = requests + 1`, ghi `exhausted_until`, tự hết hiệu lực khi qua thời điểm reset); kiểm tra bằng unit test có điều khiển đồng hồ và test hai thread cùng tăng đếm không mất lượt
- [x] 4.2 Hiện thực `providers/chain.py` với policy FOREGROUND/BACKGROUND theo D2 (bỏ qua bước đã hết quota, chuyển bước khi hết quota ngày, backoff tối đa 3 lần khi rate limit, dừng khi gặp lỗi khác hoặc lỗi giữa stream); kiểm tra bằng test cho mọi scenario trong spec `llm-providers` (Primary exhausted, Non-quota error, Whole chain exhausted, Recovered after wait)
- [x] 4.3 Nối `ChainProvider` trong `container.py`, giữ khả năng override provider/model từ CLI; kiểm tra bằng test spec "Model override" và "Select provider per request"

## 5. Pipeline dịch một request

- [x] 5.1 Viết prompt 3 phần (`<<TITLE>>`/`<<BODY>>`/`<<NAMES>>`, có ví dụ ngắn, glossary trong phần hướng dẫn cố định) và `SectionParser` streaming; kiểm tra bằng unit test với input bị cắt ở mọi vị trí, thiếu NAMES, thiếu BODY
- [x] 5.2 Viết lại `ChapterTranslator` thành dạng phát sự kiện, cắt đoạn chỉ khi vượt `NT_CHAPTER_CHAR_LIMIT` (tiêu đề đi cùng đoạn đầu), kiểm tra độ đầy đủ (rỗng, truncated → lỗi; lệch >20% số đoạn → cờ `possible_omission`); kiểm tra bằng test các scenario spec `translation-pipeline`
- [x] 5.3 Cập nhật `TranslationService`: lưu `glossary_version`, `chain_step`; quota hết thì để `pending`; không dịch lại chương `translated`/`edited` khi không có `force`; đưa tên đề xuất vào hàng chờ (bỏ qua term đã có hoặc đã bị dismiss); kiểm tra bằng test với provider `echo`
- [x] 5.4 Cập nhật CLI `translate` theo chuỗi mới và cập nhật test CLI/API hiện có; kiểm tra toàn bộ `pytest -q` pass

## 6. Job manager và prefetch

- [x] 6.1 Hiện thực `application/jobs.py` theo D4 (registry một job mỗi chương, hai làn, phát lại sự kiện cho subscriber muộn, nâng job đang chờ lên làn foreground, hủy job đang chờ); kiểm tra bằng test đồng thời dùng provider `echo` có độ trễ
- [x] 6.2 Hiện thực `PrefetchService.on_reading_signal` với đầy đủ điều kiện chặn của spec `translation-prefetch` (N+1 không tồn tại / đã dịch / đang dịch / prefetch tắt / bước 1 hết quota) và chỉ chạy policy BACKGROUND; kiểm tra bằng test cho từng scenario của spec

## 7. Bộ tên, biên tập, tiến độ, tùy chọn

- [x] 7.1 Service hàng chờ đề xuất tên (đồng ý / đồng ý kèm sửa / bỏ qua) và tăng `glossary_version` mỗi khi bộ tên thay đổi; kiểm tra bằng test các scenario "Suggestion review queue" và "Glossary versioning"
- [x] 7.2 Lan truyền đổi tên theo D9 (chỉ chương có raw chứa term, regex ranh giới từ Unicode, chương edited chỉ gắn cờ, một transaction); kiểm tra bằng test "Rename applied", "Unrelated chapter untouched", "Partial word not replaced", "Edited chapter labelled only"
- [x] 7.3 Service biên tập: sửa tay → `edited`; từ chối sửa chương chưa dịch; dịch lại chương edited phải có xác nhận; dịch lại thì xóa cờ outdated; kiểm tra bằng test spec `translation-editing`
- [x] 7.4 Service tiến độ đọc + tùy chọn đọc (lưu server-side) + `last_read_at` và thứ tự thư viện; xóa truyện cần xác nhận và hủy prefetch đang chờ; kiểm tra bằng test spec `novel-library` và "Reading progress"

## 8. API, auth và SSE

- [x] 8.1 Auth theo D7: lệnh `novel hash-password`, kiểm tra `NT_PASSWORD_HASH` lúc khởi động, login/logout, session hash trong DB, hết hạn sau 30 ngày không dùng, khóa 15 phút sau 5 lần sai theo IP (tin `X-Forwarded-For` từ `NT_TRUSTED_PROXY`), bắt buộc header `X-Requested-With` cho request thay đổi dữ liệu; kiểm tra bằng test mọi scenario spec `access-control`
- [x] 8.2 Middleware `X-Robots-Tag` + `/robots.txt`; kiểm tra bằng test "Crawler request"
- [x] 8.3 Tách router `/api` theo nhóm (library, chapters, glossary, progress/preferences, settings/quota) và nối vào services mới; mã lỗi: 401, 404, 429 kèm `reset_at`, 502 kèm loại lỗi; kiểm tra bằng test TestClient cho từng nhóm
- [x] 8.4 Endpoint dịch trả 202 và SSE stream theo D5 (sự kiện `waiting_for_quota`, `paragraph`, `fallback_step`, sự kiện kết thúc; keep-alive; `X-Accel-Buffering: no`); kiểm tra bằng test "Subscribe mid-way" và test hai client cùng nhận một job
- [x] 8.5 Endpoint `reading-signal` gọi `PrefetchService`, endpoint quota/usage cho màn hình cài đặt; kiểm tra bằng test API

## 9. Frontend SvelteKit

- [x] 9.1 Khởi tạo `web/` (SvelteKit, `adapter-static`, `ssr=false`, fallback `index.html`), API client có cookie + `X-Requested-With`, tự chuyển sang `/login` khi gặp 401; FastAPI phục vụ `web/build` ở `/` với fallback deep link; kiểm tra `npm run build` thành công và test spec "Deep link"
- [x] 9.2 Nền tảng giao diện theo D11: `theme.css` (token + 4 theme đọc Tuyên chỉ/Hoàng quyển/Dạ nguyệt/Trúc lâm), font tự host qua `@fontsource` (`font-display: swap`), component `Seal`, `ScrollFrame`, `JadeTablet`, `StatusChip`, `InkMountains`, layout chung (thanh điều hướng có nhãn tu tiên + nhãn rõ nghĩa); kiểm tra `npm run build` không có request font ra ngoài (DevTools Network) và tương phản chữ thân bài ≥4.5:1 trên cả 4 theme
- [x] 9.3 Trang đăng nhập và thư viện (danh sách theo lần đọc gần nhất, upload `.txt` có báo lỗi kích thước, xóa có hộp xác nhận) theo artboard "Tiên hiệp · Đăng nhập", "Tiên hiệp · Tàng Thư Các", "Tiên hiệp · Upload TXT"; kiểm tra thủ công trên viewport 360px và 1280px
- [ ] 9.4 Trang danh sách chương với nhãn trạng thái (pending/translating/translated/edited/failed/glossary-outdated/fallback/possible-omission, hiển thị bằng chữ thường qua `StatusChip`) và nút đọc tiếp, theo artboard "Tiên hiệp · Chi tiết truyện & mục lục"; kiểm tra thủ công với dữ liệu mẫu
- [ ] 9.5 Reader: hiển thị bản đã lưu; tự dịch kèm streaming qua SSE (gắn vào job đang chạy); thông báo hết quota có giờ reset; lỗi kèm nút thử lại; chuyển chương trước/sau; xem bản gốc; nhãn nguồn gốc bản dịch; theo artboard "Tiên hiệp · Reader" và "Tiên hiệp · Reader trạng thái dịch"; kiểm tra thủ công với provider `echo` có độ trễ
- [ ] 9.6 Reader: đếm tín hiệu đọc (30 giây chương hiển thị, tạm dừng khi tab ẩn; cuộn ≥60%; nút "chuẩn bị chương tiếp") gửi một lần mỗi chương; lưu tiến độ debounce 5 giây + `sendBeacon` khi `pagehide`; khôi phục vị trí khi mở truyện; kiểm tra thủ công: đọc 30 giây làm chương N+1 chuyển sang translated
- [ ] 9.7 Chế độ biên tập trong reader (sửa tiêu đề/nội dung, lưu, xác nhận khi dịch lại chương đã sửa) theo artboard "Tiên hiệp · Reader desktop & biên tập"; kiểm tra thủ công
- [ ] 9.8 Trang bộ tên: danh sách term dạng `JadeTablet`, sửa/xóa (cảnh báo số chương bị ảnh hưởng), hàng chờ đề xuất có nút đồng ý / sửa / bỏ qua, theo artboard "Tiên hiệp · Danh Lục"; kiểm tra thủ công một lần đổi tên lan sang chương đã dịch
- [ ] 9.9 Trang cài đặt: theme (Tuyên chỉ/Hoàng quyển/Dạ nguyệt/Trúc lâm), cỡ chữ, giãn dòng (lưu server-side), công tắc prefetch, bảng lượt dùng và trạng thái quota theo từng bước, ghi chú về dữ liệu ở free tier, nút đăng xuất, theo artboard "Tiên hiệp · Thiết lập"; kiểm tra thủ công rằng tùy chọn áp dụng trên trình duyệt khác
- [ ] 9.10 Kiểm tra mobile-first và nhãn: không có thanh cuộn ngang ở 360px, vùng chạm của điều hướng ≥44px, mọi nhãn tu tiên có nhãn rõ nghĩa đi kèm (spec "Plain-language labels"); kiểm tra bằng DevTools device mode

## 10. Đóng gói và triển khai

- [ ] 10.1 `Dockerfile` multi-stage (Node build `web/` → Python 3.14 slim, cùng phiên bản với môi trường dev; uvicorn `--workers 1`; không cần volume dữ liệu) và `docker-compose.yml` mẫu nối vào Docker network `external` của `shared-postgres` (tên network và host lấy từ biến); kiểm tra `docker build` thành công và container trả `/health` OK khi chạy cùng `shared-postgres` local
- [ ] 10.2 Viết `docs/DEPLOY.md`: lệnh SQL tạo role + database, biến môi trường, tạo hash mật khẩu, cách tìm tên network của `shared-postgres`, cấu hình reverse proxy cho subdomain (Nginx và Caddy, tắt buffering cho SSE), sao lưu bằng `pg_dump -Fc` và rollback bằng `pg_restore`; kiểm tra bằng cách làm theo tài liệu trên máy local với docker compose
- [ ] 10.3 Cập nhật `docs/ARCHITECTURE.md` (sơ đồ có web/SSE/job manager/chain, bảng lớp, backlog mới, mục ngôn ngữ giao diện tóm tắt D11 kèm link mockup) và `CLAUDE.md` (lệnh build web, env mới); kiểm tra các lệnh ghi trong tài liệu chạy được

## 11. Kiểm tra tích hợp

- [ ] 11.1 Chạy `pytest -q` và `ruff check src tests` toàn bộ; kiểm tra pass
- [ ] 11.2 Kịch bản end-to-end trên container local (nối `shared-postgres`, database `ai_novel_translator`) với provider `echo`: đăng nhập → upload → mở chương 1 (thấy streaming) → đọc 30 giây → chương 2 đã dịch sẵn → đồng ý một tên đề xuất → đổi tên đó → chương bị ảnh hưởng có nhãn → sửa tay một chương → xóa truyện; kiểm tra mọi bước đúng spec
- [ ] 11.3 Smoke test với Gemini thật (key cá nhân): dịch 2 chương, xác nhận đếm lượt và nhãn model; kiểm tra màn hình quota hiển thị đúng số lượt
- [ ] 11.4 `openspec validate mvp-web-reader --strict` pass

## Workflow follow-up

- Triển khai lên VPS theo `docs/DEPLOY.md` sau khi review.
- Archive change bằng `/opsx:archive` để gộp delta vào `openspec/specs/`.
