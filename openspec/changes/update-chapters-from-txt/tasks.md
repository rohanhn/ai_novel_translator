# Tasks

## 1. Bộ so khớp thuần (domain)

- [x] 1.1 Tạo `domain/chapter_merge.py` với `StoredRef`, `Incoming`, `content_key` (bỏ khoảng trắng đầu/cuối dòng, dòng trống, NFKC, sha256), `title_key` (số chương qua `chapter_split.classify_line` + phần còn lại NFKC bỏ khoảng trắng) và `Keyer` mặc định. Kiểm tra bằng `tests/test_chapter_merge.py` theo các scenario "Whitespace-only difference" và "Numeral style difference in title".
- [x] 1.2 Thêm `plan_append` (design D1): neo theo lần xuất hiện cuối, lùi tối đa 5 chương, khớp nội dung trước tiêu đề; không có neo thì xét số liên tiếp, `gap`, `needs_start`; `start` do người dùng chọn; `differing`. Kiểm tra bằng test cho mọi scenario của "Append anchors on the last stored chapter", "Append without an anchor", "Nothing new" và "Stored chapters differ from the file".
- [x] 1.3 Thêm `plan_replace`: hai lượt ghép tham lam giữ thứ tự, các mục `reuse`/`changed`/`new`/`missing`/`kept`, vị trí chèn chương giữ lại, `delete`, thống kê và `edited_lost`. Kiểm tra bằng test cho các ca:
  - chèn chương giữa, xóa chương, đổi chỗ hai chương;
  - trùng tiêu đề ở hai quyển, trùng nội dung (hai chương "请假条");
  - chương `kept` ở đầu, chương `kept` liền nhau.
- [x] 1.4 Thêm `progress` remap. Kiểm tra bằng test theo scenario "Reading chapter shifted", "Reading chapter deleted", chương đang đọc là `changed` (về chương trước, `position = 0`) và không còn chương nào phía trước (về chương 1). Thêm test hiệu năng: 2000 chương, mỗi chương 20 KB, `plan_replace` dưới 2 giây.

## 2. Storage và job

- [x] 2.1 Repo: `add_chapters` chèn thêm `glossary_outdated`, `possible_omission`; thêm `replace_chapters(novel_id, chapters)` (DELETE rồi chèn theo lô trong `unit_of_work`); cập nhật port `NovelRepository`. Kiểm tra bằng `tests/test_storage.py`: thay danh sách giữ đủ mọi trường, lỗi giữa chừng trong `unit_of_work` thì rollback nguyên trạng.
- [x] 2.2 `TranslationJobManager`: `has_jobs_for_novel`, context manager `hold_novel`, `NovelBusyError` từ `submit` khi đang giữ; `PrefetchService` trả `reason="updating"`. Kiểm tra bằng `tests/test_jobs.py` và `tests/test_prefetch.py`: submit trong lúc giữ bị từ chối, ra khỏi khối thì submit lại được, job của truyện khác không bị ảnh hưởng.

## 3. Service cập nhật (application)

- [x] 3.1 `ImportDraftService`: `Draft.novel_id`, `create(..., novel_id)` kiểm tra truyện tồn tại; `commit` từ chối draft có `novel_id`. Tách hàm dựng chương `vi` dùng chung với `import_text` (`services.py`). Kiểm tra bằng `tests/test_import_drafts.py` (draft cập nhật cho truyện không tồn tại báo `NotFoundError`, commit draft cập nhật bị từ chối) và các test import cũ vẫn pass.
- [x] 3.2 Tạo `application/chapter_update.py` với `ChapterUpdateService.preview`: áp ranh giới, kiểm tra ngôn ngữ, gọi `plan_append`/`plan_replace`, tính `revision`, không ghi gì. Nối trong `container.py`. Kiểm tra bằng `tests/test_chapter_update.py` theo scenario "Preview does not modify", "Replace preview counts", "Vietnamese file for a Chinese novel" và file `unknown` được chấp nhận.
- [x] 3.3 `ChapterUpdateService.apply` cho `append`: so revision, ghi chương mới với index nối tiếp (`pending`, hoặc `translated` cho truyện `vi`), xóa draft; ghi lỗi thì giữ draft. Kiểm tra bằng test theo scenario "Chapters appended", "Append to a Vietnamese novel", "Chapter translated after preview" (409); kiểm tra tiến độ đọc không đổi và không có request nào tới provider `echo`.
- [x] 3.4 `ChapterUpdateService.apply` cho `replace`: `hold_novel`, bỏ prefetch còn chờ, kiểm tra job, ghi `replace_chapters` và `save_progress` trong một `unit_of_work`. Kiểm tra bằng test theo các scenario:
  - "Chapter inserted in the middle", "Unchanged chapter keeps its translation", "Unchanged edited chapter";
  - "Author revised a chapter", "Revised chapter that was edited";
  - "Missing chapter kept by default", "Missing chapter deleted";
  - "Replace keeps glossary and details", "Job running" (409), "Failure while saving" (repo giả ném lỗi giữa chừng, dữ liệu như cũ, draft còn).

## 4. API và CLI

- [x] 4.1 API theo design D5: field `novel_id` trong `POST /api/imports`, `ImportPreview.novel_id`, `POST /api/imports/{id}/update-preview`, `POST /api/imports/{id}/update`, schema `UpdatePreview`/`UpdateResult`, ánh xạ lỗi 404/410/422/409. Kiểm tra bằng `tests/test_api_chapter_update.py`:
  - các scenario "Upload for an existing novel", "Unknown novel", "Preview expired", "Mode missing", "No anchor and no usable numbers" (422 khi thiếu `start`);
  - các route yêu cầu session và header CSRF.
- [x] 4.2 CLI `novel import <file> --into <id>` (design D7): in neo và số chương thêm; thoát mã 1 khi `needs_start` hoặc không có chương mới. Kiểm tra bằng `tests/test_cli.py` (CliRunner) theo scenario "CLI append" và "CLI cannot place the file".
- [ ] 4.3 Cập nhật `docs/ARCHITECTURE.md`: bảng lớp thêm `domain/chapter_merge.py` và `application/chapter_update.py`; ghi chú khóa so khớp là điểm mở rộng cho nhập từ URL; README hoặc `--help` của CLI nêu `--into`. Kiểm tra bằng `grep` tên module thật trong tài liệu và `.venv/bin/novel import --help` có `--into`.

## 5. Web

- [ ] 5.1 Client API và kiểu `UpdatePreview`/`UpdateResult` trong `web/src/lib/`. Nút "Cập nhật từ txt" trên trang truyện mở `UpdateDialog.svelte`, gồm bước chọn file và bước `ImportPreview` (ẩn tên và ngôn ngữ). Kiểm tra `npm run check` không lỗi.
- [ ] 5.2 `UpdateChanges.svelte` (design D6):
  - radio chế độ không chọn sẵn; xác nhận chỉ bật khi đã chọn;
  - append: neo, chương sẽ thêm, cảnh báo khoảng trống, chọn chương bắt đầu khi `needs_start`, thông báo `differing`;
  - replace: các con số, danh sách chương thiếu có checkbox và "chọn tất cả", cảnh báo `edited_lost`, dòng tiến độ đọc;
  - 409 revision thì tự xem lại; 409 bận thì hiện thông điệp.

  Kiểm tra `npm run check` và `npm run check:contrast` pass.
- [ ] 5.3 Playwright `web/e2e/chapter-update.spec.ts` (mobile 360px và desktop), chạy với provider `echo`:
  - append: file có chương mới thì mục lục tăng đúng số chương, chương cũ còn bản dịch;
  - replace: một chương sửa và một chương thiếu được tick xóa thì chương sửa thành chưa dịch, chương thiếu biến mất, tiến độ đọc trỏ đúng chương;
  - chưa chọn chế độ thì không xác nhận được; huỷ thì không đổi gì;
  - không cuộn ngang, vùng chạm ≥44px.

  Kiểm tra `npm run build && npm run test:e2e` pass.

## 6. Kiểm tra tích hợp

- [ ] 6.1 Chạy toàn bộ `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `cd web && npm run check && npm run check:contrast && npm run build && npm run test:e2e`, `openspec validate update-chapters-from-txt --strict`. Kiểm tra tất cả pass.
- [ ] 6.2 Thử trên app local (`NT_PROVIDER=echo`) với một truyện thật nhiều chương của người dùng:
  - thêm từ file tải lại cả bộ, và từ file chỉ có chương mới;
  - tải lại với file đã sửa vài chương.

  Kiểm tra số chương, bản dịch được giữ, tiến độ đọc và glossary đúng như màn xem trước, và thời gian áp tải lại với truyện lớn nhất dưới 10 giây.

## Workflow follow-up

- Mở pull request từ nhánh `update-chapters-from-txt` vào `main` khi người dùng yêu cầu.
- `/opsx:archive` sau khi review xong (gộp `specs/chapter-update` vào `openspec/specs/`).
