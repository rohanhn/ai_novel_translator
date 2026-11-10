# Design: Import TXT thông minh

## Context

- `ingest/txt_loader.py` vừa đọc file (đoán UTF-8/GB18030) vừa tách chương bằng một regex `第X[章回节卷]`. `LibraryService.import_novel(path)` gọi loader rồi lưu ngay.
- Web upload (`POST /api/novels`) ghi file tạm rồi gọi `import_novel`, nên mọi upload đều được lưu ngay mà không qua bước kiểm tra.
- `Novel` đã có `source_lang`/`target_lang` (mặc định `zh`/`vi`). `Chapter` đã có `translated_*`, `status`, `provider`, `model`. Không cần đổi schema.
- App chạy đúng một process (design D4 của `mvp-web-reader`), nên dữ liệu tạm trong bộ nhớ là chấp nhận được.
- Lý do và phạm vi xem `proposal.md`; hành vi xem `specs/`.

## Goals / Non-Goals

**Goals:**
- Logic tách chương là code thuần, test được bằng chuỗi văn bản, dùng chung cho CLI, API cũ và luồng xem trước.
- Chỉ server tính kết quả tách và cảnh báo; client chỉ gửi danh sách ranh giới.
- Không đổi schema DB.

**Non-Goals:**
- Lưu bản xem trước qua restart, hoặc dùng chung giữa nhiều process.
- Nhận diện tiêu đề bằng thống kê hay LLM; chỉ dùng luật có thể giải thích.

## Decisions

### D1. Bộ tách là code thuần ở `domain/chapter_split.py`

- Lý do đặt ở `domain/`: `application/` cần gọi nó (xem trước, áp ranh giới), mà `application` không được import `ingest/`. Tiền lệ: `domain/rename.py` cũng là logic chữ thuần nằm ở domain.
- `ingest/txt_loader.py` chỉ còn đọc và giải mã file. Port `SourceLoader` đổi từ `load(path) -> list[RawChapter]` thành `read_text(path) -> str`.
- API của module:
  - `detect_language(text) -> "zh" | "vi" | "unknown"`
  - `find_headings(lines) -> list[Heading]`. `Heading` gồm số dòng, loại (`chapter`/`special`/`volume`), số chương đã chuẩn hóa hoặc `None`, và text.
  - `plan(text) -> SplitPlan`: ranh giới mặc định, phần mở đầu và lựa chọn mặc định cho nó, các chương và cảnh báo.
  - `apply(text, boundaries, keep_front_matter) -> SplitPlan`: dựng lại chương và cảnh báo từ một tập ranh giới bất kỳ.
- Đơn vị ranh giới là **số dòng** (0-based) của văn bản sau khi chuẩn hóa xuống dòng về `\n`. Client chỉ gửi danh sách số nguyên, server tính lại mọi thứ.
- Đọc từng dòng, tối đa 80 ký tự đầu mỗi dòng, chạy O(n). File 50 MB vẫn xử lý trong vài giây.

**Luật nhận diện** (chi tiết hành vi xem spec `chapter-splitting`):
- Regex neo đầu dòng cho từng họ tiêu đề: Hán, Việt, đặc biệt và quyển.
- Dòng bị loại nếu dài hơn 80 ký tự hoặc kết thúc bằng dấu câu (trừ dấu ngay sau số).
- Không có điều kiện "trước đó là dòng trống": nhiều file TXT không để dòng trống quanh tiêu đề, nên điều kiện này sẽ bỏ sót tiêu đề thật.
- Chuẩn hóa số: chữ số full-width, số Hán (`一千零二十`, `两百`, `〇`) và số La Mã (`XII`).
- Dòng quyển: khi file có tiêu đề cấp chương, text của quyển được giữ làm `volume_prefix` và ghép vào tiêu đề chương ngay sau. Khi không có tiêu đề chương, quyển trở thành chương.

**Nhận diện ngôn ngữ:**
- Đếm trên tối đa 200.000 ký tự đầu: chữ Hán (`\p{Han}` qua khoảng Unicode CJK) và chữ cái Latin.
- `han / (han + latin) ≥ 0.3` → `zh`. Không phải `zh` mà có ký tự đặc trưng tiếng Việt (`ăâđêôơư` và các nguyên âm có dấu) → `vi`. Còn lại → `unknown`.

**Phương án bị loại:**
- Dùng thư viện langdetect: thêm dependency cho một phép đếm đơn giản, và kết quả không ổn định với văn bản ngắn.
- Dùng LLM để tách: tốn quota, chậm với file lớn, và kết quả không tái lập được.

### D2. Bản xem trước giữ trong bộ nhớ: `application/imports.py`

- `ImportDraftService` giữ `dict[draft_id → Draft]`. `Draft` gồm text đã giải mã, tên file, `SplitPlan` hiện tại và thời điểm tạo.
- Draft id sinh bằng `secrets.token_urlsafe(16)`. Truy cập được bảo vệ bằng `threading.Lock`.
- **Hạn dùng:** 60 phút kể từ lần dùng cuối, dọn dẹp lười mỗi khi gọi service. Giữ tối đa 3 draft; tạo draft thứ 4 thì bỏ draft cũ nhất. Với file 50 MB, tổng bộ nhớ tối đa vào khoảng 150–300 MB, chấp nhận được cho một user.
- **Các thao tác:**
  - `create(filename, data)`: đoán encoding qua loader, rồi `plan`.
  - `adjust(id, boundaries, keep_front_matter)`: gọi `apply`.
  - `lines(id, start, count)`: trả về một cửa sổ dòng để UI chọn điểm tách.
  - `commit(id, title, lang)`: tạo truyện qua `LibraryService`, rồi xóa draft.
  - `discard(id)`.
- Draft không tồn tại hoặc đã hết hạn → `DraftExpiredError`, API trả **410 Gone** với thông báo "Bản xem trước đã hết hạn, hãy upload lại".

**Phương án bị loại:**
- Bảng `import_drafts` trong Postgres: phải thêm migration và job dọn dẹp cho dữ liệu chỉ sống vài phút.
- Client giữ toàn bộ text rồi gửi lại khi xác nhận: phải upload 50 MB hai lần qua mạng điện thoại.

### D3. API

| Method | Path | Trả về |
|---|---|---|
| `POST` | `/api/imports` (multipart `file`) | 201 `ImportPreview` |
| `PUT` | `/api/imports/{id}` body `{boundaries, keep_front_matter}` | 200 `ImportPreview` (tính lại) |
| `GET` | `/api/imports/{id}/lines?start=&count=` | 200 `{start, lines[]}`, `count` ≤ 500 |
| `POST` | `/api/imports/{id}/commit` body `{title?, lang, boundaries, keep_front_matter}` | 201 `NovelOut`; 410 nếu hết hạn |
| `DELETE` | `/api/imports/{id}` | 204 |

- `ImportPreview` gồm:
  - `id`, `filename`, `detected_lang`, `line_count`
  - `front_matter {start_line, end_line, chars, excerpt, keep}`
  - `chapters[] {number, start_line, end_line, title, chars, excerpt, warnings[]}`
  - `warnings[]` (cấp file)
  - Mỗi cảnh báo có dạng `{code, message, params}`. `code` gồm `number_gap`, `number_repeat`, `number_decrease`, `too_short`, `too_long`, `front_matter`, `no_headings`. `message` là câu tiếng Việt thường để UI hiện thẳng.
- `commit` nhận lại `boundaries` để việc xác nhận không phụ thuộc vào thứ tự của các lần `PUT`.
- Giới hạn 50 MB và lỗi file rỗng giữ như upload hiện tại; phần kiểm tra được tách thành hàm dùng chung.
- `POST /api/novels` (lưu ngay) giữ lại cho script và CLI-qua-API, nhận thêm form field `lang` tùy chọn và dùng `plan()` mặc định.
- `NovelOut` thêm `source_lang` (nếu chưa có) và `pretranslated: bool` để web biết cách hiển thị.
- Mọi route đều nằm sau auth và CSRF header như các route khác.

### D4. Truyện bản dịch có sẵn

- **Nhận diện:** `Novel.source_lang == Novel.target_lang` (`vi`/`vi`). Thuộc tính tính sẵn `Novel.pretranslated` nằm ở domain.
- **Khi lưu**, mỗi chương có:
  - `source_text = translated_text = body`, `title = translated_title = title`
  - `status = translated`, `provider = "import"`, `model = None`, `chain_step = None`
  - `glossary_version = novel.glossary_version`
- Giữ `source_text` để các truy vấn và ràng buộc hiện có không phải xử lý trường hợp NULL.
- **Chặn ở application** (không rẽ nhánh theo tên provider):
  - `TranslationService.translate*`: truyện `pretranslated` → `PreTranslatedError` (lớp con của `InvalidOperationError`). API trả 409 trong bước kiểm tra trước của `POST .../translate`.
  - `PrefetchService`: truyện `pretranslated` → trả `reason="pretranslated"`, không tạo job.
- Biên tập, xuất file, tiến độ đọc và xóa không cần đổi.
- Lan truyền đổi tên: luật cũ (raw chứa term) vẫn chạy. Với truyện tiếng Việt, raw là chính bản Việt nên chỉ thay khi term nguồn xuất hiện trong text. Không thêm luật riêng.

### D5. Web

- `UploadDialog` thành hai bước:
  - **Bước 1:** chọn file, kiểm tra 50 MB ở client như hiện tại, gọi `POST /api/imports`.
  - **Bước 2:** màn xem trước, toàn màn hình trên mobile.
- **Màn xem trước:**
  - Phần trên: tên truyện, công tắc ngôn ngữ "Tiếng Trung · cần dịch" / "Tiếng Việt · bản dịch có sẵn", số chương, tổng cảnh báo kèm nút "Chỉ hiện chương có cảnh báo".
  - Khối "Phần đầu file" (nếu có): đoạn trích và công tắc Giữ làm "Mở đầu" / Bỏ.
  - Danh sách chương ảo hóa, vì có thể có hàng nghìn chương. Mỗi dòng gồm số, tiêu đề, độ dài, đoạn trích, cảnh báo (`StatusChip` màu cảnh báo, chữ thường) và nút "Gộp vào chương trước".
  - Mở rộng một chương để tải các dòng của nó (`GET .../lines`); mỗi dòng có nút "Tách chương tại đây".
  - Mỗi lần gộp hoặc tách gọi `PUT` rồi vẽ lại danh sách. Hai nút "Lưu vào thư viện" và "Huỷ".
- Gặp 410 thì hiện thông báo và quay về bước 1.
- **Reader** với truyện `pretranslated`: ẩn "Xem bản gốc" và "Dịch lại", không gọi translate, không gửi reading-signal, hiện nhãn "Bản dịch có sẵn". Danh sách chương và thư viện hiện số chương "Đã dịch" như bình thường.
- Phong cách theo D11 của `mvp-web-reader` (token, nhãn thường cho cảnh báo). Không thêm mockup; bố cục theo dialog Upload hiện có.

### D6. CLI

- `novel import <file> [--title] [--lang zh|vi]`: gọi `plan()` mặc định, in ngôn ngữ, số chương và từng cảnh báo, rồi lưu ngay.
- `--lang` ghi đè ngôn ngữ. Ngôn ngữ `unknown` mà không có `--lang` thì dùng `zh` và in cảnh báo.

### Các lớp bị thay đổi

| Lớp | Thay đổi |
|---|---|
| `domain/` | mới `chapter_split.py`; `Novel.pretranslated`; port `SourceLoader.read_text`; lỗi `PreTranslatedError` (application) |
| `ingest/` | `TxtLoader` chỉ đọc và giải mã (bỏ `CHAPTER_RE`) |
| `application/` | mới `imports.py` (`ImportDraftService`); `LibraryService.import_text(text, title, lang, plan)`; chặn ở `TranslationService` và `PrefetchService` |
| `interfaces/api` | router `imports.py`; `POST /api/novels` thêm `lang`; `NovelOut.pretranslated`; preflight 409 |
| `interfaces/cli` | `import --lang`, in cảnh báo |
| `container.py` | nối `ImportDraftService` |
| `web/` | `UploadDialog` hai bước + màn xem trước; reader ẩn các thao tác dịch với truyện `pretranslated` |
| `pipeline/`, `providers/`, `storage/` | không đổi; không có migration |

## Risks / Trade-offs

- **[Nhận nhầm tiêu đề]**, ví dụ dòng thoại ngắn "Hồi 3 rồi." → Luật dấu câu cuối dòng, giới hạn 80 ký tự, cảnh báo số chương bất thường, và màn xem trước cho gộp lại. Bộ test có fixture lấy từ file thật (đoạn ví dụ của người dùng).
- **[Bỏ sót tiêu đề kiểu lạ]**, ví dụ `【第一章】` hay `001.` → Màn xem trước có "Tách chương tại đây"; cảnh báo chương quá dài gợi ý chỗ nên tách. Thêm mẫu mới thì chỉ sửa luật trong một module.
- **[BREAKING: `第X卷` không còn là chương riêng]** → Truyện đã import trước đây không bị ảnh hưởng, vì không tách lại. Chỉ file import mới dùng luật mới.
- **[Draft mất khi restart hoặc deploy]** → Trả 410 kèm hướng dẫn upload lại. Draft chỉ sống vài phút nên rủi ro thấp.
- **[Bộ nhớ khi nhiều draft lớn]** → Giới hạn 3 draft, hết hạn 60 phút, một người dùng.
- **[Nhận diện ngôn ngữ sai]**, ví dụ bản convert Hán-Việt lẫn nhiều chữ Hán → Ngưỡng 30% chữ Hán, và ngôn ngữ đổi được ở màn xem trước. File `unknown` mặc định `zh`.
- **[Danh sách hàng nghìn chương chậm trên điện thoại]** → Danh sách ảo hóa; `excerpt` cắt ở 80 ký tự; dòng của chương chỉ tải khi mở rộng.

## Migration Plan

- Không đổi schema và không có migration. Deploy như bình thường; truyện cũ giữ nguyên.
- Rollback: chạy lại image cũ. Truyện `vi` đã import vẫn đọc được, vì đã ở trạng thái `translated`, nhưng image cũ không chặn nút "Dịch lại" cho chúng.
