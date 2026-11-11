# Design

## Context

- Cờ chất lượng hiện có là `possible_omission`. Cờ này được tính trong `pipeline/translator.py` (`is_possible_omission`), lưu thành cột trên `chapters`, rồi đi qua `ChapterSummary` (API), sự kiện `completed` của job, `chipsFor` (web) và `novel chapters` (CLI). Change này đi theo đúng đường đó.
- `domain/chapter_split.py` đã có `_is_han` (CJK Unified, Ext A, Ext B, Compatibility) dùng cho nhận diện ngôn ngữ.
- Bản dịch được đổi ở ba chỗ:
  - `TranslationService.translate_chapter` khi dịch hoặc dịch lại;
  - `EditingService.edit_chapter` khi sửa tay;
  - `ChapterUpdateService` khi tải lại cả bộ: chương `reuse` chép nguyên mọi trường, chương `changed` hoặc `new` không có bản dịch.

  Truyện `vi` được import thì bản dịch chính là text gốc (`provider = import`).
- Màn đọc (`routes/novels/[id]/chapters/[n]/+page.svelte`) tách `translated_text` theo dòng rồi render mỗi đoạn trong một `<p>`.

## Goals / Non-Goals

**Goals:**
- Đếm chữ Hán còn sót bằng một hàm thuần duy nhất, dùng chung cho dịch, sửa tay và migration.
- Màn đọc tô sáng đúng những chữ được đếm.
- Không thêm request LLM nào.

**Non-Goals:**
- Tính lại số đếm của mọi chương khi glossary đổi (xem Risks).
- Tô sáng trong lúc đang stream. Chỉ tô sau khi chương dịch xong và được tải lại.

## Decisions

### D1. Hàm đếm thuần: `domain/han_residue.py`

- `is_han(c)`: chuyển từ `chapter_split._is_han` sang module này; `chapter_split` import lại để không có hai định nghĩa.
- `kept_chars(glossary_targets) -> frozenset[str]`: các chữ Hán xuất hiện trong bản dịch của glossary.
- `residue(title, text, kept) -> Residue(count, chars)`: `count` là số chữ Hán không thuộc `kept`, trong tiêu đề và nội dung dịch; `chars` là tập chữ riêng biệt, theo thứ tự xuất hiện.
- Dấu câu CJK (`《》，。`…) không phải chữ Hán nên tự nhiên không bị đếm.
- **Loại chữ của glossary theo chữ, không theo vị trí:** chữ `丹` có trong bản dịch glossary thì không bị đếm ở bất kỳ đâu trong chương. Cách này đơn giản và cho client cùng một tập chữ để tô. Bỏ sót một chữ `丹` đứng lẻ là chấp nhận được, vì người dùng đã chủ động giữ chữ đó.
- **Phương án bị loại:** đặt bước kiểm tra trong `pipeline/translator.py` cạnh `is_possible_omission`. Sửa tay và migration không đi qua pipeline, nên hàm phải nằm ở `domain/` để mọi chỗ dùng chung.

### D2. Lưu số đếm: cột `chapters.untranslated_han`

- Migration `003_untranslated_han.sql`: `ALTER TABLE chapters ADD COLUMN untranslated_han INT NOT NULL DEFAULT 0`.
- Model `Chapter.untranslated_han: int = 0`. Repo đọc và ghi cột này trong `update_chapter`, `_insert_chapters` (nên `add_chapters` và `replace_chapters` giữ được giá trị khi chương `reuse` được chép), và `_chapter`.
- Chỉ lưu số đếm, không lưu tập chữ: danh sách chương chỉ cần số để gắn nhãn. Tập chữ để tô sáng được tính khi mở một chương (D4), nên không cần thêm cột hay bảng.
- **Phương án bị loại:** tính khi đọc mà không lưu. `GET /chapters` (mục lục 2000 chương) hiện không cần đọc text để gắn nhãn; tính khi đọc sẽ phải nạp toàn bộ bản dịch.

### D3. Ghi số đếm ở tầng application

- `translate_chapter`: sau khi có `out`, đặt `chapter.untranslated_han = residue(out.title, out.text, kept_chars(glossary)).count`, với `glossary` là bộ đã dùng để dịch.
- `edit_chapter`: tính lại với glossary hiện tại.
- Chương mất bản dịch (`changed`/`new` khi tải lại, chương `pending`) có số đếm 0. Chương `vi` được import hoặc cập nhật cũng đi qua cùng hàm dựng chương `vi` và được tính như thường.
- `TranslationJobManager` thêm `untranslated_han` vào payload của sự kiện `completed`. CLI `novel chapters` in thêm cờ "còn N chữ chưa dịch" cạnh cờ thiếu đoạn.

### D4. API

- `ChapterSummary` thêm `untranslated_han: int`.
- `ChapterOut` (chi tiết một chương) thêm `untranslated_chars: list[str]`, tính khi đọc bằng `residue(...).chars` với glossary hiện tại. Client chỉ tô các chữ có trong danh sách này, nên tô đúng chữ được đếm, kể cả sau khi glossary đổi.

### D5. Web

- `status.ts`: thêm `ChipKind` `untranslated_han` với nhãn "Còn chữ chưa dịch", hiện khi `untranslated_han > 0`. Bộ lọc "có vấn đề" trên trang truyện cũng tính cờ này.
- Màn đọc thêm thông báo "Còn N chữ chưa dịch." cạnh thông báo thiếu đoạn, kèm nút "Dịch lại". Nút này dùng `translate({ force: true })` sẵn có, nên chương đã sửa tay vẫn phải xác nhận như mọi lần dịch lại.
- Tô sáng bằng hàm thuần `lib/reader/highlight.ts`: `splitHan(text, chars) -> {text, mark}[]`, render mỗi đoạn thành chuỗi các `<span>` và `<mark class="han-residue">`. Không dùng `{@html}`, nên không có rủi ro chèn mã. Gom các chữ liền nhau vào một `<mark>` (`蕩着` là một mark).
- Màu tô lấy từ token của "Thủy mặc · Chu sa" (nền chu sa nhạt, gạch chân), thêm cặp màu vào `check:contrast` cho cả sáng và tối.

### D6. Prompt

- `BASE_SYSTEM` thêm một dòng: "Không để lại chữ Hán trong bản dịch: mọi từ phải dịch nghĩa hoặc phiên âm Hán-Việt."
- Prompt hệ thống vẫn giống nhau giữa các đoạn của cùng chương, nên cache của provider không bị ảnh hưởng (spec "Glossary-aware prompting").

### D7. Tính sẵn cho bản dịch cũ (migration)

- Cùng migration 003, một câu `UPDATE` dùng `regexp_count` (PostgreSQL ≥ 15; môi trường hiện tại là 16) để đếm chữ Hán trong `coalesce(translated_title,'') || coalesce(translated_text,'')`:
  - lớp ký tự `[一-鿿㐀-䶿豈-﫿\U00020000-\U0002a6df]`;
  - trước khi đếm, `regexp_replace` bỏ các chữ Hán có trong bản dịch glossary của cùng truyện. Tập chữ này được gom bằng CTE từ bảng `glossary`.
- Chỉ áp cho chương có `translated_text IS NOT NULL`.
- Test migration đối chiếu kết quả SQL với hàm Python `residue` trên cùng dữ liệu (có chữ Hán, có chữ do glossary giữ, có dấu câu CJK).
- **Phương án bị loại:** tính lại ở tầng Python lúc khởi động app. Cách này cần thêm cơ chế "đã chạy chưa" ngoài bộ migrator SQL hiện có.

### Các lớp bị thay đổi

| Lớp | Thay đổi |
|---|---|
| `domain/` | Mới `han_residue.py`; `chapter_split` dùng `is_han` từ đó; `Chapter.untranslated_han`. |
| `application/` | `services.py` (`translate_chapter`, `edit_chapter`), `jobs.py` (payload `completed`). `chapter_update.py` không đổi logic, vì giá trị đi theo chương được chép. |
| `pipeline/` | `prompts.py`: thêm một dòng yêu cầu. |
| `storage/` | Migration 003 (cột + tính sẵn); repo đọc và ghi cột. |
| `interfaces/` | API: `untranslated_han`, `untranslated_chars`. CLI: cờ trong `novel chapters`. Web: nhãn, thông báo, tô sáng. |
| `providers/` | Không đổi. |

## Risks / Trade-offs

- **[Rủi ro] Glossary đổi sau khi dịch** (thêm hoặc xóa mục có chữ Hán trong bản dịch) làm số đếm đã lưu lệch với tập chữ tô sáng. → Hiếm, vì bản dịch glossary là tiếng Việt. Số đếm được tính lại ở lần dịch hoặc sửa kế tiếp. Tập chữ tô sáng luôn tính theo glossary hiện tại.
- **[Rủi ro] Truyện `vi` import có chữ Hán thật trong text** (ví dụ chú thích nguyên văn) sẽ bị gắn nhãn. → Đúng là còn chữ Hán; người dùng sửa tay hoặc bỏ qua. Nhãn chỉ là thông tin, không chặn gì.
- **[Đánh đổi] Không tự dịch lại.** Chương lỗi vẫn hiện tới khi người dùng bấm "Dịch lại". Đổi lại không tốn thêm quota, và streaming đang hiển thị không phải làm lại.
- **[Rủi ro] Migration chậm với thư viện lớn.** `regexp_count` trên vài chục MB text chỉ chạy một lần, mất vài giây. Migration chạy lúc khởi động như hai migration trước.

## Migration Plan

- Migration 003 chạy tự động khi app khởi động (`migrate`): thêm cột với mặc định 0, rồi tính sẵn cho các chương đã có bản dịch.
- Rollback bằng image cũ: code cũ không đọc cột mới. `SELECT *` vẫn chạy, `_chapter` chỉ lấy các cột nó biết, nên cột thừa không gây lỗi. Không cần gỡ cột.
