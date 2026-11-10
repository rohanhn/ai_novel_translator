# Tasks

## 1. Bộ tách chương thuần (domain)

- [x] 1.1 Tạo `domain/chapter_split.py`: chuẩn hóa xuống dòng, regex các họ tiêu đề (Hán, Việt, đặc biệt, quyển), luật đứng riêng (≤80 ký tự, dấu câu cuối dòng), chuẩn hóa số (full-width, số Hán gồm `零〇两百千万`, La Mã); kiểm tra bằng `tests/test_chapter_split.py` phủ mọi scenario của requirement "Chinese chapter headings", "Vietnamese chapter headings", "Heading lines must stand alone"
- [x] 1.2 Thêm `detect_language` (ngưỡng 30% chữ Hán, ký tự đặc trưng tiếng Việt, mẫu 200.000 ký tự đầu); kiểm tra bằng test cho `zh`, `vi`, `unknown` (văn bản Latin không dấu) và bản convert lẫn ít chữ Hán
- [x] 1.3 Thêm `plan()`/`apply()`: ghép quyển vào tiêu đề chương kế, chỉ dùng quyển làm chương khi không có tiêu đề chương, phần mở đầu (mặc định giữ khi ≥200 ký tự), fallback một chương, áp tập ranh giới tùy ý (gộp/tách); kiểm tra bằng test cho các requirement "Volume headings", "Front matter before the first heading", "Fallback when no heading is found", "Adjustable split"
- [x] 1.4 Thêm cảnh báo (`number_gap`, `number_repeat`, `number_decrease`, `too_short`, `too_long`, `front_matter`, `no_headings`) kèm `message` tiếng Việt thường, bỏ qua tiêu đề đặc biệt và quyển khi kiểm tra dãy số; thêm fixture `tests/fixtures/split/kiem-lai-vi.txt` (đoạn ví dụ của người dùng là đoạn giữa file: đặt sau tiêu đề `Chương 1: …` và vài đoạn thân chương 1, tiếp theo là `Chương 2: Mở cửa` rồi `Chương 3: …`) và một fixture raw tiếng Trung; kiểm tra bằng test requirement "Chapter number sequence warnings", "Chapter length warnings" và test fixture: đúng 3 chương, không có phần mở đầu, ranh giới chỉ ở các dòng `Chương N`, câu `… rồng ngẩng đầu”.` và chú thích `(3) …` nằm ở cuối thân chương 1; thêm test hiệu năng: văn bản 50 MB tổng hợp được `plan()` trong dưới 10 giây

## 2. Import ở application, ingest và CLI

- [x] 2.1 Đổi port `SourceLoader` thành `read_text(path) -> str`; `TxtLoader` chỉ đọc và giải mã (UTF-8 → GB18030), bỏ `CHAPTER_RE`; kiểm tra test loader cũ (encoding) được chuyển sang API mới và pass
- [ ] 2.2 Thêm `Novel.pretranslated`, `LibraryService.import_text(text, title, lang, plan)`: tạo truyện `zh` (chương `pending`) hoặc `vi` (chương `translated`, `translated_* = nguồn`, `provider="import"`, `glossary_version` của truyện); `import_novel(path, title, lang)` dùng `plan()` mặc định và trả cảnh báo; kiểm tra bằng test scenario "Vietnamese file with chapter headings", "Language override", "File without chapter headings", "Empty file" của `novel-library`
- [ ] 2.3 Chặn truyện `pretranslated`: `PreTranslatedError` trong `TranslationService` (mọi đường dịch và dịch lại), `PrefetchService` trả `reason="pretranslated"`; kiểm tra bằng test không có request nào tới provider `echo`, biên tập chuyển `edited`, xuất TXT đủ chương
- [ ] 2.4 CLI `novel import --lang zh|vi`, in ngôn ngữ, số chương và cảnh báo, `unknown` → `zh` kèm cảnh báo; kiểm tra bằng `tests/test_cli.py` (CliRunner) với fixture tiếng Việt và tiếng Trung
- [ ] 2.5 Cập nhật `docs/ARCHITECTURE.md` (bảng lớp: `domain/chapter_split.py`, `application/imports.py`, `SourceLoader.read_text`; điểm mở rộng "Định dạng nhập"); kiểm tra tài liệu khớp tên module thật bằng `grep`

## 3. Bản xem trước và API

- [ ] 3.1 `application/imports.py` `ImportDraftService` (dict + lock, id `token_urlsafe(16)`, hết hạn 60 phút từ lần dùng cuối, tối đa 3 draft, `create/adjust/lines/commit/discard`, `DraftExpiredError`) và nối trong `container.py`; kiểm tra bằng test với đồng hồ giả: hết hạn, bỏ draft cũ nhất khi tạo thứ 4, commit xóa draft, commit lần hai báo hết hạn
- [ ] 3.2 Router `interfaces/api/routers/imports.py` theo design D3 (POST, PUT, GET lines `count` ≤500, POST commit, DELETE; 410 khi hết hạn; dùng chung kiểm tra 50 MB/file rỗng/đuôi `.txt` với upload cũ); `POST /api/novels` nhận `lang`; `NovelOut` thêm `source_lang`, `pretranslated`; preflight `POST .../translate` trả 409 cho truyện `pretranslated`; kiểm tra bằng `tests/test_api_imports.py` phủ các scenario của "Upload novel from the web" (gồm không lưu gì trước khi xác nhận, gộp tiêu đề nhầm, preview hết hạn sau khi tạo container mới, file 60 MB) và "Pre-translated novels never reach an LLM"; route yêu cầu session và header CSRF

## 4. Web

- [ ] 4.1 Client API cho `/api/imports` và kiểu `ImportPreview` trong `web/src/lib/`; `UploadDialog` thành hai bước (chọn file → xem trước), 410 thì báo và quay lại bước 1; kiểm tra `npm run check` không lỗi
- [ ] 4.2 Màn xem trước: tên truyện, công tắc ngôn ngữ có nhãn rõ nghĩa, số chương, lọc "chỉ chương có cảnh báo", khối phần đầu file (giữ/bỏ), danh sách chương ảo hóa với cảnh báo chữ thường cạnh chương, "Gộp vào chương trước", mở rộng chương để xem dòng và "Tách chương tại đây", "Lưu vào thư viện"/"Huỷ"; kiểm tra bằng Playwright `web/e2e/import.spec.ts` (mobile 360px và desktop): upload file tiếng Việt có số chương nhảy cóc → thấy cảnh báo ở đúng chương, gộp một chương, tách một chương, lưu → mục lục đúng số chương; huỷ → không có truyện mới; không cuộn ngang, vùng chạm ≥44px
- [ ] 4.3 Reader và mục lục với truyện `pretranslated`: nhãn "Bản dịch có sẵn", ẩn "Xem bản gốc"/"Dịch lại", không gọi translate, không gửi reading-signal; kiểm tra bằng Playwright: mở chương của truyện tiếng Việt không có request `/translate` hay `/reading-signal`, biên tập vẫn lưu được

## 5. Kiểm tra tích hợp

- [ ] 5.1 Chạy `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `cd web && npm run check && npm run build && npm run test:e2e` toàn bộ; kiểm tra tất cả pass
- [ ] 5.2 Thử trên app local với một file TXT thật nhiều chương của người dùng (tiếng Việt) và một raw tiếng Trung: xem trước, chỉnh, lưu, đọc; kiểm tra số chương và tiêu đề khớp file, không có request LLM cho truyện tiếng Việt (quota bước 1 không đổi)
- [ ] 5.3 `openspec validate smart-txt-import --strict` pass

## Workflow follow-up

- Archive `mvp-web-reader` trước (change này sửa requirement "Upload novel from the web" và thêm vào spec `web-reader` do change đó tạo ra).
- Archive change này bằng `/opsx:archive` sau khi review.
