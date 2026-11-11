# Proposal: Phát hiện chữ Hán còn sót trong bản dịch

## Why

Model đôi khi để lại chữ Hán trong bản dịch. Ví dụ chương 2 của "剑烛大荒" dịch bằng `gemini-3.5-flash` còn 72 chữ Hán (蕩, 幽, 瞬…), nhưng app vẫn ghi chương là "Đã dịch" và không báo gì. Người đọc chỉ phát hiện khi đọc tới, và cách chữa duy nhất là đoán chỗ sai rồi sửa tay hoặc dịch lại cả chương. Chất lượng dịch là ưu tiên số 1, nên lỗi này phải được bắt tự động.

## What Changes

- Sau mỗi lần dịch, app đếm chữ Hán còn trong tiêu đề và nội dung bản dịch. Chữ nằm trong bản dịch của một mục glossary không bị tính, vì người dùng chủ động giữ nó.
- Số chữ còn sót được lưu cùng chương và tính lại mỗi khi bản dịch đổi: dịch, dịch lại, sửa tay. Khi tải lại cả bộ, chương được tái dùng giữ nguyên số đã tính.
- Chương còn chữ Hán có nhãn **"Còn chữ chưa dịch"** trong mục lục, cùng kiểu với nhãn "Có thể thiếu đoạn". Màn đọc hiện thông báo kèm số chữ và nút "Dịch lại".
- Khi đọc, các chữ Hán còn sót được **tô sáng** để thấy ngay chỗ cần sửa.
- Prompt dịch thêm một yêu cầu rõ ràng: không để lại chữ Hán trong bản dịch.
- Chương đã dịch từ trước được tính số chữ còn sót ngay khi nâng cấp, không cần dịch lại.

**Ngoài phạm vi:**
- Tự động dịch lại khi phát hiện chữ Hán. Việc này tốn thêm quota và phải làm lại luồng streaming đang hiển thị; người dùng tự bấm "Dịch lại" khi cần.
- Đánh dấu và sửa từng từ hoặc đoạn khi đọc (thêm glossary, dịch lại một đoạn, sửa tại chỗ). Phần này thuộc change riêng `mark-translation-issues`.
- Phát hiện câu văn Hán-Việt ghép chữ hoặc dịch kém. Không có cách đo đáng tin mà không gọi thêm LLM.
- Chặn lưu bản dịch còn chữ Hán. Bản dịch vẫn được lưu và chỉ gắn cờ, giống quy tắc thiếu đoạn.

## Capabilities

### New Capabilities
<!-- Không có -->

### Modified Capabilities
- `translation-pipeline`: thêm kiểm tra chữ Hán còn sót sau khi dịch (gắn cờ, không từ chối), tính lại khi bản dịch đổi.
- `web-reader`: nhãn "Còn chữ chưa dịch" trong mục lục, thông báo kèm nút "Dịch lại" và tô sáng chữ Hán còn sót trên màn đọc.

## Impact

- **Schema DB:** thêm cột số chữ Hán còn sót vào bảng chương. Có migration, kèm tính sẵn cho các chương đã dịch.
- **API:** dữ liệu chương (danh sách, chi tiết, sự kiện hoàn tất dịch) thêm trường số chữ còn sót. Không bỏ hay đổi trường cũ.
- **CLI:** `novel chapters` hiện thêm cờ "còn chữ chưa dịch" giống cờ thiếu đoạn.
- **Code:** hàm đếm thuần ở `domain/`; dịch, sửa tay và cập nhật chương ở `application/` ghi số đếm; repo thêm cột; web thêm nhãn, thông báo và tô sáng.
- **Chi phí LLM:** không tăng. Không có request mới; prompt chỉ dài thêm một dòng.
