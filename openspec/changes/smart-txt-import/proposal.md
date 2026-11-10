# Proposal: Import TXT thông minh (tách chương + xem trước)

## Why

File `.txt` người dùng tải về thường gộp nhiều chương, và tiêu đề chương không theo một mẫu cố định. Hiện `TxtLoader` chỉ nhận dòng `第X章/回/节/卷`; file không có dòng nào khớp (ví dụ file tiếng Việt với "Chương 2: Mở cửa") bị lưu thành **một** "Chương 1" khổng lồ. Kết quả là không đọc được theo chương, và với raw tiếng Trung thì tốn quota vì một chương bị cắt thành nhiều request. Người dùng cũng có sẵn bản dịch tiếng Việt muốn đọc trong cùng thư viện mà không phải dịch lại.

## What Changes

**Tách chương**
- Bộ tách chương mới nhận diện tiêu đề cho cả hai loại file:
  - **Raw tiếng Trung:** `第X章/回/节`, số Hán hoặc Ả Rập, `序章/楔子/引子/尾声/番外/后记`, `Chapter N`.
  - **Bản tiếng Việt:** `Chương N`, `Hồi N`, `Chương N: …`, `Chương N - …`, `Mở đầu/Phiên ngoại/Ngoại truyện/Vĩ thanh`.
- Dòng quyển (`第X卷`, `Quyển N`, `Tập N`) không còn tách thành chương riêng. Tên quyển được ghép vào tiêu đề chương ngay sau nó. Chỉ khi file không có tiêu đề cấp chương thì quyển mới được dùng làm chương. **BREAKING:** trước đây `第X卷` tạo một chương riêng.
- Dòng chỉ được coi là tiêu đề khi đứng riêng, ngắn và mở đầu bằng mẫu tiêu đề. Chú thích kiểu `(3) Vỡ vỡ bình an: …` và câu văn có chữ "chương" không bị nhận nhầm.
- Không dùng LLM để tách chương, nên chi phí LLM vẫn là 0.

**Nhận diện ngôn ngữ và bản dịch có sẵn**
- Tự nhận diện file là tiếng Trung hay tiếng Việt. Người dùng có thể đổi lại ở màn xem trước.
- File tiếng Việt được lưu như **bản dịch có sẵn**:
  - Chương ở trạng thái Đã dịch, nhãn nguồn "Bản dịch có sẵn".
  - Đọc được ngay, không bao giờ gửi tới LLM.
  - Không có "Dịch lại", không có prefetch, không có "Xem bản gốc".
  - Vẫn biên tập tay và xuất file như bình thường.

**Xem trước trước khi lưu (web)**
- Upload trên web không lưu ngay. App trả về bản xem trước gồm:
  - Ngôn ngữ nhận diện được.
  - Danh sách chương: số thứ tự, tiêu đề, độ dài, vài chữ đầu.
  - Phần đầu file trước tiêu đề đầu tiên.
  - Các cảnh báo: số chương nhảy cóc, trùng số hoặc lùi số; chương quá ngắn hoặc quá dài; có phần mở đầu chưa rõ xử lý ra sao.
- Người dùng chỉnh rồi xác nhận mới lưu:
  - Bỏ một dòng tiêu đề, tức gộp chương đó vào chương trước.
  - Tách chương tại một dòng bất kỳ.
  - Giữ phần mở đầu thành chương "Mở đầu", hoặc bỏ đi.
  - Đổi ngôn ngữ, đặt tên truyện.
- Bản xem trước giữ trong bộ nhớ server có hạn dùng. Khi hết hạn hoặc server restart thì người dùng phải upload lại.

**CLI**
- `novel import` dùng cùng bộ tách và bộ nhận diện ngôn ngữ, lưu ngay không qua xem trước, in cảnh báo ra màn hình. Thêm tùy chọn `--lang zh|vi` để ghi đè ngôn ngữ.

### Out of scope
- Tách chương bằng LLM; import EPUB/DOCX/HTML; import qua URL.
- Ghép bản Trung và bản Việt của cùng một truyện thành song ngữ.
- Dịch từ tiếng Việt sang ngôn ngữ khác, hoặc dùng LLM viết lại bản tiếng Việt cho mượt.
- Chỉnh tách chương sau khi đã lưu. Muốn tách lại thì xóa truyện rồi upload lại.
- Trích tên riêng cho bộ tên từ bản tiếng Việt.

## Capabilities

### New Capabilities
- `chapter-splitting`: nhận diện tiêu đề chương (Trung/Việt), xử lý dòng quyển và phần mở đầu, nhận diện ngôn ngữ file, sinh cảnh báo về kết quả tách.

### Modified Capabilities
- `novel-library`:
  - "Import novel from TXT" đổi quy tắc tách và thêm nhận diện ngôn ngữ.
  - "Upload novel from the web" chuyển sang upload → xem trước → xác nhận.
  - Thêm requirement cho truyện bản dịch có sẵn (tiếng Việt).
- `web-reader`: chương của truyện bản dịch có sẵn không có "Xem bản gốc", "Dịch lại" hay prefetch, và có nhãn nguồn "Bản dịch có sẵn".

**Phụ thuộc:** spec `web-reader` và requirement "Upload novel from the web" đến từ change `mvp-web-reader`, change này đã xong nhưng chưa archive. Cần archive `mvp-web-reader` trước khi archive change này.

## Impact

- **Code:**
  - `ingest/`: bộ tách chương mới thay `CHAPTER_RE` và bộ nhận diện ngôn ngữ, đều là code thuần, không phụ thuộc framework.
  - `application/`: `LibraryService` thêm bước xem trước và xác nhận; thêm kho bản xem trước trong bộ nhớ; `TranslationService` và prefetch từ chối chương của truyện tiếng Việt.
  - `interfaces/api`: thêm endpoint xem trước và xác nhận. Endpoint upload cũ (lưu ngay) vẫn dùng được cho script.
  - `interfaces/cli`: `import --lang`, in cảnh báo.
  - `web/`: dialog Upload thêm bước xem trước; reader ẩn các thao tác không áp dụng.
- **API:**
  - Thêm nhóm `/api/imports`:
    - `POST /api/imports`: upload, trả bản xem trước.
    - `PUT /api/imports/{id}`: chỉnh ranh giới chương.
    - `GET /api/imports/{id}/lines`: xem các dòng để chọn điểm tách.
    - `POST /api/imports/{id}/commit`: xác nhận và lưu.
    - `DELETE /api/imports/{id}`: hủy bản xem trước.
  - `POST /api/novels` nhận thêm trường `lang` tùy chọn.
  - `POST .../translate` trả 409 với chương của truyện tiếng Việt.
- **Schema DB:** không đổi. Dùng `novels.source_lang = 'vi'` cùng các cột sẵn có của `chapters` (`status`, `provider`, `translated_text`).
- **Chi phí LLM:** không tăng. Truyện tiếng Việt không bao giờ gọi LLM, và raw tiếng Trung được tách đúng chương nên không còn tình trạng một "chương" khổng lồ bị cắt thành nhiều request.
