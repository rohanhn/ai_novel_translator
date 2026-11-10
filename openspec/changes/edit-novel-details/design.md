# Design: Sửa thông tin truyện

## Context

- **Bảng `novels`** (`001_initial.sql`) hiện có `title`, `source_lang`, `target_lang`, `glossary_version`, `created_at`, `last_read_at`.
  - `Novel` (domain) có các trường tương ứng.
  - `PostgresRepository._novel` map từng dòng sang `Novel`.
  - `library_overview` dùng `SELECT n.*`.
- **API**: `NovelOut` và `LibraryItem` (`interfaces/api/schemas.py`) trả về truyện. Router `routers/library.py` có `GET/POST/DELETE /api/novels...`.
- **Lỗi**:
  - `ValueError` → 400.
  - `NotFoundError` → 404.
  - `InvalidOperationError` → 409.
  - Request body sai kiểu → 422 (Pydantic).
- **Bảo vệ**: mọi `/api/*` cần session. Mọi request đổi dữ liệu cần header `X-Requested-With`. Mọi response có `X-Robots-Tag` (`privacy.py`).
- **Web**:
  - `Cover.svelte` vẽ bìa từ `id` và `title`.
  - Thư viện (`routes/+page.svelte`) và trang chi tiết (`routes/novels/[id]/+page.svelte`) dùng `Cover`.
  - Đã có `Modal` (kích thước `default` và `wide`, vừa sửa để luôn nằm trong khung nhìn).
  - Client `api.ts` có sẵn `patch`, `put`, `del`. Upload multipart đã có mẫu ở `library/imports.ts`.
- **Môi trường**:
  - Không có volume lưu file. App chạy một container, dữ liệu nằm ở `shared-postgres`.
  - Chưa có thư viện xử lý ảnh (Pillow chưa cài).

## Goals / Non-Goals

**Goals:**

- Sửa tên, tác giả, giới thiệu ngắn và ảnh bìa từ web. Sửa tên, tác giả, giới thiệu từ CLI.
- Ảnh bìa lấy từ máy hoặc từ link trên internet (server tự tải về).
- Ảnh bìa an toàn: giải mã thật, mã hoá lại, giới hạn kích thước, bỏ metadata.
- Tải ảnh từ link không thể bị lợi dụng để gọi vào mạng nội bộ (SSRF).
- Ảnh lưu cùng chỗ với dữ liệu riêng tư và chỉ phục vụ khi đã đăng nhập.
- Không làm chậm danh sách thư viện: không đọc byte ảnh khi liệt kê.

**Non-Goals:**

- Tìm bìa tự động, crop hoặc xoay trong trình duyệt, nhiều kích thước ảnh (thumbnail riêng).
- Tự lấy tác giả từ file khi import.
- Lệnh ảnh trong CLI.

## Decisions

### D1. Lớp bị thay đổi

| Lớp | Thay đổi |
|---|---|
| `domain/` | `Novel` thêm `author`, `description`, `cover_updated_at`. Hằng giới hạn và hàm thuần `normalize_details(title, author, description)` (trim, chuỗi rỗng → `None`, kiểm độ dài), ném `NovelDetailsError(field, message)` (lớp con của `ValueError`). Port `CoverImageProcessor.process(data: bytes) -> CoverImage(mime, data, width, height)`, ném `InvalidImageError(ValueError)`. Port `CoverImageFetcher.fetch(url) -> bytes`, ném `CoverFetchError(ValueError)` (có `reason`: `invalid_url`, `blocked_address`, `download_failed`, `too_large`). Port `NovelRepository` thêm `update_novel_details`, `set_cover`, `get_cover`, `delete_cover`. |
| `application/` | `LibraryService.update_details(novel_id, *, title=UNSET, author=UNSET, description=UNSET)`, `set_cover(novel_id, data)`, `remove_cover(novel_id)`, `get_cover(novel_id)`. `LibraryService.preview_cover_from_url(url) -> CoverImage` (fetcher → processor, không lưu). Dùng sentinel `UNSET` để phân biệt "không gửi" với "gửi rỗng → xoá". |
| `media/` (adapter mới) | `PillowCoverProcessor` (Pillow) và `SafeHttpImageFetcher` (`httpx` + network backend kiểm IP, D7). Cả hai nối trong `container.py`; `build_container(..., cover_fetcher=None)` nhận bộ tải ảnh thay thế (test truyền bản giả), `Container` có trường `cover_fetcher`. |
| `storage/` | Migration `002_novel_details.sql`; repo hiện thực các hàm mới; `_novel` map thêm cột. |
| `interfaces/api` | `PATCH /api/novels/{id}`; `PUT`/`DELETE`/`GET /api/novels/{id}/cover`; `NovelOut` thêm `author`, `description`, `cover_url`; `POST /api/covers/fetch`; handler cho `NovelDetailsError` (400 + `field`), `InvalidImageError` (400 + `field: "cover"`) và `CoverFetchError` (400 + `field: "cover_url"`, kèm `reason`). |
| `interfaces/cli` | `novel edit`; `novel list` thêm tác giả. |
| `web/` | `Modal` thêm snippet `footer` (thân cuộn, footer cố định); `Cover` nhận `src`; `EditNovelDialog.svelte`; client `library/details.ts`; trang chi tiết và thư viện hiển thị thông tin mới, tìm theo tác giả. |

`pipeline/` và `providers/` không đổi. Không có request LLM nào. Request mạng ra ngoài duy nhất là tải ảnh từ link, và chỉ khi người dùng bấm.

### D2. Schema và migrate dữ liệu cũ

```sql
-- 002_novel_details.sql
ALTER TABLE novels
    ADD COLUMN author           TEXT,
    ADD COLUMN description      TEXT,
    ADD COLUMN cover_updated_at TIMESTAMPTZ;

CREATE TABLE novel_covers (
    novel_id BIGINT PRIMARY KEY REFERENCES novels(id) ON DELETE CASCADE,
    mime     TEXT   NOT NULL,
    data     BYTEA  NOT NULL,
    width    INT    NOT NULL,
    height   INT    NOT NULL
);
```

- **Dữ liệu cũ**: mọi cột mới cho phép NULL, nên truyện cũ có `author`, `description` và `cover_updated_at` đều NULL (không có ảnh). Không cần backfill. Runner tự áp dụng lúc khởi động, có `pg_advisory_lock`.
- **Vì sao bảng riêng**: `library_overview` và `get_novel` dùng `n.*`. Để `BYTEA` (vài chục KB mỗi truyện) trong `novels` thì mỗi lần liệt kê sẽ kéo cả ảnh. Bảng riêng chỉ được đọc ở `GET .../cover`.
- **Xoá**: `ON DELETE CASCADE` xoá ảnh theo truyện.
- `cover_updated_at` nằm trong `novels` để biết có ảnh hay không và để tạo URL có phiên bản mà không phải join.
- `set_cover` ghi `novel_covers` (UPSERT) và cập nhật `cover_updated_at = now()` trong cùng một `unit_of_work`. `delete_cover` xoá dòng và đặt `cover_updated_at = NULL`.
- **Phương án bị loại**:
  - Lưu file trên đĩa: container không có volume nên ảnh sẽ mất khi deploy.
  - Object storage: thêm dịch vụ ngoài, không cần thiết cho một người dùng.

### D3. Xử lý ảnh (Pillow, adapter `media/pillow_cover.py`)

1. **Kiểm tra trước khi giải mã.**
   - Router đọc file theo chunk và dừng ngay khi vượt 10 MB (413), giống `read_txt_upload`.
   - Đặt `Image.MAX_IMAGE_PIXELS = 40_000_000`; Pillow ném `DecompressionBombError` khi vượt, và lỗi đó được map thành `InvalidImageError`.
2. **Mở và xác minh định dạng.**
   - `Image.open(BytesIO(data))`.
   - Chỉ chấp nhận `img.format in {"JPEG", "PNG", "WEBP"}`. Định dạng lấy từ nội dung file, không tin đuôi file hay `Content-Type`.
   - Gọi `img.load()` để giải mã thật; file hỏng sẽ báo lỗi ở bước này.
3. **Chuẩn hoá.**
   - `ImageOps.exif_transpose` để xoay đúng chiều ảnh chụp.
   - Chuyển sang `RGB`; nếu có alpha thì ghép lên nền `#F3EDE0` (`--paper`) để bìa PNG trong suốt không thành đen.
4. **Thu nhỏ.** `img.thumbnail((600, 900), Image.LANCZOS)` giữ tỉ lệ và không phóng to ảnh nhỏ.
5. **Mã hoá lại.**
   - Lưu thành `WEBP`, `quality=82`, `method=4`, không truyền `exif`, nên metadata bị bỏ.
   - Trả về `CoverImage("image/webp", bytes, w, h)`.
   - Kết quả thường dưới 100 KB.

Vì sao làm ở server, không resize bằng canvas ở trình duyệt: mã hoá lại phía server là lớp bảo vệ thật (không lưu file polyglot, không lưu metadata), và client không cần tin cậy. Web vẫn kiểm định dạng và kích thước trước khi gửi để báo lỗi sớm (spec web-reader).

Vì sao chọn Pillow: chuẩn de-facto, có wheel sẵn cho CPython 3.10–3.14 trên manylinux, đọc được JPEG/PNG/WebP và có `exif_transpose`. Phương án bị loại: tự đọc header để lấy kích thước mà không giải mã; cách này không thu nhỏ hay bỏ metadata được.

### D4. API

- **`PATCH /api/novels/{id}`**
  - Body `NovelDetailsIn { title?: str, author?: str | null, description?: str | null }`.
  - Dùng `model_fields_set` để chỉ truyền trường có mặt vào `update_details`; với `author`/`description`, `null` được xử lý như chuỗi rỗng, tức là xoá. `title: null` → 400 `field: "title"` "Tên truyện không được để trống."
  - Không đặt `max_length` ở Pydantic: mọi giới hạn độ dài do `normalize_details` kiểm, để lỗi luôn là 400 có `field` (không phải 422).
  - Body rỗng → 400 "Cần ít nhất một trường".
  - Trả `200 NovelOut`.
- **`PUT /api/novels/{id}/cover`**
  - multipart `file`. Giới hạn 10 MB theo chunk (413). File rỗng → 400.
  - Trả `200 NovelOut` (có `cover_url` mới).
- **`POST /api/covers/fetch`**
  - Body `{ url: str }`. Không đặt `max_length` ở Pydantic; bộ tải ảnh tự kiểm 2000 ký tự và trả 400 `invalid_url` để form hiện lỗi cạnh ô link.
  - Tải và xử lý ảnh, trả `Response(webp, media_type="image/webp")` kèm header `X-Cover-Width`/`X-Cover-Height`, `Cache-Control: no-store`. Không lưu gì.
  - Không gắn với truyện nào nên không có `{id}` trong đường dẫn; vẫn cần session và CSRF header như mọi `POST`.
  - Router dùng `def` đồng bộ, chạy trong threadpool, nên timeout 15 giây không chặn event loop.
- **`DELETE /api/novels/{id}/cover`** → 204, idempotent: gỡ khi chưa có ảnh vẫn trả 204.
- **`GET /api/novels/{id}/cover`**
  - Trả `Response(data, media_type=mime)` với `Cache-Control: private, max-age=31536000, immutable`.
  - Không có ảnh → 404.
  - Session và `X-Robots-Tag` do middleware sẵn có lo.
  - Query `?v=` chỉ để bust cache; server bỏ qua giá trị của nó.
- **`cover_url`** = `/api/novels/{id}/cover?v={int(cover_updated_at.timestamp()*1000)}`, hoặc `None` khi chưa có ảnh.
  - Dùng timestamp thay vì bộ đếm: sau khi gỡ rồi upload lại, giá trị vẫn mới, nên trình duyệt không lấy ảnh cũ trong cache.
- **Lỗi**:
  - `NovelDetailsError` → 400 `{detail, field: "title" | "author" | "description"}`.
  - `InvalidImageError` → 400 `{detail, field: "cover"}`.
  - `CoverFetchError` → 400 `{detail, field: "cover_url", reason}`. Ví dụ: "Chỉ nhận link http hoặc https.", "Không được tải ảnh từ địa chỉ nội bộ.", "Không tải được ảnh từ link này (máy chủ trả lỗi 404).", "Ảnh ở link này lớn hơn 10 MB."
  - Thông báo bằng tiếng Việt thường, vd. "File không phải ảnh JPG, PNG hoặc WebP.", "Tên truyện không được để trống.", "Giới thiệu tối đa 2000 ký tự."
- **Độ dài** đếm theo ký tự Unicode sau khi chuẩn hoá NFC và trim. `description` giữ `\n` và chuẩn hoá `\r\n` → `\n`.

### D5. CLI

```
novel edit <novel_id> [--title T] [--author A] [--description D]
```

- Typer option mặc định `None` nghĩa là không gửi; `""` nghĩa là xoá. Không có option nào → `_fail` (thoát mã 1).
- `NotFoundError` và `NovelDetailsError` → `_fail` kèm thông báo.
- `novel list` in `#id\ttitle\tauthor|-\tsrc→tgt`.

### D6. Web

- **`Cover.svelte`**
  - Thêm prop `src?: string | null`.
  - Khi có `src`: render `<img src alt="" loading="lazy" decoding="async">` phủ khung (`object-fit: cover`), giữ khung viền đồng.
  - `onerror` → bật cờ `broken`, quay về bìa tự vẽ.
  - Ảnh đi cùng tiêu đề hiển thị ngay bên cạnh nên dùng `alt=""`; component vẫn `aria-hidden` như cũ.
- **`library/details.ts`**
  - `updateDetails(id, patch)`, `uploadCover(id, file)` (FormData), `removeCover(id)`.
  - `coverFileProblem(file)`: chỉ nhận `image/jpeg|png|webp` (kiểm cả đuôi file), tối đa 10 MB, và trả câu báo lỗi thường.
  - `MAX_COVER_BYTES`.
  - `fetchCoverFromUrl(url) -> Blob`: gọi `POST /api/covers/fetch`, trả Blob WebP để xem trước và để upload khi lưu.
- **`library/EditNovelDialog.svelte`**
  - Dùng `Modal` với snippet `footer` mới: `Modal` giới hạn chiều cao theo khung nhìn (`100dvh`), thân hộp cuộn riêng, footer chứa nút Huỷ/Lưu luôn hiện. Trên màn ≤640 px hộp chiếm toàn màn hình như cỡ `wide`. Các hộp hiện có không truyền `footer` thì giữ nguyên bố cục.
  - **Cột ảnh**: `Cover` xem trước bằng `URL.createObjectURL` và thu hồi URL khi đóng; nút "Chọn ảnh…" (input file ẩn, `accept="image/jpeg,image/png,image/webp"`) và "Gỡ ảnh" (chỉ hiện khi đang có ảnh, hoặc vừa chọn ảnh). Bấm "Gỡ ảnh" khi vừa chọn ảnh mới: bỏ ảnh vừa chọn, xem trước bìa tự vẽ, và khi lưu thì gỡ luôn ảnh đang có (nếu có). Chọn ảnh khác sau khi bấm gỡ thì huỷ trạng thái gỡ.
  - **Link ảnh**: ô "Hoặc dán link ảnh" (`type=url`) và nút "Lấy ảnh". Bấm thì nút chuyển "Đang tải ảnh…" và bị khoá; thành công thì Blob trả về được xem trước như một file đã chọn. Lỗi hiện cạnh ô link, ảnh xem trước cũ giữ nguyên. Trình duyệt không bao giờ đặt link người dùng dán vào `<img src>`.
  - **Trường nhập**: "Tên truyện" (bắt buộc, `maxlength=200`), "Tác giả" (`maxlength=100`), "Giới thiệu ngắn" (textarea, bộ đếm `n/2000`).
  - **Khi lưu**, theo thứ tự:
    1. `PATCH` nếu có trường văn bản đổi.
    2. `PUT cover` nếu đã chọn ảnh mới (file từ máy hoặc Blob lấy từ link), hoặc `DELETE cover` nếu đã bấm gỡ.
    3. Gọi `onsaved(novel)` với `NovelOut` cuối cùng.
  - Lỗi 400 có `field` hiện cạnh trường đó và giữ nguyên dữ liệu đã nhập.
  - Nếu `PATCH` thành công mà ảnh lỗi: báo lỗi ở ô ảnh, giữ dialog mở. Phần văn bản đã lưu và được báo rõ ("Đã lưu thông tin; ảnh bìa chưa lưu: …").
  - Nút Lưu và Huỷ nằm trong `footer` của `Modal`, ngoài vùng cuộn.
- **Trang chi tiết**
  - Nút "Sửa thông tin" trong `.actions`.
  - Dưới `h1` hiện "Tác giả: …" (nếu có).
  - Giới thiệu là đoạn `white-space: pre-line`. Nếu dài hơn 6 dòng thì gập lại, kèm nút "Xem thêm" / "Thu gọn".
  - Lưu xong thì gán `novel = saved`; `<title>` tự cập nhật.
- **Thư viện**
  - Card và khối "đang đọc" truyền `src={n.cover_url}` vào `Cover`, hiện tác giả nhỏ dưới tên.
  - Lọc theo `title` hoặc `author` (không phân biệt hoa thường).
  - Thư viện tải lại danh sách mỗi lần mở trang nên thấy ngay thông tin mới.
- **Types**: `Novel` và `LibraryItem` thêm `author: string | null`, `description: string | null`, `cover_url: string | null`.

### D7. Tải ảnh từ link an toàn (adapter `media/http_fetcher.py`)

Luồng: người dùng dán link → `POST /api/covers/fetch` → `SafeHttpImageFetcher.fetch(url)` lấy byte → `PillowCoverProcessor.process` → trả WebP để xem trước → người dùng bấm Lưu → `PUT .../cover` với Blob đó. Ảnh đã xử lý chỉ khoảng 100 KB nên gửi đi gửi lại không tốn kém, và chỉ có một đường lưu ảnh.

1. **Kiểm tra link trước khi gọi mạng**: `urllib.parse.urlsplit`; scheme `http`/`https`; có host; không có `user:pass@`; cổng rỗng, 80 hoặc 443; dài tối đa 2000 ký tự. Sai → `CoverFetchError("invalid_url")`, không có request nào.
2. **Kiểm tra IP ở tầng kết nối**: lớp con của `httpcore.NetworkBackend` (bọc `SyncBackend`) override `connect_tcp(host, port, ...)`:
   - `socket.getaddrinfo(host, port)`.
   - Mọi IP phải là địa chỉ public: `ipaddress.ip_address(ip).is_global` và không `is_multicast`. Chỉ cần một IP không đạt là từ chối (`blocked_address`).
   - IPv6 nhúng IPv4 phải được tách ra và kiểm cả hai: IPv4-mapped (`::ffff:a.b.c.d`, `ipv4_mapped`), NAT64 well-known (`64:ff9b::/96`, 32 bit cuối), 6to4 (`2002::/16`, `sixtofour`) và Teredo (`2001::/32`, `teredo`). Lý do: `ipaddress.ip_address("64:ff9b::7f00:1").is_global` trả `True` dù trỏ tới 127.0.0.1 qua NAT64 (đã thử trên Python của dự án).
   - Kết nối tới chính IP đã kiểm. TLS vẫn dùng `server_hostname` là tên miền gốc, vì httpcore gọi `start_tls` với host ban đầu, nên chứng chỉ và SNI vẫn đúng. Cách này chặn DNS rebinding: không có lần phân giải thứ hai nào.
   - Backend được gắn vào `httpcore.ConnectionPool(network_backend=...)` và bọc trong một `httpx.BaseTransport` mỏng.
3. **Client**: `httpx.Client(transport=..., trust_env=False, follow_redirects=False, timeout=httpx.Timeout(15, connect=5))`; header `User-Agent: NovelTranslator/1.0 (cover fetch)`, `Accept: image/jpeg,image/png,image/webp`, `Accept-Encoding: identity` (chống bom gzip: httpx tự giải nén nên `Content-Length` nén không phản ánh kích thước thật); không gửi cookie, `Authorization` hay `Referer`. Constructor nhận `timeout`, `max_bytes`, `max_redirects` (mặc định 15 s / 10 MB / 3) để test dùng giá trị nhỏ.
4. **Chuyển hướng tự xử lý**: tối đa 3 lần. Mỗi `Location` được kiểm lại bước 1, và bước 2 tự áp dụng khi kết nối.
5. **Giới hạn tổng thời gian và kích thước**: có hạn chót 15 giây cho toàn bộ (kể cả chuyển hướng). `Content-Length` > 10 MB → từ chối ngay; dù có header hay không vẫn đếm byte thực nhận qua `iter_raw` và dừng khi vượt 10 MB (`too_large`). Nếu máy chủ vẫn gửi `Content-Encoding` khác `identity` → `download_failed`.
6. **Trạng thái HTTP khác 2xx** → `download_failed`, kèm mã. Không tin `Content-Type`: định dạng do Pillow quyết định (D3).
7. **Không thử lại, không cache**: mỗi lần bấm "Lấy ảnh" là một request.

Phương án bị loại:
- Trình duyệt tự tải link rồi upload: bị CORS chặn với đa số site ảnh, và trang ảnh thấy IP/trình duyệt của người dùng.
- Lưu bìa ngay khi tải: trái nguyên tắc chỉ lưu khi bấm Lưu và khó huỷ.
- Hotlink (lưu link, hiển thị trực tiếp): ảnh có thể mất, và trang ảnh biết mỗi lần người dùng mở thư viện.
- Chỉ kiểm IP bằng `getaddrinfo` trước rồi để httpx tự kết nối: bị DNS rebinding lách qua.
- Danh sách chặn tự viết theo dải IP: dễ sót; `ipaddress.is_global` của thư viện chuẩn đã bao gồm các dải private, loopback, link-local, CGNAT, documentation và reserved.

### D8. Test

- **Không gọi LLM.**
- **Ảnh test** được tạo bằng Pillow ngay trong test: JPEG 3000×4000 có EXIF Orientation=6 và GPS; PNG 300×450 có alpha; file text đổi đuôi `.jpg`; ảnh vượt `MAX_IMAGE_PIXELS` (dùng monkeypatch hạ ngưỡng).
- **Không gọi internet thật.** Test tải ảnh từ link:
  - Kiểm tra link và IP: test thuần với resolver giả (monkeypatch `getaddrinfo`) cho `127.0.0.1`, `10.0.0.5`, `169.254.169.254`, `::1`, `::ffff:127.0.0.1`, `64:ff9b::7f00:1`, `2002:7f00:1::`, `0.0.0.0`, `100.64.0.1`, tên miền trả về cả IP public lẫn IP nội bộ, tên miền trỏ về `192.168.1.10`, scheme `ftp`, cổng 8080, `user:pass@`.
  - Đường thành công, chuyển hướng, quá 10 MB, timeout, 404, `Content-Encoding: gzip`: chạy server HTTP local trong test, với `timeout`/`max_bytes` nhỏ để test nhanh; fetcher nhận `resolver` (DNS giả: tên miền test → một IP public giả) và `inner_backend` (socket tới IP public giả được chuyển về server local). Không có cờ nào tắt được việc chặn địa chỉ nội bộ, nên test chạy đúng đường kiểm tra thật. Kiểm tra request nhận được không có cookie, `Authorization` hay `Referer`, và chuyển hướng tới IP nội bộ hoặc tên miền trỏ về IP nội bộ bị từ chối mà không có request thứ hai.
  - API: `build_container(..., cover_fetcher=FakeFetcher(...))` trả ảnh có sẵn hoặc ném `CoverFetchError`; không test API nào chạm mạng.
- **Pytest**:
  - domain `normalize_details`;
  - adapter Pillow (kích thước, chiều xoay, không còn EXIF, nền alpha);
  - service (partial update, xoá trường, không đổi chương);
  - repo (cascade khi xoá truyện);
  - API (PATCH, cover PUT/GET/DELETE, 401 khi chưa đăng nhập, 403 khi thiếu CSRF header, 413, `cover_url` đổi sau khi thay ảnh, `X-Robots-Tag`);
  - CLI `edit`/`list`;
  - export dùng tên mới.
- **Playwright** (mobile 360 và desktop 1280): `POST /api/covers/fetch` được giả bằng `page.route` (trả PNG hoặc lỗi 400); kiểm tra trình duyệt không gửi request nào tới host của link. Sửa thông tin, chọn ảnh PNG tạo từ buffer, xem trước, lưu, kiểm tra thư viện; gỡ ảnh; file `.gif` bị báo lỗi; huỷ thì không đổi gì; nút Lưu nằm trong khung nhìn; không có cuộn ngang.

## Risks / Trade-offs

- **SSRF là rủi ro chính của tính năng link**: giảm thiểu bằng D7 (kiểm tra ở tầng kết nối, chuyển hướng tự xử lý, chỉ cổng 80/443, không gửi thông tin đăng nhập). App chỉ có một người dùng đã đăng nhập, và endpoint cần session lẫn CSRF header, nên người ngoài không gọi được.
- **Một số site ảnh chặn request không có Referer hoặc từ server**: lúc đó link sẽ lỗi. Báo rõ "Không tải được ảnh từ link này" kèm gợi ý tải ảnh về máy rồi chọn file. Không giả Referer hay User-Agent trình duyệt.
- **Bản quyền ảnh bìa**: ảnh được lưu bản sao trong thư viện riêng tư (noindex, không chia sẻ), đúng ràng buộc của dự án; không công khai lại ảnh.

- **Ảnh trong Postgres làm DB phình**: khoảng 100 KB × số truyện. Với thư viện cá nhân vài trăm truyện thì chỉ cỡ chục MB, chấp nhận được. Backup DB đã bao gồm ảnh, đây là ưu điểm.
- **Pillow là dependency native mới**: dùng wheel manylinux có sẵn; Dockerfile không cần thêm gói hệ thống. Pillow có lịch sử CVE trong decoder, nên giảm thiểu bằng cách chỉ mở 3 định dạng, giới hạn pixel, và luôn mã hoá lại. Ngoài ra phải giữ phiên bản Pillow mới (`>=11`).
- **Xử lý ảnh chạy trong request**: thu nhỏ một ảnh 12 MP mất khoảng 0,2–0,5 s CPU. Endpoint là `def` đồng bộ nên chạy trong threadpool, không chặn event loop. Chỉ có một người dùng, nên chấp nhận được.
- **Lưu không nguyên tử giữa văn bản và ảnh** (hai request): có thể lưu được văn bản mà ảnh lỗi. Giảm thiểu bằng cách báo rõ phần nào đã lưu (D6). Gộp tất cả vào một request multipart bị loại vì làm API phức tạp hơn mà không có lợi gì thêm cho một người dùng.
- **Thứ tự archive**: delta `web-reader` thêm requirement vào spec chỉ tồn tại sau khi archive `mvp-web-reader`. Cần archive `mvp-web-reader`, rồi `smart-txt-import`, rồi change này.
