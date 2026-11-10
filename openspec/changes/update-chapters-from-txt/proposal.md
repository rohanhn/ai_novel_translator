# Proposal: Cập nhật chương từ TXT cho truyện có sẵn

## Why

Truyện dài liên tục ra chương mới, nhưng hiện mọi lần import TXT (CLI `novel import`, web `POST /api/imports` → `commit`) đều tạo **truyện mới**. Muốn có chương mới thì phải import lại thành một truyện khác, và mất bản dịch, bản sửa tay, glossary, tiến độ đọc, bìa và thông tin truyện. Với truyện vài trăm chương, việc này vừa tốn quota dịch lại vừa phá trải nghiệm đọc.

## What Changes

- Thêm luồng **Cập nhật từ TXT** trên trang truyện. Luồng dùng lại bước upload và xem trước cách tách chương của import thông minh, rồi bắt người dùng **chọn một trong hai chế độ**, không có mặc định:
  - **Thêm chương**: tìm *điểm nối* là chương cuối của truyện trong file mới. Không thấy thì lùi tối đa 5 chương cuối. Vẫn không thấy thì xét số chương: liên tiếp thì nối toàn bộ, có khoảng trống thì cảnh báo, không đọc được số thì người dùng tự chọn chương bắt đầu. Chỉ các chương sau điểm nối được thêm, với số thứ tự nối tiếp. Chương cũ không bị đụng tới.
  - **Tải lại cả bộ**: thứ tự chương lấy theo file mới. Mỗi chương mới được so với chương cũ:
    - nội dung gốc giống nhau → **tái dùng** bản dịch, trạng thái và cờ, kể cả bản đã sửa tay;
    - cùng tiêu đề nhưng nội dung gốc đã đổi → **bỏ bản dịch cũ, kể cả bản sửa tay**, chuyển `pending`;
    - không khớp → chương mới `pending`.
  - Chương cũ không còn trong file: người dùng **chọn từng chương để xóa** (mặc định không chọn, có "chọn tất cả"). Chương không xóa được giữ ngay sau chương khớp đứng trước nó.
- Màn **xem trước thay đổi** cho biết số chương thêm, giữ, đổi và có thể xóa, số bản sửa tay sẽ mất, và tiến độ đọc sẽ chuyển sang đâu. Chỉ khi người dùng xác nhận mới ghi, và ghi trong một transaction.
- Giữ nguyên khi cập nhật: tên, tác giả, giới thiệu, bìa, glossary, đề xuất glossary. Tiến độ đọc được chuyển theo chương khớp.
- Chặn cập nhật khi:
  - ngôn ngữ file khác ngôn ngữ truyện;
  - truyện đã thay đổi sau lúc xem trước;
  - ở chế độ tải lại, đang có job dịch của truyện chờ hoặc chạy.

**Ngoài phạm vi:**
- Nhập và cập nhật từ link URL (manifest, connector, tải raw lười). Đây sẽ là change riêng, dùng lại bộ so khớp của change này.
- Tự động theo dõi chương mới, lịch chạy, cron.
- Tự dịch hàng loạt chương mới sau khi cập nhật. Chương mới chỉ được dịch qua prefetch hoặc dịch tay như hiện tại.
- Đổi thứ tự chương bằng tay, gộp hoặc tách chương đã lưu.
- Lưu số chương vào DB.
- CLI ngang tính năng với web. CLI chỉ thêm chế độ "Thêm chương" ở dạng tối thiểu.

## Capabilities

### New Capabilities
- `chapter-update`: cập nhật danh sách chương của một truyện đã có từ file TXT. Gồm so khớp chương cũ và mới, hai chế độ Thêm và Tải lại, xem trước thay đổi, các điều kiện chặn, và cách giữ hoặc chuyển bản dịch, tiến độ đọc, glossary.

### Modified Capabilities
<!-- Không có: import tạo truyện mới, đọc, dịch, glossary giữ nguyên hành vi. -->

## Impact

- **API:**
  - `POST /api/imports` nhận thêm trường `novel_id` (tùy chọn) để tạo draft cập nhật.
  - Endpoint mới để tính thay đổi và để áp cập nhật trên draft.
  - Các endpoint import hiện tại giữ nguyên hành vi.
- **CLI:** `novel import <file> --into <novel_id>` cho chế độ Thêm chương.
- **Schema DB:** không đổi, không có migration.
- **Code:**
  - module so khớp thuần mới ở `domain/`;
  - service cập nhật ở `application/`;
  - repo thêm thao tác thay danh sách chương trong một transaction;
  - `TranslationJobManager` thêm truy vấn job theo truyện;
  - web thêm hộp thoại cập nhật trên trang truyện, dùng lại `ImportPreview`.
- **Chi phí LLM:**
  - Chế độ Thêm không tốn gì.
  - Chế độ Tải lại không dịch lại chương có nội dung gốc không đổi. Chỉ chương đổi hoặc mới tốn quota, và chỉ khi được dịch (prefetch hoặc dịch tay), không dịch hàng loạt.
