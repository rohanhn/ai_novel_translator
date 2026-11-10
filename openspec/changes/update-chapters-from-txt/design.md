# Design: Cập nhật chương từ TXT

## Context

- Lý do và phạm vi xem `proposal.md`, hành vi xem `specs/chapter-update/spec.md`.
- Import thông minh (change `smart-txt-import`) đã có:
  - `domain/chapter_split.py`: `classify_line` đọc số chương (Hán, La Mã, full-width), `apply(text, boundaries, keep_front_matter)` trả `SplitPlan` với `SplitChapter(title, body, heading_number, ...)`;
  - `application/imports.py` (`ImportDraftService`): draft trong RAM, 60 phút, tối đa 3 draft;
  - API `/api/imports` (tạo, chỉnh ranh giới, xem dòng, commit, huỷ) và component web `ImportPreview.svelte`.
- `LibraryService.import_text` luôn gọi `add_novel`. Chương đánh số từ 1, `UNIQUE (novel_id, idx)`. Không có bảng nào tham chiếu `chapters.id`.
- Repo có `unit_of_work()` gom thao tác vào một transaction. `update_chapter` đặt `updated_at = now()` mỗi lần đổi chương.
- `reading_progress` lưu theo `chapter_index`. Glossary và đề xuất glossary gắn với `novel_id`, không gắn với chương.
- `TranslationJobManager` khóa job theo `(novel_id, index)` và có `cancel_queued_for_novel(novel_id, lane)`. Prefetch chỉ đặt job ở làn `BACKGROUND`.

## Goals / Non-Goals

**Goals:**
- Logic so khớp và tính kết quả là code thuần ở `domain/`, test bằng dữ liệu trong bộ nhớ.
- Khóa so khớp tách khỏi thuật toán, để change "link URL" sau này cắm khóa URL chương vào mà không viết lại.
- Server tính lại mọi thứ từ đầu vào (ranh giới, chế độ, lựa chọn). Client không gửi kết quả đã tính.
- Không đổi schema DB.

**Non-Goals:**
- Lưu draft qua restart (giữ nguyên quyết định D2 của import thông minh).
- So khớp mờ (fuzzy, khoảng cách chỉnh sửa). Chỉ dùng hai mức khớp trong spec.

## Decisions

### D1. Bộ so khớp thuần: `domain/chapter_merge.py`

Đầu vào nhẹ, không phụ thuộc model DB:

```
StoredRef(index, title, source_text, status)      # chương đang lưu
Incoming(position, title, body, heading_number)   # chương trong file (từ SplitChapter)
```

**Khóa:**
- `content_key(text)`: bỏ khoảng trắng đầu và cuối mỗi dòng, bỏ dòng trống, NFKC, rồi lấy sha256. So bằng hash nên không phải giữ hai bản text để so.
- `title_key(title)`: chạy `chapter_split.classify_line` lấy số chương, phần còn lại qua NFKC và bỏ mọi khoảng trắng. Kết quả là `(number, rest)`. Tiêu đề không đọc được số thì key là `(None, rest)`.
- Các hàm nhận một `Keyer` (mặc định là hai khóa trên). Change URL sẽ thêm một khóa định danh đứng trước hai khóa này.

**`plan_append(stored, incoming, start=None) -> AppendPlan`:**
1. `start` do người dùng chọn thì dùng luôn.
2. Không có `start`: với `k` từ chương cuối lùi tối đa 5 chương, tìm **lần xuất hiện cuối** trong file của `stored[k]`. Thứ tự ưu tiên: trùng cả nội dung lẫn tiêu đề, rồi trùng nội dung, rồi trùng tiêu đề. Thấy thì điểm nối là vị trí đó. Mức đầu giúp các chương có thân giống hệt nhau (thông báo, dữ liệu mẫu) không neo nhầm vào lần xuất hiện cuối của một chương khác.
3. Không thấy neo: xét `heading_number` của chương có số đầu tiên trong file, so với số của chương cuối đang lưu (đọc từ `title_key`). Bằng số cuối + 1 thì nối từ đầu file. Lớn hơn thì cũng nối từ đầu file, kèm cảnh báo `gap` có danh sách số bị thiếu. Còn lại thì trả `needs_start`.
4. Trả về: `anchor` (index đang lưu, vị trí trong file, loại khớp, hoặc `None`), `to_add` (danh sách vị trí trong file), `warnings`, và `differing` (các chương trước neo chỉ khớp tiêu đề, để hiện thông báo gợi ý dùng tải lại).

**`plan_replace(stored, incoming, delete: set[int]) -> ReplacePlan`:**
1. **Lượt 1 (khớp nội dung):** trước hết ghép theo cặp (nội dung, tiêu đề), sau đó mới ghép theo riêng nội dung. Map `content_key → [stored index]`. Duyệt file theo thứ tự, lấy chương lưu chưa dùng nhỏ nhất **lớn hơn chương lưu vừa khớp trước đó**. Không có thì lấy chương chưa dùng nhỏ nhất. Cách này giữ đúng thứ tự khi có chương trùng nội dung, ví dụ hai chương "请假条".
2. **Lượt 2 (khớp tiêu đề):** làm như lượt 1 cho các chương còn lại, theo `title_key`. Tiêu đề `第一章` trùng ở hai quyển nhờ vậy vẫn ghép đúng thứ tự.
3. Mỗi chương trong file thành một mục:
   - `reuse(old)` khi khớp nội dung,
   - `changed(old)` khi chỉ khớp tiêu đề,
   - `new` khi không khớp.
4. Chương lưu không được dùng là `missing`. Chương có index trong `delete` thì bị bỏ. Chương còn lại là `kept(old)`, được chèn ngay sau mục mới của chương lưu gần nhất phía trước đã được dùng hoặc được giữ, hoặc ở đầu nếu không có chương nào như vậy. Các chương `kept` liền nhau giữ thứ tự cũ.
5. `progress(old_index, position) -> (new_index, position)`:
   - chương đang đọc là `reuse`: giữ `position`;
   - là `kept`: giữ `position`;
   - là `changed` hoặc bị xóa: lùi về mục gần nhất phía trước có nguồn là chương cũ được giữ, với `position = 0`. Không có thì về chương 1.
6. Thống kê cho màn xem trước: số `reuse`/`changed`/`new`/`missing`, `edited_lost` (chương `changed` mà chương cũ ở trạng thái `edited`), và vị trí đọc mới.

**Phương án bị loại:**
- So bằng thuật toán diff dãy (LCS hoặc kiểu `difflib`): khó giải thích trên UI và tốn O(n·m) với 2000 chương. Ghép tham lam theo hash cho kết quả giống nhau trong các ca thực tế (chèn, xóa, sửa vài chương).
- Lưu `heading_number` hoặc hash vào DB: phải thêm migration, trong khi tính lại từ `title`/`source_text` chỉ mất vài trăm ms cho 2000 chương.

### D2. Draft gắn truyện, service cập nhật: `application/chapter_update.py`

- `Draft` thêm trường `novel_id: int | None`. `ImportDraftService.create(filename, data, novel_id=None)` kiểm tra truyện tồn tại (404 nếu không), còn lại giữ nguyên. `commit` (tạo truyện mới) từ chối draft có `novel_id`, và ngược lại.
- `ChapterUpdateService(repo, drafts, jobs, prefetch)` có hai thao tác:
  - `preview(draft_id, mode, boundaries, keep_front_matter, start, delete) -> UpdatePreview`. Lấy draft, `chapter_split.apply`, kiểm tra ngôn ngữ, đọc `list_chapters`, gọi `plan_append` hoặc `plan_replace`, rồi tính `revision`. Không ghi gì.
  - `apply(draft_id, mode, boundaries, keep_front_matter, start, delete, revision) -> UpdateResult`. Tính lại như `preview`, kiểm tra các điều kiện chặn, ghi, rồi xóa draft. Ghi lỗi thì giữ draft.
- **Revision:** sha256 của `(count, [(idx, id, status, updated_at)])` của toàn bộ chương. Mọi lần dịch, sửa, đổi trạng thái hay cập nhật đều đổi `id` hoặc `updated_at`, nên revision lệch thì trả 409 `StalePreviewError`.
- **Ngôn ngữ:** `draft.detected_lang ∈ {zh, vi}` và khác `novel.source_lang` thì trả 422 với thông điệp nêu cả hai ngôn ngữ.
- **Truyện `vi`:** chương thêm mới và chương `changed` được lưu như `import_text` làm với truyện `vi`: `translated_*` = text gốc, `TRANSLATED`, `provider = IMPORT_PROVIDER`. Đoạn này tách ra một hàm dùng chung với `import_text` để không lặp code.

### D3. Chặn job khi tải lại

- `TranslationJobManager` thêm:
  - `has_jobs_for_novel(novel_id) -> bool`;
  - context manager `hold_novel(novel_id)`. Trong khối này, `submit` cho truyện đó ném `NovelBusyError`, API trả 409 "Truyện đang được cập nhật". Prefetch nhận lỗi thì trả quyết định `no("updating")`.
- Thứ tự trong `apply(replace)`:
  1. vào `hold_novel`;
  2. `cancel_queued_for_novel(novel_id, BACKGROUND)`, tức là bỏ prefetch còn chờ (prefetch là việc nền, tự tạo lại được);
  3. `has_jobs_for_novel` còn true (job tiền cảnh đang chờ hoặc đang chạy) thì 409 `NovelBusyError`;
  4. ghi.
- Cách này đóng khe hở giữa bước kiểm tra và bước ghi.
- `append` không cần các bước trên, vì không đổi index chương nào đang có. Chỉ cần kiểm tra revision.

### D4. Ghi trong một transaction

- Repo thêm:
  - `replace_chapters(novel_id, chapters)`: trong `unit_of_work`, `DELETE FROM chapters WHERE novel_id` rồi chèn lại toàn bộ (kèm `glossary_outdated`, `possible_omission`) bằng `executemany`. Vì không có FK tới `chapters.id`, đổi `id` không ảnh hưởng gì, và revision cũng đổi theo.
  - `add_chapters` mở rộng để chèn thêm hai cờ trên (mặc định false).
- `apply(replace)` gọi trong cùng một `unit_of_work`: `replace_chapters` và `save_progress` (nếu có tiến độ).
- `apply(append)`: `add_chapters` với index = chương cuối + 1 ...

**Phương án bị loại:** UPDATE tại chỗ, dời index qua giá trị âm để tránh vi phạm `UNIQUE`. Cách này giữ được `id` nhưng nhiều câu lệnh và nhiều nhánh hơn, mà không có ai dùng `id`.

### D5. API

| Method | Path | Body | Trả về |
|---|---|---|---|
| `POST` | `/api/imports` (multipart `file`, thêm field `novel_id`) | | 201 `ImportPreview` (thêm `novel_id`) |
| `POST` | `/api/imports/{id}/update-preview` | `{mode, boundaries, keep_front_matter, start?, delete[]}` | 200 `UpdatePreview` |
| `POST` | `/api/imports/{id}/update` | như trên, thêm `revision` | 200 `UpdateResult {novel, added, reused, changed, new, deleted, progress}` |

- Hai endpoint mới dùng `POST` vì body lớn (danh sách ranh giới) và vì có header CSRF sẵn.
- `PUT /api/imports/{id}` (chỉnh ranh giới) và `GET .../lines` dùng lại nguyên.
- `UpdatePreview`:
  - `mode`, `revision`, `warnings[]`;
  - với append: `anchor {index, title, file_position, match}`, `needs_start`, `to_add[{position, title}]`, `differing[{index, title}]`;
  - với replace: `counts {reuse, changed, new, missing}`, `edited_lost`, `missing[{index, title, status}]`, `changed[{index, title, status}]`, `progress {from, to, position_kept}`.
- Danh sách tiêu đề trả về không kèm nội dung. Với 2000 chương, payload vẫn ở mức vài chục KB.
- **Mã lỗi:**
  - 404: truyện không tồn tại;
  - 410: draft hết hạn;
  - 422: thiếu `mode`, thiếu `start` khi `needs_start`, hoặc ngôn ngữ lệch;
  - 409: không có chương mới, revision lệch, hoặc truyện đang bận.

### D6. Web

- Trang truyện (`routes/novels/[id]/+page.svelte`) thêm nút "Cập nhật từ txt", mở `UpdateDialog.svelte` (thư mục `lib/library/`). Hộp thoại có ba bước:
  1. chọn file; dùng lại upload và giới hạn kích thước của `UploadDialog`;
  2. `ImportPreview` sẵn có để chỉnh cách tách; ẩn ô tên và ô ngôn ngữ, vì đã lấy theo truyện;
  3. `UpdateChanges.svelte`: radio chế độ không chọn sẵn, nút xác nhận chỉ bật khi đã chọn. Đổi chế độ thì gọi lại `update-preview`.
     - Append: neo, danh sách chương sẽ thêm, cảnh báo khoảng trống, ô chọn chương bắt đầu khi `needs_start`, thông báo `differing`.
     - Replace: các con số, danh sách chương thiếu có checkbox và "chọn tất cả", cảnh báo nổi bật khi `edited_lost > 0`, dòng "Tiến độ đọc: chương 312 → 313".
- Gặp 409 revision thì tự gọi lại `update-preview` và báo "Truyện vừa thay đổi, hãy xem lại". Gặp 409 đang bận thì hiện thông điệp và giữ nguyên hộp thoại.
- Màu, chữ và khoảng cách theo token của ngôn ngữ giao diện "Thủy mặc · Chu sa" đã có. Kiểm tra bằng `npm run check:contrast`.

### D7. CLI

- `novel import <file> --into <id>` đọc file và chạy `chapter_split.plan` mặc định, rồi gọi thẳng `plan_append` và ghi qua `ChapterUpdateService.apply_append_direct`, không qua draft.
- `needs_start` hoặc không có chương mới thì thoát với mã 1 và gợi ý dùng web.
- CLI không có chế độ tải lại (proposal: CLI không bắt buộc ngang tính năng).

### Các lớp bị thay đổi

| Lớp | Thay đổi |
|---|---|
| `domain/` | Mới `chapter_merge.py` (thuần). `chapter_split` không đổi, chỉ được gọi lại `classify_line`. |
| `application/` | Mới `chapter_update.py`. `imports.py`: `Draft.novel_id`, `create(..., novel_id)`, `commit` từ chối draft cập nhật. `jobs.py`: `has_jobs_for_novel`, `hold_novel`, `NovelBusyError`. `prefetch.py`: xử lý `updating`. `services.py`: tách hàm dựng chương `vi`. |
| `storage/` | `replace_chapters`. `add_chapters` thêm hai cờ. Port `NovelRepository` cập nhật theo. |
| `interfaces/` | API: field `novel_id`, hai endpoint mới, schema. CLI: `--into`. Web: `UpdateDialog`, `UpdateChanges`, nút trên trang truyện. |
| `container.py` | Nối `ChapterUpdateService`. |
| `pipeline/`, `providers/` | Không đổi. |

## Risks / Trade-offs

- **[Rủi ro] Ghép tham lam sai khi file sắp xếp lại nhiều chương.** → Màn xem trước hiện rõ danh sách `changed` và `missing` trước khi ghi. Người dùng có thể huỷ hoặc chọn xóa hết rồi tải lại. Thêm test cho các ca chèn, xóa, đổi chỗ, trùng tiêu đề và trùng nội dung.
- **[Rủi ro] Hai chương thật sự khác nhau nhưng trùng nội dung** (ví dụ chương chỉ có "请假"): mang nhầm bản dịch sang. → Bản dịch của văn bản giống hệt nhau thì vẫn đúng, nên không mất chất lượng.
- **[Rủi ro] Tác giả sửa chính tả vài chữ thì chương chuyển thành `changed` và phải dịch lại**, kể cả khi đã sửa tay. → Đây là quyết định của người dùng (bỏ bản dịch khi nguồn đổi). Màn xem trước báo số bản sửa tay sẽ mất.
- **[Đánh đổi] Tải lại xóa rồi chèn lại toàn bộ chương:** với 2000 chương và khoảng 50 MB text là một transaction lớn, vài giây. → Chấp nhận được với một người dùng. `executemany` theo lô. Nếu chậm thì đo ở task kiểm thử thực tế.
- **[Đánh đổi] `list_chapters` nạp toàn bộ text để so khớp** (bộ nhớ khoảng 2× kích thước truyện trong lúc tính). → Chấp nhận cho một process, một người dùng. Nếu cần có thể thêm truy vấn chỉ lấy hash sau.
- **[Rủi ro] Job tiền cảnh chạy lâu chặn tải lại.** → Thông điệp 409 rõ ràng. Không tự huỷ job tiền cảnh, vì nó đang tốn quota và sắp xong.

## Migration Plan

- Không có migration DB. Triển khai như bình thường (image mới qua CI, `IMAGE_TAG`). Rollback bằng image cũ không ảnh hưởng dữ liệu, vì không có cột mới.
- Draft cập nhật nằm trong RAM. Restart lúc đang xem trước thì người dùng nhận 410 và upload lại (giống import).
