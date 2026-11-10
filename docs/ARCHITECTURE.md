# Kiến trúc Novel Translator

Web reader cá nhân dịch truyện Trung → Việt bằng LLM, chạy một container trên VPS. Kiến trúc hexagonal (ports & adapters): lõi nghiệp vụ không biết gì về HTTP, PostgreSQL hay SDK của LLM. Nhờ vậy thêm provider, định dạng file, hay giao diện mới chỉ cần thêm adapter.

```
   ┌──────────────────────────┐
   │ Web SPA (SvelteKit, web/)│  build tĩnh, FastAPI phục vụ ở "/"
   └────────────┬─────────────┘
                │ JSON + SSE (/api/...)
   ┌────────────▼─────────────┐     ┌──────────────┐
   │ API (FastAPI)            │     │ CLI (Typer)  │   interfaces/  (CLI = công cụ quản trị/dev)
   │ auth · noindex · SSE     │     └──────┬───────┘
   └────────────┬─────────────┘            │
                └──────────┬───────────────┘
                           ▼
   ┌─────────────────────────────────────────────────────┐
   │ application/                                        │
   │  services.py: Library, Glossary, Translation,       │
   │               Reader, Editing, Export               │
   │  jobs.py: TranslationJobManager (2 làn: foreground, │
   │           background; 1 job/chương; replay sự kiện) │
   │  prefetch.py: buffer N+1 · auth.py: đăng nhập/session│
   │  imports.py: bản xem trước import TXT (bộ nhớ, TTL) │
   └──────────┬─────────────────────────┬────────────────┘
              │                         ▼
              │           ┌──────────────────────────────┐
              │           │ pipeline/                    │  prompt 3 phần → SectionParser
              │           │ prompts · sections · translator│ (TITLE/BODY/NAMES) → sự kiện
              │           └──────────────┬───────────────┘
              ▼                          ▼
   ┌─────────────────────────────────────────────────────┐
   │ domain/ (models, ports, lỗi dịch, chapter_split,    │  không phụ thuộc gì
   │          novel_details)                             │
   └─────────────────────────────────────────────────────┘
        ▲                  ▲                       ▲            ▲          ▲
   storage/            providers/              ingest/txt   export/txt   media/      adapters
   Postgres repo,      ChainProvider ──► gemini, anthropic,              ảnh bìa (Pillow),
   quota tracker,      (fallback +       openai/ollama, echo             tải link chống
   migrator            quota)                                            SSRF
        └──────────────────┴───────────────────────┴────────────┴──────────┘
                           nối trong container.py
```

Luồng dịch một chương khi đọc:

```
reader mở chương ─POST .../translate─► JobManager ─► ChapterTranslator ─► ChainProvider ─► Gemini (stream)
       ▲                (202 + URL stream)   │ sự kiện title/paragraph/names/done/failed
       └──────── GET .../stream (SSE) ◄──────┘ (subscriber đến muộn được phát lại từ đầu)
reading-signal (≥30s, ≥60% cuộn) ─► PrefetchService ─► job background chương N+1 (chỉ bước 1 của chuỗi)
```

## Các lớp

| Thư mục | Vai trò | Được import |
|---|---|---|
| `domain/` | `Novel` (`pretranslated` khi import từ bản tiếng Việt; `author`, `description`, `cover_updated_at`), `Chapter` (status `pending`/`translating`/`translated`/`edited`/`failed`), `GlossaryEntry`, `GlossarySuggestion`, `ReadingProgress`, `ChainPolicy`; port `LLMProvider` (`stream`/`complete`), `NovelRepository`, `QuotaTracker`, `SessionStore`, `SourceLoader`, `Exporter`, `CoverImageProcessor`, `CoverImageFetcher`; `novel_details.py` (luật sửa tên/tác giả/giới thiệu `normalize_details`, `UNSET`, `CoverImage`, lỗi `NovelDetailsError`/`InvalidImageError`/`CoverFetchError`); `chapter_split.py` (nhận diện tiêu đề chương Trung/Việt, quyển, phần mở đầu, ngôn ngữ file, cảnh báo, áp ranh giới tùy ý); lỗi `RefusalError`, `TruncatedError`, `RateQuotaError`, `DailyQuotaError`, `MalformedOutputError`, `ProviderError`; `rename.py` (thay tên theo ranh giới từ) | không gì cả |
| `pipeline/` | `prompts` (prompt 3 phần + glossary), `sections` (`SectionParser` streaming), `translator` (`ChapterTranslator`: một request mỗi chương, kiểm tra sót đoạn), `segmenter` (chỉ cắt khi vượt `NT_CHAPTER_CHAR_LIMIT`) | domain |
| `application/` | `services.py` (`LibraryService` gồm sửa thông tin truyện và ảnh bìa: `update_details`, `set_cover`/`remove_cover`/`get_cover`, `preview_cover_from_url`, `GlossaryService` gồm hàng chờ đề xuất và lan truyền đổi tên, `TranslationService`, `ReaderService` tiến độ + tùy chọn, `EditingService`, `ExportService`); `imports.py` (`ImportDraftService`: upload → xem trước → xác nhận); `jobs.py`; `prefetch.py`; `auth.py` | domain, pipeline |
| `providers/` | `chain` (`ChainProvider`: fallback theo `NT_CHAIN`, policy FOREGROUND/BACKGROUND, backoff lỗi phút, chuyển bước khi hết quota ngày), `gemini` (mặc định), `anthropic_provider`, `openai_compat` (OpenAI/Ollama), `echo` (test) + `registry` | domain |
| `storage/` | `db.py` (pool psycopg 3, `ping` cho health check), `migrator.py` + `migrations/NNN_*.sql` (`002_novel_details.sql`: cột `author`/`description`/`cover_updated_at`, bảng `novel_covers` chứa byte ảnh), `postgres_repo.py`, `quota_repo.py` | domain |
| `media/` | `pillow_cover.py` (`PillowCoverProcessor`: chỉ JPEG/PNG/WebP theo nội dung, giới hạn số điểm ảnh, xoay theo EXIF, thu về 600×900, mã hoá lại WebP không metadata); `http_fetcher.py` (`SafeHttpImageFetcher`: tải ảnh từ link, chỉ http/https cổng 80/443, chỉ IP public kể cả IPv4 nhúng trong IPv6, kết nối thẳng tới IP đã kiểm, chuyển hướng tự kiểm ≤3, ≤10 MB, 15 giây, không cookie/proxy/thử lại) | domain |
| `ingest/`, `export/` | đọc và giải mã TXT (`SourceLoader.read_text`/`decode`: UTF-8, GB18030), xuất TXT | domain |
| `container.py` | composition root: nơi duy nhất chọn adapter cụ thể, tạo pool, chạy migration; `run_migrations()` chỉ migrate (cho entrypoint và `novel migrate`, không cần key LLM hay mật khẩu); `Container.database_ok()` cho health | tất cả |
| `interfaces/api` | `app.py` (`/api/health` công khai, `/health` là bí danh; log version lúc khởi động), `auth.py` (session cookie, CSRF header, chống brute-force theo IP client: `NT_TRUSTED_PROXY` là danh sách IP/CIDR của proxy được tin để đọc `X-Forwarded-For`), `privacy.py` (`X-Robots-Tag`, `robots.txt`), `routers/` theo nhóm, `web.py` (phục vụ SPA + fallback deep link) | application, container |
| `interfaces/cli` | import/dịch/xuất/glossary để quản trị và debug; `edit` (tên/tác giả/giới thiệu; ảnh bìa chỉ có trên web); `hash-password`; `migrate`; `serve` | application, container |
| `web/` | SvelteKit SPA (`adapter-static`): 6 màn `/login`, `/`, `/novels/[id]`, `/novels/[id]/chapters/[n]`, `/novels/[id]/glossary`, `/settings` | gọi API qua HTTP |

## Điểm mở rộng thường gặp

- **Provider LLM mới**: viết class kế thừa `StreamingProvider` (có `name`, `default_model`, `stream()`), phân loại lỗi thành các lớp lỗi trong `domain/ports.py`, rồi gọi `register_provider()` trong `registry.py`. Khai báo vào chuỗi qua `NT_CHAIN=provider:model,...`. Không rẽ nhánh theo tên provider trong pipeline/application.
- **Định dạng nhập** (EPUB, crawl web): hiện thực `SourceLoader` (`read_text`/`decode` trả văn bản), nối trong `container.py`; tách chương dùng chung `domain/chapter_split.py`.
- **Mẫu tiêu đề chương mới** (vd. `【第一章】`, `001.`): thêm regex trong `domain/chapter_split.py` kèm test; mọi đường import (CLI, API, xem trước) dùng chung.
- **Định dạng xuất** (EPUB, DOCX): hiện thực `Exporter`, thêm vào dict `exporters`.
- **Thay đổi schema**: thêm file `storage/migrations/NNN_<tên>.sql` mới (không sửa file đã chạy); entrypoint của image (và `build_container`) tự áp dụng lúc khởi động. **Chỉ thêm**: bảng mới (kèm mọi constraint), cột nullable hoặc có `DEFAULT`, index, `UPDATE` để backfill. Cấm DROP/RENAME/TRUNCATE/DELETE, đổi kiểu, `NOT NULL` mới, `DROP DEFAULT`, constraint hay `UNIQUE INDEX` mới trên bảng đã có; `tests/test_migration_rules.py` chặn các câu này. Code đọc cột mới phải chịu được `NULL` (rollback về bản cũ rồi nâng cấp lại sẽ có dòng do bản cũ ghi). Nhờ vậy rollback image không cần khôi phục database; migrator bỏ qua version lạ trong `schema_migrations`.

## Quyết định thiết kế

Chi tiết và phương án bị loại xem `openspec/changes/mvp-web-reader/design.md` (sau khi archive: `openspec/changes/archive/`).

- **Gemini là provider mặc định**, chạy qua chuỗi fallback `NT_CHAIN` (mặc định `gemini-3.5-flash` → `gemini-3.5-flash-lite`, cùng một key). Mục tiêu chi phí $0 với free tier. Lỗi 429 theo phút: backoff tối đa 3 lần; theo ngày: sang bước kế hoặc dừng và báo giờ reset. Không xoay vòng nhiều key/tài khoản.
- **Một request mỗi chương** (tiêu đề + nội dung + đề xuất tên), phản hồi dạng marker `<<TITLE>>`/`<<BODY>>`/`<<NAMES>>` để stream được từng đoạn.
- **Job trong process** (`TranslationJobManager`): hai làn, mỗi làn một job, mỗi chương tối đa một job. Giả định đúng một process (`uvicorn --workers 1`); job mất khi restart, chương `translating` quay về `pending`.
- **SSE** cho streaming (một chiều); reverse proxy phải tắt buffering (Traefik v3 mặc định không buffer, xem `docs/DEPLOY.md`). Khi container restart, luồng đang mở bị cắt và job trong bộ nhớ mất: trang đọc báo mất kết nối, mở lại chương thì dịch lại.
- **Buffer N+1**: tín hiệu đọc thật → dịch trước tối đa một chương, chỉ bằng bước 1 của chuỗi; quota dự phòng dành cho chương người dùng chủ động mở.
- **PostgreSQL** dùng chung instance `shared-postgres`, database + role riêng, pool nhỏ (`NT_DB_POOL_MAX`), migration SQL tay có `pg_advisory_lock`. Test dùng database riêng `NT_TEST_DATABASE_URL`.
- **Import có xem trước**: upload web không lưu ngay; draft (văn bản + kết quả tách) giữ trong bộ nhớ 60 phút, tối đa 3 draft, mất khi restart. File tiếng Việt lưu thành truyện "bản dịch có sẵn": chương Đã dịch, `provider = "import"`, không bao giờ gửi tới LLM.
- **Ảnh bìa lưu trong PostgreSQL** (bảng `novel_covers`, tách khỏi `novels` để danh sách không kéo byte ảnh): app không có volume lưu file. Ảnh luôn được giải mã và mã hoá lại ở server; URL `cover_url` có `?v=` theo thời điểm đổi ảnh, cache `private`. Chi tiết: `openspec/changes/edit-novel-details/design.md`.
- **Request mạng ra ngoài duy nhất ngoài LLM là tải ảnh bìa từ link**, chỉ khi người dùng bấm "Lấy ảnh". Server tải về rồi trả ảnh để xem trước; trình duyệt không mở link người dùng dán. Mọi kiểm tra chống SSRF nằm ở `media/http_fetcher.py`; không có cờ nào tắt được (test thay DNS/socket thay vì bỏ kiểm tra).
- **Một người dùng**: hash argon2 trong `NT_PASSWORD_HASH`, session lưu server-side (chỉ lưu SHA-256 token), mọi trang `noindex`.
- **Triển khai "CI build, VPS chỉ chạy"** (chi tiết: `openspec/changes/deploy-vps-ghcr/design.md`, vận hành: `docs/DEPLOY.md`):
  - GitHub Actions kiểm tra, build image một lần, quét Trivy, rồi push lên GHCR chính image đã quét (`sha-…` + `latest` từ `main`, `vX.Y.Z` từ git tag nằm trên `main`).
  - Image nhận `NT_VERSION` lúc build. Entrypoint `docker/entrypoint.sh`: lệnh là `uvicorn` thì `novel migrate` (advisory lock; lỗi → container thoát) rồi `exec` server; lệnh khác (vd. `novel hash-password`) chạy thẳng, không cần DB.
  - Container không trạng thái: rootfs read-only, bỏ mọi capability, uid 10001, chỉ `/tmp` là tmpfs (Starlette đệm upload lớn ra file tạm). Một container, một worker.
  - `GET /api/health`: `SELECT 1` qua pool, 200 `{"status":"ok"}` hoặc 503 `{"status":"unavailable"}`; chỉ người đã đăng nhập mới thấy `version`. `HEALTHCHECK` dùng endpoint này với `--start-interval=2s` để Traefik nhận container mới ngay khi sẵn sàng; uvicorn `--timeout-graceful-shutdown 10` vì SSE không tự đóng.
  - Traefik dùng chung định tuyến theo label `Host`; app không publish cổng, nối hai network ngoài `traefik` và `postgres`.

## Ngôn ngữ giao diện "Thủy mặc · Chu sa"

Tóm tắt design D11. Mockup tham chiếu: https://claude.ai/artifact/9L5YJPQnkHCwMMYxtM34vn (chỉ các artboard "Tiên hiệp · …"). Mockup là tham chiếu bố cục; khi lệch với spec thì spec thắng.

- **Token màu** trong `web/src/lib/styles/theme.css`; component chỉ dùng biến: `--paper` `#F3EDE0`, `--paper-raised` `#FAF6EC`, `--ink` `#1E1B16`, `--ink-muted` `#5E5648`, `--cinnabar` `#9E2B1E` (nút chính, nguy hiểm), `--jade` `#2F6B57` (đã dịch, tiến độ), `--bronze` `#8C6A2A` (chỉ trang trí), `--line` `#D9CDB4`.
- **Theme đọc**: `light` Tuyên chỉ, `sepia` Hoàng quyển, `dark` Dạ nguyệt, `bamboo` Trúc lâm; chữ thân bài tương phản ≥4.5:1 (`npm run check:contrast`).
- **Chữ** (tự host qua `@fontsource/*`, không gọi CDN lúc chạy): Ma Shan Zheng cho chữ Hán trang trí, Cormorant Garamond cho tiêu đề Việt, Noto Serif / Noto Serif SC cho nội dung, Be Vietnam Pro cho chữ giao diện nhỏ.
- **Quy ước nhãn**: tên khu vực kiểu tu tiên luôn kèm nhãn rõ nghĩa (Tàng Thư Các · Thư viện, Danh Lục · Bộ tên, Thiết lập · Cài đặt…); trạng thái, lỗi, quota và hộp xác nhận luôn dùng từ thường.
- **Component dùng chung** (`web/src/lib/components/`): `Seal`, `ScrollFrame`, `JadeTablet`, `StatusChip`, `InkMountains`, `Modal`, `Cover`, `QuotaPill`. Không emoji; icon là SVG nét.

## Backlog gợi ý (đẩy qua `/opsx:propose`)

- Import qua URL / connector, chapter manifest, prefetch raw từ web; quy trình takedown
- Provider fallback ngoài Gemini (OpenRouter, Groq…) trong chuỗi
- Bộ tên chung cấp user; style profile theo truyện
- Ngữ cảnh chương trước (tóm tắt) để giữ mạch truyện
- Reader lật trang kiểu ebook; đọc offline/PWA
- Import EPUB; export EPUB
- Nhiều tài khoản, BYOK qua giao diện
- Theo dõi token/chi phí theo chương
