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
   └──────────┬─────────────────────────┬────────────────┘
              │                         ▼
              │           ┌──────────────────────────────┐
              │           │ pipeline/                    │  prompt 3 phần → SectionParser
              │           │ prompts · sections · translator│ (TITLE/BODY/NAMES) → sự kiện
              │           └──────────────┬───────────────┘
              ▼                          ▼
   ┌─────────────────────────────────────────────────────┐
   │ domain/ (models + ports + lỗi dịch)                 │  không phụ thuộc gì
   └─────────────────────────────────────────────────────┘
        ▲                  ▲                       ▲            ▲
   storage/            providers/              ingest/txt   export/txt     adapters
   Postgres repo,      ChainProvider ──► gemini, anthropic,
   quota tracker,      (fallback +       openai/ollama, echo
   migrator            quota)
        └──────────────────┴───────────────────────┴────────────┘
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
| `domain/` | `Novel`, `Chapter` (status `pending`/`translating`/`translated`/`edited`/`failed`), `GlossaryEntry`, `GlossarySuggestion`, `ReadingProgress`, `ChainPolicy`; port `LLMProvider` (`stream`/`complete`), `NovelRepository`, `QuotaTracker`, `SessionStore`, `SourceLoader`, `Exporter`; lỗi `RefusalError`, `TruncatedError`, `RateQuotaError`, `DailyQuotaError`, `MalformedOutputError`, `ProviderError`; `rename.py` (thay tên theo ranh giới từ) | không gì cả |
| `pipeline/` | `prompts` (prompt 3 phần + glossary), `sections` (`SectionParser` streaming), `translator` (`ChapterTranslator`: một request mỗi chương, kiểm tra sót đoạn), `segmenter` (chỉ cắt khi vượt `NT_CHAPTER_CHAR_LIMIT`) | domain |
| `application/` | `services.py` (`LibraryService`, `GlossaryService` gồm hàng chờ đề xuất và lan truyền đổi tên, `TranslationService`, `ReaderService` tiến độ + tùy chọn, `EditingService`, `ExportService`); `jobs.py`; `prefetch.py`; `auth.py` | domain, pipeline |
| `providers/` | `chain` (`ChainProvider`: fallback theo `NT_CHAIN`, policy FOREGROUND/BACKGROUND, backoff lỗi phút, chuyển bước khi hết quota ngày), `gemini` (mặc định), `anthropic_provider`, `openai_compat` (OpenAI/Ollama), `echo` (test) + `registry` | domain |
| `storage/` | `db.py` (pool psycopg 3), `migrator.py` + `migrations/NNN_*.sql`, `postgres_repo.py`, `quota_repo.py` | domain |
| `ingest/`, `export/` | đọc TXT (tách `第X章`), xuất TXT | domain |
| `container.py` | composition root: nơi duy nhất chọn adapter cụ thể, tạo pool, chạy migration | tất cả |
| `interfaces/api` | `app.py`, `auth.py` (session cookie, CSRF header, chống brute-force), `privacy.py` (`X-Robots-Tag`, `robots.txt`), `routers/` theo nhóm, `web.py` (phục vụ SPA + fallback deep link) | application, container |
| `interfaces/cli` | import/dịch/xuất/glossary để quản trị và debug; `hash-password`; `serve` | application, container |
| `web/` | SvelteKit SPA (`adapter-static`): 6 màn `/login`, `/`, `/novels/[id]`, `/novels/[id]/chapters/[n]`, `/novels/[id]/glossary`, `/settings` | gọi API qua HTTP |

## Điểm mở rộng thường gặp

- **Provider LLM mới**: viết class kế thừa `StreamingProvider` (có `name`, `default_model`, `stream()`), phân loại lỗi thành các lớp lỗi trong `domain/ports.py`, rồi gọi `register_provider()` trong `registry.py`. Khai báo vào chuỗi qua `NT_CHAIN=provider:model,...`. Không rẽ nhánh theo tên provider trong pipeline/application.
- **Định dạng nhập** (EPUB, crawl web): hiện thực `SourceLoader`, nối trong `container.py`.
- **Định dạng xuất** (EPUB, DOCX): hiện thực `Exporter`, thêm vào dict `exporters`.
- **Thay đổi schema**: thêm file `storage/migrations/NNN_<tên>.sql` mới (không sửa file đã chạy); runner tự áp dụng lúc khởi động.

## Quyết định thiết kế

Chi tiết và phương án bị loại xem `openspec/changes/mvp-web-reader/design.md` (sau khi archive: `openspec/changes/archive/`).

- **Gemini là provider mặc định**, chạy qua chuỗi fallback `NT_CHAIN` (mặc định `gemini-3.5-flash` → `gemini-3.5-flash-lite`, cùng một key). Mục tiêu chi phí $0 với free tier. Lỗi 429 theo phút: backoff tối đa 3 lần; theo ngày: sang bước kế hoặc dừng và báo giờ reset. Không xoay vòng nhiều key/tài khoản.
- **Một request mỗi chương** (tiêu đề + nội dung + đề xuất tên), phản hồi dạng marker `<<TITLE>>`/`<<BODY>>`/`<<NAMES>>` để stream được từng đoạn.
- **Job trong process** (`TranslationJobManager`): hai làn, mỗi làn một job, mỗi chương tối đa một job. Giả định đúng một process (`uvicorn --workers 1`); job mất khi restart, chương `translating` quay về `pending`.
- **SSE** cho streaming (một chiều, tự reconnect); reverse proxy phải tắt buffering (xem `docs/DEPLOY.md`).
- **Buffer N+1**: tín hiệu đọc thật → dịch trước tối đa một chương, chỉ bằng bước 1 của chuỗi; quota dự phòng dành cho chương người dùng chủ động mở.
- **PostgreSQL** dùng chung instance `shared-postgres`, database + role riêng, pool nhỏ (`NT_DB_POOL_MAX`), migration SQL tay có `pg_advisory_lock`. Test dùng database riêng `NT_TEST_DATABASE_URL`.
- **Một người dùng**: hash argon2 trong `NT_PASSWORD_HASH`, session lưu server-side (chỉ lưu SHA-256 token), mọi trang `noindex`.

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
