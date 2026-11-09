# Design: MVP web reader

## Context

Hiện trạng v0.1 (xem `docs/ARCHITECTURE.md`):
- **Lõi hexagonal:** `domain/` → `pipeline/` → `application/services.py`; adapter nằm ở `providers/`, `storage/sqlite_repo.py`, `ingest/`, `export/`; mọi thứ được nối trong `container.py`.
- **Provider:** đều đồng bộ, `LLMProvider.complete()` trả về toàn bộ text. Đã có `anthropic`, `openai`, `ollama`, `echo`; chưa có Gemini.
- **Pipeline:** `ChapterTranslator` gọi riêng một request cho tiêu đề, rồi cắt nội dung thành các đoạn 3.000 ký tự, mỗi đoạn một request.
- **Storage:** SQLite với ba bảng `novels`, `chapters`, `glossary`. Chưa có cơ chế migration. Change này thay bằng PostgreSQL 16 có sẵn: container `shared-postgres` dùng chung với các app khác, trên cả máy dev lẫn VPS.
- **API:** FastAPI đồng bộ, không có auth. Chưa có frontend.

Ràng buộc chính: một user, một container trên VPS, $0 (Gemini free tier). Quota là tài nguyên khan hiếm. Mục tiêu và phạm vi xem `proposal.md`; hành vi xem các spec trong `specs/`.

## Goals / Non-Goals

**Goals:**
- Giữ lõi hexagonal: logic chuỗi fallback, quota, prefetch nằm ở application/providers, không nằm ở interface.
- Streaming từ provider tới trình duyệt mà không tạo thêm request LLM.
- Mỗi chương có tối đa một bản dịch đang chạy, kể cả khi reader và prefetch cùng yêu cầu chương đó.
- Có cơ chế migration DB để các change sau dùng tiếp.

**Non-Goals:**
- Chạy nhiều process hoặc scale ngang (thiết kế giả định đúng một process).
- Hàng đợi job bền vững qua restart: job đang chạy mất khi restart, chương quay về `pending`.
- Đồng bộ sửa tay theo thời gian thực giữa nhiều thiết bị.

## Decisions

### D1. Provider stream text thô; một parser 3 phần nằm ở pipeline

- `LLMProvider` có thêm `stream(request) -> Iterator[str]`, trả về các mẩu text thô.
- `complete()` giữ lại cho CLI/test; mặc định nó ghép kết quả của `stream()`.
- `pipeline/` có `SectionParser` đọc luồng text, nhận diện marker `<<TITLE>>`, `<<BODY>>`, `<<NAMES>>`, rồi phát ra sự kiện `title`, `paragraph` (mỗi khi gặp xuống dòng trong BODY), `names`, `done`.
- Prompt yêu cầu model trả lời đúng định dạng này. Dòng NAMES có dạng `nguồn | dịch | loại`.

**Lý do:**
- Đặt marker parsing ở pipeline giúp mọi provider dùng chung, không phải viết lại cho từng bên.
- Text thô stream được từng đoạn, còn JSON thì phải đợi xong mới parse an toàn.

**Phương án bị loại:**
- Structured output JSON: không stream từng đoạn được, và nội dung truyện dài trong JSON dễ lỗi escape.
- Gọi một request riêng để trích tên: tốn gấp đôi quota.

### D2. Chuỗi fallback là một provider ghép trong `providers/`, quota là port riêng

- `ChainProvider` hiện thực `LLMProvider`, bọc danh sách `(provider, model)` và nhận thêm tham số `policy`:
  - `FOREGROUND`: dùng mọi bước của chuỗi.
  - `BACKGROUND`: chỉ dùng bước 1.
- Domain có thêm port `QuotaTracker`, adapter PostgreSQL đặt ở `storage/`. Nó ghi số lượt dùng mỗi ngày theo từng bước, và `exhausted_until` của bước nào đã hết quota.
- `ChainProvider` hỏi tracker trước khi gọi, để bỏ qua bước đã hết mà không gửi request.

**Quy tắc chuyển bước:**
- Lỗi quota ngày → sang bước kế tiếp. Chuyển được là vì lỗi 429 trả về trước khi stream bắt đầu, nên chưa phát ra đoạn nào.
- Lỗi rate theo phút → backoff tối đa 3 lần trên cùng bước, phát sự kiện `waiting_for_quota`.
- Lỗi khác → dừng ngay, không thử bước sau.
- Lỗi phát sinh khi stream đã chạy được một phần → không chuyển bước, chương `failed`.

Provider chỉ việc phân loại lỗi thành `RefusalError`, `TruncatedError`, `RateQuotaError(retry_after)`, `DailyQuotaError(reset_at)` hoặc `ProviderError`. Các lớp này nằm trong `domain/ports.py` và đều là lớp con của `TranslationError`.

**Lý do:** application chỉ thấy một `LLMProvider`, đúng quy tắc "không rẽ nhánh theo tên provider".

**Phương án bị loại:** đặt logic fallback trong `TranslationService`. Như vậy service sẽ dính vào chi tiết quota.

### D3. Provider Gemini

- Dùng SDK chính thức `google-genai` với hàm stream nội dung, key lấy từ `GEMINI_API_KEY`.
- **Phân loại 429:** đọc phần chi tiết lỗi của Google API.
  - Quota có id chứa `PerDay` → hết quota ngày. `reset_at` là 0h giờ Pacific của ngày kế tiếp, đúng cách Gemini reset quota ngày.
  - `RetryInfo` → hết quota phút, `retry_after` lấy từ đó.
  - Không phân loại được → coi là quota phút, vì đây là hướng an toàn hơn.
- `finish_reason` là `MAX_TOKENS` → `TruncatedError`; là `SAFETY` hoặc bị chặn → `RefusalError`.
- Task đầu tiên là một spike nhỏ dùng key thật để xác nhận định dạng chi tiết lỗi. Unit test dùng fixture của định dạng đó.

### D4. Bộ quản lý job dịch trong process

`application/jobs.py` có `TranslationJobManager`:
- Một registry `chapter_id → Job`, bảo đảm mỗi chương chỉ có một job.
- **Hai làn chạy (thread)**: làn foreground và làn background, mỗi làn chạy tối đa một job.
  - Chia hai làn để chương bạn vừa mở không phải chờ một prefetch đang chạy dở.
  - Tối đa hai request song song là mức an toàn với giới hạn RPM của free tier.
- Mỗi `Job` giữ danh sách sự kiện đã phát ra, để client đăng ký muộn được phát lại từ đầu (spec "Subscribe mid-way"). Sự kiện được phân phát qua `queue.Queue` riêng cho từng subscriber.
- **Khi foreground mở đúng chương đang được prefetch:** đăng ký vào job đó, không tạo job mới.
  - Nếu job đó chưa bắt đầu chạy, nâng nó sang làn foreground.
  - Nếu đã chạy, giữ nguyên. Job đó chỉ dùng bước 1; nếu bước 1 hết quota giữa chừng thì job trả `quota_exhausted`, và reader tự gửi lại yêu cầu foreground.
- **Hủy prefetch:** chỉ hủy job đang chờ trong hàng; job đã gửi request thì chạy đến hết (spec "Owner leaves").
- **Khi restart:** chương nào đang ở `translating` thì đặt về `pending`.

**Phương án bị loại:**
- Celery/RQ: phải thêm Redis và một process nữa, quá nặng với một user.
- `asyncio` thuần: provider SDK đồng bộ, và code hiện tại đều đồng bộ.

### D5. SSE từ FastAPI

- `GET /api/chapters/{id}/stream` trả về `StreamingResponse` với `text/event-stream`, đọc từ queue của subscriber.
- Gửi header `X-Accel-Buffering: no` và `Cache-Control: no-cache`, kèm comment keep-alive mỗi 15 giây.
- Reverse proxy cần tắt buffering cho đường dẫn này; ghi chú trong tài liệu triển khai.
- Endpoint `POST .../translate` tạo job hoặc gắn vào job có sẵn, và trả ngay `202` cùng URL stream.

**Phương án bị loại:** WebSocket. Chỉ cần luồng một chiều, SSE đơn giản hơn và tự reconnect.

### D6. PostgreSQL: kết nối, pool, migration

**Kết nối**
- Một biến duy nhất `NT_DATABASE_URL` (`postgresql://<role>:<pass>@<host>:5432/ai_novel_translator`).
- App dùng database và role riêng trong instance dùng chung. Role chỉ có quyền trên database của mình. App **không** tự tạo database hay role; việc đó làm thủ công một lần, theo `docs/DEPLOY.md`.
- Trong Docker, container app nối vào Docker network sẵn có của `shared-postgres` (khai báo `external` trong compose) và dùng hostname `shared-postgres`. Khi dev chạy ngoài Docker thì dùng `localhost:5432`.

**Driver và pool**
- `psycopg` 3 (đồng bộ, bản binary) với `psycopg_pool.ConnectionPool` (min 1, max 5, cấu hình được qua `NT_DB_POOL_MAX`).
- Pool dùng chung cho các thread API và hai làn job. Mỗi thao tác repository mượn một kết nối, dùng trong một transaction rồi trả lại.
- Giới hạn pool nhỏ để không chiếm hết `max_connections` của instance dùng chung.

**Migration**
- `storage/migrations/` chứa các file `NNN_*.sql`; bảng `schema_migrations(version, applied_at)` ghi lại file nào đã chạy.
- Lúc khởi động, runner lấy `pg_advisory_lock` để không có hai process cùng migrate, rồi chạy tuần tự các file chưa áp dụng. Mỗi file chạy trong một transaction; Postgres hỗ trợ DDL trong transaction nên file lỗi giữa chừng sẽ rollback sạch.
- Chỉ có một file `001_initial.sql` chứa toàn bộ schema mới. SQLite v0.1 bị bỏ, không chuyển dữ liệu.

**Phương án bị loại**
- SQLAlchemy + Alembic: kéo theo ORM/Core cho khoảng 8 bảng với truy vấn đơn giản. Repository viết SQL tay đã đủ.
- `asyncpg`: toàn bộ code đang đồng bộ.

Schema trong `001_initial.sql`:

| Bảng | Cột chính |
|---|---|
| `novels` | `id BIGSERIAL` PK, `title`, `source_lang`, `target_lang`, `glossary_version INT NOT NULL DEFAULT 0`, `created_at TIMESTAMPTZ`, `last_read_at TIMESTAMPTZ` |
| `chapters` | `id BIGSERIAL` PK, `novel_id` FK, `idx INT`, `title`, `source_text`, `translated_title`, `translated_text`, `status TEXT` CHECK (`pending`/`translating`/`translated`/`edited`/`failed`), `provider`, `model`, `chain_step INT`, `glossary_version INT`, `glossary_outdated BOOLEAN DEFAULT false`, `possible_omission BOOLEAN DEFAULT false`, `updated_at TIMESTAMPTZ`; UNIQUE(`novel_id`, `idx`) |
| `glossary` | `id BIGSERIAL` PK, `novel_id` FK, `source_term`, `target_term`, `note`; UNIQUE(`novel_id`, `source_term`) |
| `glossary_suggestions` | `novel_id` FK, `source_term`, `target_term`, `category`, `status TEXT` CHECK (`pending`/`dismissed`); UNIQUE(`novel_id`, `source_term`) |
| `reading_progress` | `novel_id` PK/FK, `chapter_index INT`, `position REAL` (0–1), `updated_at TIMESTAMPTZ` |
| `preferences` | `key TEXT` PK, `value JSONB`: theme, cỡ chữ, giãn dòng, bật/tắt prefetch |
| `provider_usage` | `day DATE`, `step INT`, `requests INT`, `exhausted_until TIMESTAMPTZ`; PK(`day`, `step`) |
| `sessions` | `token_hash TEXT` PK, `created_at`, `last_seen_at TIMESTAMPTZ` |

- Mọi bảng con đều có khóa ngoại `ON DELETE CASCADE` về `novels`, để xóa truyện là xóa sạch.
- Upsert (glossary, suggestions, usage, preferences) dùng `INSERT ... ON CONFLICT`. Đếm lượt dùng quota bằng `UPDATE ... SET requests = requests + 1` để an toàn khi hai làn job cùng ghi.
- Tìm chương có raw chứa term (D9) dùng `strpos(source_text, term) > 0`. Với quy mô một user, quét tuần tự là đủ nhanh; chưa cần index full-text.

**Test**
- Test dùng database riêng `ai_novel_translator_test` trên Postgres local, lấy từ `NT_TEST_DATABASE_URL`. Biến này chưa đặt thì test báo lỗi rõ ràng, không lặng lẽ skip.
- Mỗi phiên pytest drop và tạo lại schema `public` rồi chạy migration một lần; mỗi test kết thúc bằng `TRUNCATE ... RESTART IDENTITY CASCADE` mọi bảng.

### D7. Auth: hash mật khẩu trong env, session lưu server-side

- `NT_PASSWORD_HASH` chứa hash argon2 (thư viện `argon2-cffi`). Lệnh `novel hash-password` tạo hash. Không lưu mật khẩu dạng plaintext trong env.
- Session token sinh bằng `secrets.token_urlsafe(32)`. DB chỉ lưu SHA-256 của token, cookie `nt_session` có HttpOnly, Secure và SameSite=Lax.
- **Chống CSRF:** request thay đổi dữ liệu bắt buộc có header `X-Requested-With`. Form từ trang khác không gửi được header này, và SameSite=Lax chặn thêm một lớp.
- Đếm số lần đăng nhập sai trong bộ nhớ, theo IP lấy từ `X-Forwarded-For` của proxy tin cậy (cấu hình `NT_TRUSTED_PROXY`).
- Middleware `noindex` gắn header cho mọi response; `/robots.txt` là route tĩnh.

### D8. Frontend: SvelteKit chế độ SPA tĩnh

- Thư mục `web/` dùng SvelteKit với `adapter-static`, `ssr = false` và `fallback: 'index.html'`. Build ra `web/build`, FastAPI mount thư mục này ở `/` cùng route fallback cho deep link.
- Chọn SvelteKit thay Svelte + router tự chọn vì có sẵn file-based routing và tooling chuẩn, mà vẫn ra file tĩnh.
- Không có Node trong runtime.

**Màn hình:**
- `/login`
- `/` (thư viện, upload)
- `/novels/[id]` (danh sách chương, nút đọc tiếp)
- `/novels/[id]/chapters/[n]` (reader)
- `/novels/[id]/glossary` (bộ tên và hàng chờ duyệt)
- `/settings` (giao diện đọc, prefetch, quota)

**Tín hiệu đọc tính ở client:**
- Đếm thời gian chương hiển thị (dùng `visibilitychange` để dừng đếm khi tab ẩn) và tỉ lệ cuộn.
- Gửi `POST /api/novels/{id}/chapters/{n}/reading-signal` một lần cho mỗi chương. Server kiểm tra lại các điều kiện chặn của spec `translation-prefetch`; client không tự quyết.
- Tiến độ lưu theo debounce 5 giây và khi `pagehide` (dùng `navigator.sendBeacon`).

### D9. Lan truyền đổi tên

- `GlossaryService.set_term` phát hiện đây là thao tác đổi bản dịch của một term đã có. Nó tìm các chương có raw chứa term (`strpos`, xem D6).
- Với chương `translated`: thay thế bằng regex với ranh giới từ Unicode, tức không có chữ cái hoặc số đứng liền trước/sau, và phân biệt hoa thường. Sau đó đặt `glossary_outdated=1`.
- Với chương `edited`: chỉ đặt cờ.
- Toàn bộ chạy trong một transaction, cùng lúc tăng `novels.glossary_version`.

### D10. Cấu hình

Thêm các biến:
- `NT_CHAIN`, ví dụ `gemini:<model-chính>,gemini:<model-nhẹ>`
- `GEMINI_API_KEY`, `NT_PASSWORD_HASH`, `NT_TRUSTED_PROXY`
- `NT_CHAPTER_CHAR_LIMIT` (mặc định 20000)

`NT_MAX_SEGMENT_CHARS` được thay bằng `NT_CHAPTER_CHAR_LIMIT`. Cấu hình database xem D6. Riêng `NT_PROVIDER`/`NT_MODEL` vẫn dùng cho CLI override.

### D11. Ngôn ngữ giao diện "Thủy mặc · Chu sa"

Cả 6 màn dùng chung một phong cách tiên hiệp. Mockup tham chiếu: https://claude.ai/artifact/9L5YJPQnkHCwMMYxtM34vn (chỉ các artboard "Tiên hiệp · …"; hai hàng bản trung tính phía trên là phương án cũ, không dùng).

**Token** (CSS custom properties trong `web/src/lib/styles/theme.css`, component chỉ dùng biến, không viết mã màu trực tiếp):

| Token | Giá trị | Dùng cho |
|---|---|---|
| `--paper` / `--paper-raised` | `#F3EDE0` / `#FAF6EC` | nền trang / khung cuộn thư |
| `--ink` / `--ink-muted` | `#1E1B16` / `#5E5648` | chữ chính / chữ phụ |
| `--cinnabar` | `#9E2B1E` | nút chính, ấn chương, thao tác nguy hiểm |
| `--jade` | `#2F6B57` | trạng thái đã dịch, tiến độ |
| `--bronze` | `#8C6A2A` | viền trang trí, đường mây (không dùng cho chữ nhỏ) |
| `--line` | `#D9CDB4` | đường kẻ, viền khung |

**Chữ:** Ma Shan Zheng cho chữ Hán ở tiêu đề, con dấu và bìa (không dùng cho chữ Việt vì font không có dấu tiếng Việt); Cormorant Garamond cho tiêu đề tiếng Việt; Noto Serif / Noto Serif SC cho nội dung chương; Be Vietnam Pro cho chữ giao diện nhỏ.

**Font tự host:** cài qua `@fontsource/*` và đóng gói vào `web/build`. App là private + `noindex`, nên không gửi request tới bên thứ ba lúc chạy. Font CJK được `@fontsource` tách theo `unicode-range` nên trình duyệt chỉ tải phần chữ đang hiển thị; mọi `@font-face` dùng `font-display: swap`.

**Quy ước nhãn:** tên khu vực kiểu tu tiên luôn có nhãn rõ nghĩa đi kèm (Tàng Thư Các · Thư viện, Danh Lục · Bộ tên, Tu vi · tiến độ dịch, Pháp khí · chuỗi model, Thiết lập · Cài đặt). Trạng thái chương, thông báo lỗi, quota và hộp xác nhận luôn dùng từ ngữ thường (Đã dịch, Lỗi, Hết lượt hôm nay…), không đổi sang từ tu tiên.

**Theme đọc** (giá trị lưu server-side theo spec `web-reader`): `light` = Tuyên chỉ, `sepia` = Hoàng quyển, `dark` = Dạ nguyệt; thêm `bamboo` = Trúc lâm. Mỗi theme định nghĩa lại bộ token trên, chữ thân bài đạt tương phản ≥4.5:1.

**Component dùng chung** (`web/src/lib/components/`): `Seal` (ấn son vuông chứa 1–2 chữ Hán), `ScrollFrame` (khung viền kép như cuộn thư), `JadeTablet` (thẻ thuật ngữ), `StatusChip` (nhãn trạng thái chương, chữ thường + màu), `InkMountains` (SVG núi thủy mặc, `aria-hidden`, chỉ trang trí). Không dùng emoji; icon là SVG nét.

**Ánh xạ route → artboard mockup:**

| Route | Artboard |
|---|---|
| `/login` | Tiên hiệp · Đăng nhập |
| `/` | Tiên hiệp · Tàng Thư Các; Tiên hiệp · Upload TXT |
| `/novels/[id]` | Tiên hiệp · Chi tiết truyện & mục lục |
| `/novels/[id]/chapters/[n]` | Tiên hiệp · Reader (mobile); Tiên hiệp · Reader trạng thái dịch (mobile); Tiên hiệp · Reader desktop & biên tập |
| `/novels/[id]/glossary` | Tiên hiệp · Danh Lục |
| `/settings` | Tiên hiệp · Thiết lập |

Mockup là tham chiếu bố cục và phong cách; hành vi lấy theo spec. Khi mockup và spec lệch nhau, spec thắng.

### Các lớp bị thay đổi

| Lớp | Thay đổi |
|---|---|
| `domain/` | entity `Chapter` (cột mới, status `edited`), `GlossarySuggestion`, `ReadingProgress`; các lớp lỗi; port `QuotaTracker`; `LLMProvider.stream` |
| `pipeline/` | prompt 3 phần, `SectionParser`, `ChapterTranslator` chuyển sang chạy trên sự kiện, kiểm tra độ đầy đủ |
| `providers/` | `gemini.py`, `chain.py`; provider cũ thêm `stream` và phân loại lỗi |
| `application/` | `jobs.py`; service cho prefetch, editing, suggestions, rename, progress, preferences; `ExportService` bỏ qua cờ |
| `storage/` | thay `sqlite_repo.py` bằng `postgres_repo.py` (pool psycopg), migration runner, các repository mới, quota tracker |
| `config.py` | thêm `NT_DATABASE_URL`, `NT_DB_POOL_MAX`; bỏ `NT_DB_PATH` |
| `interfaces/api` | auth middleware, router tách theo nhóm, SSE, phục vụ SPA |
| `interfaces/cli` | `hash-password`; `translate` dùng chuỗi |
| mới: `web/` | SvelteKit SPA; theme "Thủy mặc · Chu sa" (token, font tự host, component dùng chung, xem D11) |
| deploy | `Dockerfile` multi-stage, `docker-compose.yml` mẫu, ghi chú reverse proxy |

## Risks / Trade-offs

- **[Model không theo đúng định dạng marker]** → Prompt có ví dụ ngắn. Parser chấp nhận thiếu `<<NAMES>>`. Thiếu `<<BODY>>` thì `failed` với lỗi "malformed", để user bấm thử lại; không tự thử lại, vì mỗi lần thử tốn quota.
- **[Định dạng lỗi 429 của Gemini khác dự đoán]** → Spike ở task đầu. Không nhận diện được thì coi là quota phút (backoff có giới hạn), tránh đánh dấu nhầm là hết quota ngày.
- **[Quota và tên model free tier thay đổi]** → Không hard-code giới hạn; cấu hình model qua `NT_CHAIN`. Màn hình quota hiện số liệu đếm được thực tế.
- **[Job mất khi restart]** → Đưa `translating` về `pending` lúc khởi động. Quota đã tiêu cho job dở thì chấp nhận mất.
- **[Chạy nhiều worker uvicorn sẽ phá job registry]** → Dockerfile cố định `--workers 1`; ghi rõ trong tài liệu.
- **[Thay tên nhầm trong tiếng Việt]** (ví dụ "Tô Nhu" nằm trong "Tô Nhuận") → Có kiểm tra ranh giới từ và chỉ chạy trên chương có raw chứa term. Nhãn glossary-outdated luôn được gắn, nên user có đường dịch lại.
- **[Free tier: Google có thể dùng dữ liệu]** → Đánh đổi đã chấp nhận trong proposal. Ghi chú trong màn hình cài đặt.
- **[Font CJK nặng làm chậm lần tải đầu trên điện thoại]** → Chỉ dùng Ma Shan Zheng cho vài chữ Hán ở tiêu đề/ấn; font được tách theo `unicode-range` và `font-display: swap`, nên nội dung chương hiển thị ngay bằng font dự phòng.
- **[Tên kiểu tu tiên gây khó hiểu]** → Quy ước nhãn ở D11: luôn kèm nhãn rõ nghĩa; trạng thái và lỗi không bao giờ dùng từ tu tiên.
- **[Tương phản thấp ở theme tối hoặc chữ vàng đồng]** → `--bronze` chỉ dùng cho trang trí; mỗi theme được kiểm tra tương phản ≥4.5:1 trong task nền tảng giao diện.
- **[Token stream đến trình duyệt bị proxy buffer]** → Header `X-Accel-Buffering`; ghi chú cấu hình Nginx/Caddy.
- **[Instance Postgres dùng chung hết kết nối hoặc bị app khác làm chậm]** → Pool tối đa 5 kết nối; dùng role và database riêng nên app không đụng dữ liệu app khác. Postgres không kết nối được lúc khởi động thì app thoát với lỗi rõ ràng.
- **[Test phụ thuộc Postgres local đang chạy]** → Đã chấp nhận. Thiếu `NT_TEST_DATABASE_URL` hoặc không kết nối được thì pytest dừng sớm với thông báo hướng dẫn, thay vì hàng loạt test lỗi khó hiểu. Database test tách riêng nên không bao giờ xóa nhầm dữ liệu thật.
- **[Đổi tên container hoặc network của `shared-postgres` trên VPS]** → Tên network và host là cấu hình trong compose và `NT_DATABASE_URL`, không hard-code trong code.

## Migration Plan

1. Tạo role và database `ai_novel_translator` trên `shared-postgres` (lệnh SQL ghi trong `docs/DEPLOY.md`). Dữ liệu SQLite v0.1 không được chuyển.
2. Cấu hình env: `NT_DATABASE_URL`, `GEMINI_API_KEY`, `NT_PASSWORD_HASH`, `NT_CHAIN`, `NT_TRUSTED_PROXY`.
3. Khởi động container app trong network của `shared-postgres`; migration runner tự áp dụng `001`.
4. Thêm khối subdomain vào reverse proxy, tắt buffering cho `/api/chapters/*/stream`.
5. **Sao lưu:** `pg_dump -Fc ai_novel_translator` chạy định kỳ, chỉ database của app.
6. **Rollback:** dừng container mới, `pg_restore` bản sao lưu vào database của app, chạy lại image cũ.

## Open Questions

- ID model Gemini cụ thể cho hai bước và giới hạn free tier hiện hành: chốt lúc triển khai bằng cách xem AI Studio; chỉ ảnh hưởng giá trị mặc định của `NT_CHAIN`.
- Ngưỡng 30 giây / 60% cho tín hiệu đọc có thể chỉnh sau khi dùng thật; đổi thì phải cập nhật spec.
