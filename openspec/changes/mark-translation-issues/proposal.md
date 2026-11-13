# Proposal: Đánh dấu và sửa chỗ dịch sai ngay khi đọc

## Why

Khi đọc gặp một tên dịch sai, một câu còn chữ Hán hay một câu Hán-Việt ghép chữ khó hiểu, người đọc hiện chỉ có hai cách. Một là mở trình sửa cả chương và tự tìm lại chỗ đó. Hai là dịch lại cả chương: tốn một lượt và có thể làm hỏng chỗ khác. Cách sửa tên đúng là thêm vào bộ tên (glossary), nhưng phải rời màn đọc sang trang bộ tên và tự gõ lại nguyên văn tiếng Trung. Cần sửa được tại chỗ, đúng đoạn đang đọc.

## What Changes

- Trên màn đọc, chạm vào một đoạn dịch để mở **thanh thao tác của đoạn**, gồm ba lựa chọn:
  - **Thêm vào bộ tên:**
    - hộp thoại hiện đoạn gốc tiếng Trung tương ứng để chọn hoặc gõ nguyên văn;
    - nhập bản dịch đúng;
    - điền sẵn chữ đang bôi đen trong bản dịch làm "cách dịch sai đang thấy".
    Khi lưu, tên được thêm vào bộ tên. Nếu có "cách dịch sai", nó được thay bằng bản dịch đúng trong mọi chương đã dịch có chứa nguyên văn, theo đúng quy tắc khi đổi tên hiện có. Chương đã biên tập chỉ được gắn nhãn.
  - **Dịch lại đoạn:**
    - gửi riêng đoạn gốc tương ứng cho LLM, tốn 1 lượt, kèm bộ tên;
    - hiện bản dịch mới cạnh bản cũ;
    - người dùng chấp nhận thì thay đúng đoạn đó, hoặc bỏ qua.
  - **Sửa đoạn:** sửa trực tiếp đoạn đó, không phải mở trình sửa cả chương.
- Sửa đoạn hoặc chấp nhận đoạn dịch lại thì chương chuyển sang **đã biên tập**, như khi sửa tay cả chương, nên được bảo vệ khỏi các thay đổi tự động.
- Mọi thao tác ghi đều bị từ chối nếu chương đã đổi kể từ lúc mở (ví dụ vừa dịch lại), để không thay nhầm đoạn.
- "Dịch lại đoạn" ghép đoạn dịch với đoạn gốc theo số thứ tự. Thao tác này chỉ bật khi số đoạn dịch bằng số đoạn gốc; chương bị cờ "Có thể thiếu đoạn" thì dùng "Sửa đoạn" hoặc dịch lại cả chương.

**Ngoài phạm vi:**
- Phát hiện tự động chữ Hán còn sót (change `flag-untranslated-han`).
- Danh sách "chỗ cần xử lý sau" (ghi chú lưu lại): người dùng đã chọn sửa ngay, không ghi chú.
- Dịch lại một phần nhỏ hơn đoạn (một câu, một cụm). Đơn vị là đoạn, vì bản dịch giữ đúng cấu trúc đoạn.
- Thao tác trên bản gốc tiếng Trung hoặc trên truyện `vi` được import (không có bản gốc để dịch lại). Với truyện `vi` chỉ có "Sửa đoạn".
- Hoàn tác sau khi đã lưu.

## Capabilities

### New Capabilities
<!-- Không có -->

### Modified Capabilities
- `translation-editing`: sửa một đoạn và dịch lại một đoạn của chương (chấp nhận thì thay đúng đoạn, chương thành đã biên tập), kèm kiểm tra chương chưa đổi.
- `glossary`: thêm tên kèm "cách dịch sai đang thấy", để thay cách dịch sai trong các chương đã dịch có chứa nguyên văn.
- `web-reader`: thanh thao tác của đoạn trên màn đọc và các hộp thoại tương ứng.

## Impact

- **API:**
  - mới `PUT /api/novels/{id}/chapters/{n}/paragraphs/{i}` (sửa đoạn);
  - mới `POST /api/novels/{id}/chapters/{n}/paragraphs/{i}/retranslate` (đề xuất bản dịch mới, không lưu);
  - `PUT /api/novels/{id}/glossary` nhận thêm trường tùy chọn `observed`.
  - Các endpoint cũ giữ nguyên hành vi.
- **CLI:** không đổi. Đây là thao tác khi đọc, chỉ có trên web.
- **Schema DB:** không đổi.
- **Code:** service sửa và dịch lại đoạn ở `application/`; ghép đoạn ở `domain/`; dùng lại `ChapterTranslator`, `edit_chapter` và lan truyền tên sẵn có; web thêm thanh thao tác và hộp thoại trên màn đọc.
- **Chi phí LLM:** chỉ "Dịch lại đoạn" tốn quota, mỗi lần 1 request ngắn (một đoạn), đi qua chuỗi provider và bộ đếm quota như dịch chương. Rẻ hơn dịch lại cả chương. Thêm vào bộ tên và sửa đoạn không tốn gì.
