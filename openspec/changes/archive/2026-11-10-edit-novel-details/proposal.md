# Proposal: Sửa thông tin truyện (tên, ảnh bìa, tác giả, giới thiệu)

## Why

Hiện truyện chỉ có `title`, đặt một lần lúc import (thường là tên file như `kiem-lai-full`). Bìa do component `Cover` tự vẽ từ id và tên, và truyện chưa có chỗ ghi tác giả hay giới thiệu. Thư viện vì vậy khó nhận ra truyện nào là truyện nào, nhất là khi có nhiều bản cùng tên file. Người dùng cần sửa được các thông tin này sau khi import.

## What Changes

- Truyện có thêm ba thông tin, đều không bắt buộc:
  - **tác giả**: tối đa 100 ký tự;
  - **giới thiệu ngắn**: tối đa 2000 ký tự, giữ xuống dòng;
  - **ảnh bìa**.
- **Sửa tên, tác giả, giới thiệu** qua `PATCH /api/novels/{id}`.
  - Chỉ cập nhật trường được gửi lên.
  - Tên sau khi bỏ khoảng trắng phải có 1–200 ký tự.
  - Gửi chuỗi rỗng cho tác giả hoặc giới thiệu thì xoá trường đó.
- **Ảnh bìa upload từ máy**, qua `PUT /api/novels/{id}/cover` dạng multipart.
  - Nhận JPG, PNG hoặc WebP, tối đa 10 MB.
  - Server kiểm tra ảnh bằng cách giải mã thật, xoay theo EXIF, thu về khung tối đa 600×900 và mã hoá lại thành WebP. Metadata (EXIF, GPS) bị bỏ.
  - Ảnh lưu trong PostgreSQL, trong bảng riêng `novel_covers`.
- **Ảnh bìa từ link trên internet**, qua `POST /api/covers/fetch {url}`.
  - Chỉ nhận link http/https.
  - Server tải ảnh về (tối đa 10 MB, timeout 15 giây, tối đa 3 lần chuyển hướng) rồi xử lý giống ảnh upload.
  - Kết quả gửi lại để xem trước, chưa lưu gì. Bấm "Lưu" thì ảnh được lưu qua `PUT /api/novels/{id}/cover`, nên upload và link dùng chung một đường lưu.
  - Trình duyệt không bao giờ tự tải link ảnh, nên trang ảnh không biết người dùng đang dùng app và không có hotlink.
  - Chống SSRF: từ chối mọi địa chỉ nội bộ, kể cả khi tới đó qua chuyển hướng hoặc qua tên miền trỏ về IP nội bộ; không gửi cookie hay thông tin đăng nhập.
- **Gỡ ảnh bìa**: `DELETE /api/novels/{id}/cover`. Bìa quay về kiểu tự vẽ.
- **Xem ảnh bìa**: `GET /api/novels/{id}/cover`.
  - Cần đăng nhập và có header noindex như mọi endpoint khác.
  - Cache `private`; URL có tham số phiên bản nên đổi ảnh không bị cache cũ.
- **Phản hồi API**: `NovelOut` và `LibraryItem` có thêm `author`, `description` và `cover_url`. `cover_url` là `null` khi truyện chưa có ảnh.
- **Web**:
  - Trang chi tiết truyện có nút "Sửa thông tin". Nút mở hộp thoại gồm: ảnh bìa (xem trước, "Chọn ảnh…", ô "Hoặc dán link ảnh" + nút "Lấy ảnh", "Gỡ ảnh"), tên, tác giả và giới thiệu ngắn.
  - Trang chi tiết hiển thị tác giả và giới thiệu.
  - Thư viện dùng ảnh bìa thật nếu có, hiện tác giả dưới tên, và ô tìm kiếm khớp cả tên lẫn tác giả.
  - Component `Cover` nhận ảnh. Thiếu ảnh hoặc ảnh lỗi thì quay về bìa tự vẽ.
- **CLI**:
  - Lệnh mới `novel edit <id> [--title] [--author] [--description]`.
  - `novel list` hiện thêm tác giả.
  - CLI không có lệnh ảnh bìa.
- **Xuất TXT** dùng tên truyện hiện tại, như trước. Tên mới sẽ có hiệu lực ngay ở lần xuất sau.

**Đã chốt với người dùng:** ảnh bìa lấy từ hai nguồn, upload từ máy hoặc dán link ảnh trên internet. Với link, server tự tải ảnh về; ảnh luôn được lưu thành bản sao trong PostgreSQL, không hotlink.

## Capabilities

### New Capabilities

(không có)

### Modified Capabilities

- `novel-library`: thêm requirement sửa thông tin truyện (tên, tác giả, giới thiệu) và requirement ảnh bìa (upload, lấy từ link kèm chống SSRF, kiểm tra, thu nhỏ, gỡ, xem khi đã đăng nhập).
- `web-reader`: thêm requirement màn sửa thông tin truyện và hiển thị ảnh bìa, tác giả, giới thiệu ở thư viện và trang chi tiết. Spec này được tạo khi archive `mvp-web-reader`.
- `interfaces`: thêm requirement lệnh CLI `novel edit`.

## Out of scope

- Tìm bìa tự động (tra cứu theo tên truyện), crop hoặc xoay ảnh trong trình duyệt.
- Tự lấy tác giả hay giới thiệu từ phần đầu file khi import (vd. dòng "Tác giả: …").
- Sửa ngôn ngữ nguồn sau khi import. Muốn đổi giữa truyện cần dịch và bản dịch có sẵn thì phải import lại.
- Thể loại, tag, trạng thái hoàn thành, tên gốc tiếng Trung.
- Lệnh ảnh bìa trong CLI.
- Đưa giới thiệu hay tên truyện vào prompt dịch.

## Impact

- **Schema DB**: migration `002_novel_details.sql`.
  - Thêm vào `novels`: `author TEXT`, `description TEXT`, `cover_updated_at TIMESTAMPTZ`, đều cho phép NULL nên dữ liệu cũ giữ nguyên.
  - Bảng mới `novel_covers(novel_id PK → novels ON DELETE CASCADE, mime, data BYTEA, width, height)`.
  - Xoá truyện thì ảnh bìa bị xoá theo.
- **API**:
  - Thêm `PATCH /api/novels/{id}`, `PUT`/`DELETE`/`GET /api/novels/{id}/cover`, `POST /api/covers/fetch`.
  - `NovelOut` có thêm trường mới; client cũ bỏ qua được nên không phá vỡ tương thích.
- **CLI**: thêm `novel edit`; `novel list` thêm cột tác giả.
- **Dependency**:
  - Thêm `Pillow` (wheel sẵn cho Linux, không cần build). Ảnh hưởng image Docker là không đáng kể.
  - `httpx` chuyển từ dev dependency sang dependency chính. Thực tế nó đã được cài vì `google-genai` phụ thuộc vào nó.
- **Chi phí LLM**: không có. Không thêm request nào tới provider.
- **Bảo mật và riêng tư**:
  - Ảnh được giải mã lại và mã hoá lại, kèm giới hạn số pixel để chống bom giải nén.
  - Endpoint ảnh được bảo vệ bằng session như các endpoint khác.
  - Có request mạng ra ngoài, nhưng chỉ khi người dùng bấm "Lấy ảnh": mỗi lần bấm một request, không tự thử lại, không dùng proxy từ biến môi trường, User-Agent là tên app chung (không chứa email).
  - Chặn SSRF: chỉ cổng 80/443; từ chối IP loopback, mạng riêng, link-local (gồm metadata cloud `169.254.169.254`), multicast, reserved và các dạng IPv6 tương ứng; kiểm tra lại sau mỗi lần chuyển hướng; kết nối thẳng tới IP đã kiểm để chống DNS rebinding.
- **Phụ thuộc change khác**: delta `web-reader` cần `mvp-web-reader` đã được archive. Nên archive `mvp-web-reader` và `smart-txt-import` trước khi archive change này.
