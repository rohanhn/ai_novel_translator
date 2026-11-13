# Tasks

## 1. Ghép đoạn (domain)

- [ ] 1.1 Tạo `domain/paragraphs.py` (design D1): `translated_paragraphs`, `source_paragraph` (trả `None` khi số đoạn lệch), `replace_paragraph`. Kiểm tra bằng `tests/test_paragraphs.py`: thay đúng đoạn và giữ các đoạn khác (có dòng trống xen giữa), vị trí ngoài phạm vi báo lỗi, số đoạn lệch thì `source_paragraph` trả `None`.

## 2. Service (application)

- [ ] 2.1 `EditingService.edit_paragraph` và `StaleParagraphError` (design D2). Kiểm tra bằng test service theo các scenario "Paragraph edited", "Empty paragraph rejected", "Chapter without translation", "Chapter re-translated meanwhile"; đoạn mới có xuống dòng được gộp thành một dòng.
- [ ] 2.2 `TranslationService.retranslate_paragraph` (design D3). Kiểm tra bằng test service với provider `echo` hoặc provider giả đếm request theo các scenario:
  - "Proposal returned": đúng 1 request, nội dung là đoạn nguồn, chương không đổi;
  - "Paragraph counts differ", "Quota exhausted", "Novel without source text to translate";
  - tên đề xuất vào hàng chờ.
- [ ] 2.3 `GlossaryService.set_term(observed=...)` (design D4). Kiểm tra bằng `tests/test_glossary_service.py` theo các scenario "Wrong name fixed from the reader", "Edited chapter only labelled", "Chapter without the source term untouched", "No observed rendering"; các test lan truyền tên cũ vẫn pass.

## 3. API

- [ ] 3.1 `PUT .../chapters/{n}/paragraphs/{i}`, `POST .../chapters/{n}/paragraphs/{i}/retranslate`, `GlossaryIn.observed`, ánh xạ `StaleParagraphError` → 409 (design D2–D4). Kiểm tra bằng `tests/test_api_paragraphs.py`: luồng sửa đoạn, dịch lại rồi chấp nhận (chương thành `edited`), 409 khi đoạn đã đổi, 404/422/429 theo lỗi, các route cần session và header CSRF; test API glossary với `observed`.

## 4. Web

- [ ] 4.1 Client API và kiểu; `ParagraphActions.svelte` (chọn đoạn, thanh thao tác, đọc chữ bôi đen; ẩn khi stream, khi xem bản gốc, khi sửa cả chương; truyện `vi` không có "Dịch lại đoạn") (design D5). Kiểm tra `npm run check` không lỗi.
- [ ] 4.2 Ba hộp thoại `GlossaryFromReader.svelte`, `ParagraphRetranslate.svelte`, `ParagraphEdit.svelte`: điền sẵn từ chữ bôi đen, hiện số chương bị ảnh hưởng trước khi lưu tên, so sánh "Hiện tại" và "Đề xuất", xử lý 409 bằng cách tải lại chương. Kiểm tra `npm run check` và `npm run check:contrast` pass.
- [ ] 4.3 Playwright `web/e2e/paragraph-actions.spec.ts` (mobile 360px và desktop), provider `echo`:
  - sửa đoạn: chỉ đoạn đó đổi, chương thành "Đã biên tập";
  - dịch lại đoạn: thấy đề xuất, "Giữ bản cũ" thì không đổi, "Dùng bản mới" thì đoạn đổi;
  - thêm vào bộ tên từ chữ bôi đen kèm cách dịch sai: chữ trong chương được thay, tên có trong bộ tên;
  - truyện `vi` không có "Dịch lại đoạn"; không cuộn ngang, vùng chạm ≥44px.

  Kiểm tra `npm run build && npm run test:e2e` pass.

## 5. Tài liệu và kiểm tra tích hợp

- [ ] 5.1 Cập nhật `docs/ARCHITECTURE.md`: bảng lớp thêm `domain/paragraphs.py` và hai route đoạn; ghi chú thao tác đoạn đi qua `edit_chapter`. Kiểm tra bằng `grep` tên module và route trong tài liệu.
- [ ] 5.2 Chạy toàn bộ `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `cd web && npm run check && npm run check:contrast && npm run build && npm run test:e2e`, `openspec validate mark-translation-issues --strict`. Kiểm tra tất cả pass.
- [ ] 5.3 Thử trên app local với Gemini trên một chương thật của "剑烛大荒": dịch lại một đoạn còn chữ Hán, sửa một đoạn, thêm một tên từ chữ bôi đen. Kiểm tra kết quả đúng như hộp thoại báo trước, và quota chỉ tăng 1 cho mỗi lần dịch lại đoạn.

## Workflow follow-up

- Mở pull request từ nhánh `mark-translation-issues` vào `main` khi người dùng yêu cầu.
- `/opsx:archive` sau khi review xong.
