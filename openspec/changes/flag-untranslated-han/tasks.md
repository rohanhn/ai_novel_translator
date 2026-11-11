# Tasks

## 1. Hàm đếm (domain)

- [x] 1.1 Tạo `domain/han_residue.py` (design D1): `is_han` (chuyển từ `chapter_split._is_han`, `chapter_split` import lại), `kept_chars`, `residue(title, text, kept) -> Residue(count, chars)`. Kiểm tra bằng `tests/test_han_residue.py` theo các scenario "Han characters left in the translation", "Clean translation", "Han character kept on purpose by the glossary", "Chinese punctuation is not counted", kèm chữ Ext B và chữ trong tiêu đề; test nhận diện ngôn ngữ của `chapter_split` vẫn pass.

## 2. Lưu trữ

- [x] 2.1 Migration `003_untranslated_han.sql` (design D2, D7): thêm cột `untranslated_han INT NOT NULL DEFAULT 0`, rồi tính sẵn bằng `regexp_count`, bỏ các chữ Hán có trong bản dịch glossary của cùng truyện. `Chapter.untranslated_han`; repo đọc và ghi cột trong `update_chapter`, `_insert_chapters`, `_chapter`. Kiểm tra bằng `tests/test_storage.py`:
  - ghi rồi đọc lại giữ đúng giá trị qua `update_chapter`, `add_chapters`, `replace_chapters`;
  - test migration theo scenario "Existing translations after upgrade": dựng chương có chữ Hán, chữ do glossary giữ và dấu câu CJK, chạy câu tính sẵn, kết quả bằng `residue(...).count`.

## 3. Ghi số đếm (application)

- [x] 3.1 `translate_chapter` và `edit_chapter` ghi `untranslated_han` (design D3); payload `completed` của job có `untranslated_han`. Kiểm tra bằng test service với provider `echo` hoặc provider giả trả text có chữ Hán, theo các scenario "Han characters left in the translation", "Re-translation", "Manual edit removes the leftovers"; tải lại cả bộ giữ số đếm của chương `reuse`, và chương `changed` có số đếm 0 (`tests/test_chapter_update.py`).
- [x] 3.2 Prompt thêm dòng "không để lại chữ Hán" (design D6). Kiểm tra bằng test prompt: dòng có trong system prompt, và system prompt giống nhau giữa các đoạn.

## 4. API và CLI

- [x] 4.1 `ChapterSummary.untranslated_han`, `ChapterOut.untranslated_chars` (design D4); CLI `novel chapters` in cờ "còn N chữ chưa dịch". Kiểm tra bằng test API (danh sách có số đếm, chi tiết có tập chữ, chữ do glossary giữ không có trong tập) và test CLI (CliRunner).

## 5. Web

- [x] 5.1 `lib/reader/highlight.ts` (`splitHan`), nhãn `untranslated_han` trong `status.ts` và bộ lọc "có vấn đề", thông báo kèm "Dịch lại" và tô sáng trên màn đọc, cặp màu tô sáng trong `check:contrast` (design D5). Kiểm tra `npm run check` và `npm run check:contrast` pass.
- [x] 5.2 Playwright `web/e2e/untranslated-han.spec.ts` (mobile 360px và desktop), provider `echo`. Đặt bản dịch có chữ Hán qua API sửa tay (sửa tay cũng tính số đếm), rồi kiểm tra:
  - mục lục có nhãn "Còn chữ chưa dịch";
  - màn đọc có thông báo kèm số chữ, và `mark.han-residue` bao đúng các chữ Hán;
  - sửa lại không còn chữ Hán thì nhãn và tô sáng biến mất;
  - không cuộn ngang, vùng chạm ≥44px.

  Kiểm tra `npm run build && npm run test:e2e` pass.

## 6. Tài liệu và kiểm tra tích hợp

- [ ] 6.1 Cập nhật `docs/ARCHITECTURE.md`: bảng lớp thêm `domain/han_residue.py`, ghi chú cờ `untranslated_han` cạnh `possible_omission`. Kiểm tra bằng `grep` tên module trong tài liệu.
- [ ] 6.2 Chạy toàn bộ `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `cd web && npm run check && npm run check:contrast && npm run build && npm run test:e2e`, `openspec validate flag-untranslated-han --strict`. Kiểm tra tất cả pass.
- [ ] 6.3 Thử trên app local với truyện "剑烛大荒" đã dịch bằng Gemini. Sau khi nâng cấp (migration), chương 2 có nhãn và đúng 72 chữ được tô; sửa tay hoặc dịch lại thì nhãn cập nhật đúng.

## Workflow follow-up

- Mở pull request từ nhánh `flag-untranslated-han` vào `main` khi người dùng yêu cầu.
- `/opsx:archive` sau khi review xong.
