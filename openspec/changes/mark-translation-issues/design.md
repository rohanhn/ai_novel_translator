# Design

## Context

- Sửa tay cả chương đi qua `EditingService.edit_chapter` (`PUT /api/novels/{id}/chapters/{n}`): chuẩn hóa dòng, đặt `status = edited`. Change `flag-untranslated-han` gắn việc tính lại số chữ Hán còn sót vào chính hàm này.
- Bản dịch giữ cấu trúc đoạn: mỗi đoạn nguồn là một dòng dịch (prompt). `pipeline/segmenter.split_paragraphs` tách đoạn nguồn, màn đọc tách `translated_text` theo dòng không rỗng. Khi hai số đoạn lệch quá 20%, chương có cờ `possible_omission`.
- `GlossaryService.set_term` thêm hoặc sửa tên. Khi đổi bản dịch của tên đã có, `_propagate` thay nguyên từ (`domain/rename.replace_whole_word`) trong chương `translated` có raw chứa tên và gắn nhãn `glossary_outdated`; chương `edited` chỉ được gắn nhãn.
- `ChapterTranslator.translate(novel, glossary, title, text, policy)` dịch một khối text qua chuỗi provider, có đếm quota, và trả `TranslationOutput` (text + tên đề xuất).
- Không phụ thuộc cứng vào `flag-untranslated-han`: sửa đoạn đi qua `edit_chapter`, nên change nào vào trước thì việc tính lại số chữ Hán còn sót vẫn gắn đúng chỗ.
- Màn đọc (`routes/novels/[id]/chapters/[n]/+page.svelte`) render `paragraphs` thành các `<p class="para">`, có nút xem bản gốc và `ChapterEditor` để sửa cả chương.

## Goals / Non-Goals

**Goals:**
- Dùng lại tối đa đường có sẵn: sửa đoạn đi qua `edit_chapter`, dịch lại đoạn đi qua `ChapterTranslator`, thêm tên đi qua `set_term` và `_propagate`.
- Không thêm cột hay bảng mới.

**Non-Goals:**
- Streaming khi dịch lại đoạn. Một đoạn ngắn, trả về một lần.
- Dịch lại nhiều đoạn một lượt.

## Decisions

### D1. Ghép đoạn: `domain/paragraphs.py`

- `translated_paragraphs(text) -> list[str]`: dòng không rỗng, đúng như màn đọc đang tách.
- `source_paragraph(source_text, translated_text, i) -> str | None`: trả đoạn nguồn thứ `i` khi số đoạn nguồn (`split_paragraphs`) bằng số đoạn dịch; lệch thì trả `None`.
- `replace_paragraph(text, i, new) -> str`: thay dòng không rỗng thứ `i`, giữ nguyên các dòng khác.
- Vị trí `i` tính từ 0 trong API, khớp chỉ số mảng `paragraphs` ở web.
- **Phương án bị loại:** cho phép dịch lại đoạn khi số đoạn lệch bằng cách để người dùng tự chọn đoạn nguồn. UI phức tạp hơn nhiều, trong khi chương lệch đoạn đã có cờ và cách sửa riêng (sửa đoạn, dịch lại chương).

### D2. Sửa một đoạn

- `EditingService.edit_paragraph(novel_id, index, position, expected, text)`:
  1. lấy chương; chưa có bản dịch thì `InvalidOperationError`;
  2. `text.strip()` rỗng thì `ValueError`;
  3. kiểm tra đoạn hiện tại ở `position` bằng `expected` (so sau `strip`); khác thì `StaleParagraphError` (409);
  4. tính text mới bằng `replace_paragraph`, gọi `edit_chapter(novel_id, index, None, new_text)`.

  Nhờ bước 4, chương thành `edited` và số chữ Hán còn sót được tính lại, cùng một đường với sửa cả chương.
- Đoạn mới chứa xuống dòng thì gộp các dòng bằng dấu cách, để một đoạn vẫn là một dòng và các vị trí sau không bị lệch.
- API `PUT /api/novels/{id}/chapters/{n}/paragraphs/{i}` với body `{expected, text}`, trả về `ChapterOut`.
- **Kiểm tra cũ hay mới bằng nội dung đoạn, không bằng revision chương:** chương vừa đổi ở đoạn khác (ví dụ đổi tên ở đoạn 10) vẫn cho sửa đoạn 3 nếu đoạn 3 không đổi. Ít bị từ chối oan hơn, mà vẫn không thay nhầm.

### D3. Dịch lại một đoạn

- `TranslationService.retranslate_paragraph(novel_id, index, position) -> ParagraphProposal(text, provider, model)`:
  1. truyện `vi` (`novel.source_lang == novel.target_lang` hoặc chương `provider = import`) thì `InvalidOperationError`;
  2. lấy đoạn nguồn bằng `source_paragraph`; `None` thì `InvalidOperationError`, kèm thông điệp gợi ý sửa đoạn hoặc dịch lại chương;
  3. `ChapterTranslator(...).translate(novel, glossary, title=None, text=src_para, policy=FOREGROUND)`;
  4. kết quả có nhiều dòng thì gộp thành một dòng;
  5. tên đề xuất (nếu có) vào hàng chờ như khi dịch chương (`_queue_suggestions`);
  6. không ghi gì vào chương.
- Lỗi quota và lỗi provider dùng lại ánh xạ sẵn có (429, 502).
- API `POST /api/novels/{id}/chapters/{n}/paragraphs/{i}/retranslate`, trả `{text, provider, model}`. Gọi đồng bộ trong threadpool của FastAPI: một đoạn chỉ mất vài giây, và chuỗi provider vẫn tự chờ khi bị giới hạn tốc độ.
- Chấp nhận đề xuất: web gọi API sửa đoạn (D2) với `expected` là đoạn cũ, nên chương thành `edited`.
- **Phương án bị loại:** chấp nhận thì giữ `translated`. Đoạn đó đã được người dùng chọn và duyệt; để `translated` thì lan truyền tên hoặc dịch lại có thể ghi đè mà không hỏi.

### D4. Thêm tên kèm "cách dịch sai đang thấy"

- `GlossaryService.set_term(..., observed: str | None = None)`. Khi `observed` có giá trị và khác `target`, gọi `_propagate(novel_id, source, observed, target)` cho cả tên mới lẫn tên đã có (với tên đã có, `observed` được dùng thay cho bản dịch cũ của tên). Không có `observed` thì giữ hành vi cũ.
- API `PUT /api/novels/{id}/glossary` thêm trường tùy chọn `observed` vào `GlossaryIn`.
- **Phương án bị loại:** gắn nhãn `glossary_outdated` cho mọi chương có raw chứa tên mới thêm, kể cả khi không có `observed`. Mỗi lần chấp nhận một tên đề xuất sẽ gắn nhãn chính chương vừa dịch ra tên đó, gây nhiễu.

### D5. Web

- `lib/reader/ParagraphActions.svelte`: chạm vào một `<p class="para">` (chỉ khi `hasTranslation`, không stream, không ở chế độ xem bản gốc hay sửa cả chương) thì đánh dấu đoạn đó và hiện thanh thao tác ngay dưới đoạn. Chạm lần nữa hoặc nhấn Esc thì đóng. Đoạn được chọn có `aria-selected` và viền chu sa.
- Lúc mở thanh, đọc `window.getSelection()` (nằm trong đoạn đó) để lấy chữ đang bôi đen.
- `GlossaryFromReader.svelte` (hộp thoại):
  - hiện đoạn nguồn để bôi đen (lấy từ `source_text` theo D1); không ghép được thì hiện cả bản gốc dạng cuộn;
  - các ô "Nguyên văn", "Bản dịch đúng", "Cách dịch sai đang thấy";
  - chữ bôi đen toàn chữ Hán thì điền vào "Nguyên văn", còn lại điền vào "Cách dịch sai".
- `ParagraphRetranslate.svelte`: gọi API; trong lúc chờ hiện trạng thái "Đang dịch lại đoạn…" và cho phép huỷ phía client; có kết quả thì hiện "Hiện tại" và "Đề xuất" cạnh nhau, với nút "Dùng bản mới" và "Giữ bản cũ".
- `ParagraphEdit.svelte`: textarea tại chỗ với "Lưu" và "Huỷ".
- Gặp 409 thì báo "Chương vừa thay đổi, hãy tải lại" và tải lại chương.
- Token màu và chữ theo "Thủy mặc · Chu sa"; vùng chạm ≥44px; kiểm bằng `check:contrast`.

### Các lớp bị thay đổi

| Lớp | Thay đổi |
|---|---|
| `domain/` | Mới `paragraphs.py` (thuần). |
| `application/` | `services.py`: `edit_paragraph`, `retranslate_paragraph`, `StaleParagraphError`, `set_term(observed)`. |
| `pipeline/` | Không đổi (dùng lại `ChapterTranslator`). |
| `storage/` | Không đổi. |
| `interfaces/` | API: hai route đoạn, `GlossaryIn.observed`, ánh xạ 409. Web: thanh thao tác và ba hộp thoại trên màn đọc. CLI không đổi. |
| `providers/` | Không đổi. |

## Risks / Trade-offs

- **[Rủi ro] Đoạn dịch lại thiếu ngữ cảnh** (đại từ, xưng hô của đoạn trước) nên lệch giọng với cả chương. → Người dùng xem trước rồi mới chấp nhận. Có thể thêm đoạn trước làm ngữ cảnh sau, nếu cần, mà không đổi spec.
- **[Rủi ro] `observed` quá ngắn hoặc quá chung** (ví dụ "u") sẽ thay tràn lan. → Chỉ thay nguyên từ, chỉ trong chương có raw chứa tên, chương đã biên tập không bị đụng. Hộp thoại hiện số chương sẽ bị ảnh hưởng (API `glossary/{term}/chapters` sẵn có) trước khi lưu.
- **[Đánh đổi] Chương thành `edited` sau khi sửa một đoạn**, nên lần đổi tên sau sẽ không tự thay chữ trong chương đó mà chỉ gắn nhãn. → Đúng tinh thần bảo vệ bản sửa tay; nhãn vẫn báo để người dùng xử lý.
- **[Rủi ro] Request đồng bộ bị treo lâu khi chuỗi provider chờ quota.** → Web cho huỷ phía client; server vẫn tuân theo thời gian chờ tối đa của chuỗi như khi dịch chương.

## Migration Plan

- Không có migration DB. Triển khai như bình thường; rollback bằng image cũ không ảnh hưởng dữ liệu.
