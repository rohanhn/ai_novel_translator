# Spec Delta

## Purpose

Cập nhật danh sách chương của một truyện đã có từ file TXT, gồm thêm chương mới hoặc tải lại cả bộ. Bản dịch, bản sửa tay, glossary, thông tin truyện và tiến độ đọc được giữ lại khi nội dung gốc của chương không đổi.

## ADDED Requirements

### Requirement: Start a chapter update from TXT
The system SHALL let the owner upload a TXT file against an existing novel to create an update preview. The file SHALL be decoded and split with the same rules, front-matter handling, warnings and boundary editing as a new TXT import. Nothing SHALL be saved until the owner applies the update.

#### Scenario: Upload for an existing novel
- **WHEN** the owner uploads a TXT file to update novel 7
- **THEN** the system returns a split preview bound to novel 7 and novel 7's chapters are unchanged

#### Scenario: Unknown novel
- **WHEN** the owner uploads a TXT file to update a novel id that does not exist
- **THEN** the system returns a not-found error (HTTP 404) and no preview is created

#### Scenario: Preview expired
- **WHEN** the owner applies an update whose preview has expired or was discarded
- **THEN** the system returns HTTP 410 and the novel is unchanged

### Requirement: Explicit update mode
The system SHALL require the owner to choose the update mode, `append` (add new chapters) or `replace` (reload the whole novel), for every change preview and apply request. There SHALL be no default mode.

#### Scenario: Mode missing
- **WHEN** the owner requests a change preview or applies an update without a mode
- **THEN** the request is rejected with a validation error (HTTP 422) and the novel is unchanged

#### Scenario: Switching mode
- **WHEN** the owner switches the mode on the change preview
- **THEN** the system recomputes the change preview for the new mode without requiring a new upload

### Requirement: Chapter matching
The system SHALL treat a file chapter and a stored chapter as a content match when their source text is equal after ignoring leading and trailing whitespace on each line and blank lines. They SHALL be a title match when their titles have the same chapter number and the same remaining title text, ignoring whitespace and full-width/half-width differences.

#### Scenario: Whitespace-only difference
- **WHEN** a file chapter differs from a stored chapter only by indentation and blank lines
- **THEN** the two chapters are a content match

#### Scenario: Numeral style difference in title
- **WHEN** a stored chapter is titled `第五百章 风起` and a file chapter is titled `第500章  风起` with different body text
- **THEN** the two chapters are a title match but not a content match

### Requirement: Append anchors on the last stored chapter
In `append` mode the system SHALL search the file for the novel's last stored chapter, by content or title match, using its last occurrence. If it is not found, the system SHALL try each of the previous stored chapters, up to 5 chapters back from the last one. The anchor is the first one found. The chapters after the anchor in the file are the chapters to add.

#### Scenario: Full novel re-downloaded
- **WHEN** a novel has chapters 1 to 500 and the file contains chapters 1 to 520 with chapter 500 unchanged
- **THEN** the change preview shows the anchor at chapter 500 and 20 chapters to add (file chapters 501 to 520)

#### Scenario: File starts mid-novel
- **WHEN** a novel has chapters 1 to 500 and the file contains chapters 480 to 520
- **THEN** the change preview shows the anchor at chapter 500 and 20 chapters to add

#### Scenario: Last stored chapter was a notice dropped from the file
- **WHEN** the last stored chapter is a leave notice that is absent from the file, and the stored chapter before it is present
- **THEN** the anchor is that earlier chapter and the chapters after it in the file are to be added

### Requirement: Append without an anchor
When no anchor is found in `append` mode, the system SHALL compare chapter numbers. If the first numbered file chapter follows the last stored number, all file chapters are to be added. If it is higher, a gap warning lists the missing numbers. Otherwise the owner SHALL pick the first file chapter to add.

#### Scenario: File contains only new chapters
- **WHEN** the last stored chapter is numbered 500 and the file contains only chapters 501 to 520
- **THEN** the change preview shows all 20 file chapters to add with no warning

#### Scenario: Gap in numbering
- **WHEN** the last stored chapter is numbered 500 and the file starts at chapter 505
- **THEN** the change preview shows a gap warning listing chapters 501 to 504 and the owner can still apply the update

#### Scenario: No anchor and no usable numbers
- **WHEN** no anchor is found and the chapter numbers cannot be read from the titles
- **THEN** the change preview asks the owner to choose the first file chapter to add, and applying without that choice is rejected (HTTP 422)

#### Scenario: Owner overrides the start chapter
- **WHEN** the owner picks a different first chapter to add on the change preview
- **THEN** the chapters from that file chapter to the end of the file are the chapters to add

### Requirement: Append result
Applying `append` SHALL add the selected file chapters after the last stored chapter, numbered consecutively in file order, and SHALL NOT modify, renumber or delete any stored chapter. If there are no chapters to add, the update SHALL be rejected. File chapters that are not among the chapters to add and match no stored chapter SHALL be listed on the change preview as missing from the novel, with a notice that `replace` mode inserts them in place; `append` SHALL NOT add them.

#### Scenario: Chapters appended
- **WHEN** the owner applies an append that adds 20 chapters to a novel with 500 chapters
- **THEN** the novel has 520 chapters, chapters 501 to 520 are `pending` with the file's titles and text, and chapters 1 to 500 are unchanged

#### Scenario: Nothing new
- **WHEN** the anchor is the last chapter in the file
- **THEN** the change preview reports that there are no new chapters and applying is rejected (HTTP 409)

#### Scenario: Stored chapters differ from the file
- **WHEN** some file chapters before the anchor title-match stored chapters but are not content matches
- **THEN** the change preview shows a notice that these stored chapters differ from the file and that `replace` mode updates them, and applying `append` leaves them unchanged

#### Scenario: File has chapters missing from the middle of the novel
- **WHEN** a novel has chapters numbered 1, 2, 3, 6 and 7 and the file contains chapters 1 to 8
- **THEN** the change preview shows chapter 8 to add and a notice listing file chapters 4 and 5 as missing from the novel with a hint to use `replace`, and applying `append` adds only chapter 8

### Requirement: Replace follows the file order
Applying `replace` SHALL make the novel's chapter list follow the file order, numbered from 1. Each file chapter is matched to at most one stored chapter: a content match takes precedence, then a title match, and each stored chapter is matched at most once.

#### Scenario: Chapter inserted in the middle
- **WHEN** the file has a side story between stored chapters 3 and 4 and the owner applies `replace`
- **THEN** the side story becomes chapter 4 and the former chapters 4 onward are each numbered one higher

### Requirement: Replace fills missing chapters by number
In `replace` mode, a place is the span between two consecutive file chapters that match stored chapters, or before the first or after the last of them. When a place holds both new file chapters and kept stored chapters, the system SHALL order them by chapter number: each kept chapter goes after every new chapter in that place with a lower number, and kept chapters keep their stored order.

#### Scenario: File contains only the missing chapters
- **WHEN** a novel has chapters numbered 1, 2, 3, 6 and 7 and the owner applies `replace` with a file containing only chapters 4 and 5, deleting nothing
- **THEN** the novel has chapters 1 to 7 in numeric order, chapters 1, 2, 3, 6 and 7 keep their translations, and chapters 4 and 5 are `pending`

#### Scenario: Partial file around the gap
- **WHEN** a novel has chapters numbered 1, 2, 3, 6 and 7 and the owner applies `replace` with a file containing chapters 3 to 6, deleting nothing
- **THEN** chapters 4 and 5 are inserted between chapters 3 and 6, and chapters 1, 2 and 7 are kept with their translations

### Requirement: Kept chapters without increasing numbers stay in place
In `replace` mode, if a kept chapter in a place has no readable chapter number, or the kept chapters' numbers in that place are not increasing, the kept chapters of that place SHALL stay right after the preceding matched chapter, before the new chapters of that place.

#### Scenario: Kept chapters without numbers
- **WHEN** the kept chapters in a place have titles without a readable chapter number
- **THEN** they stay right after the preceding matched chapter, before the new chapters of that place

#### Scenario: Numbering restarts per volume
- **WHEN** the kept chapters in a place are numbered 99 then 1, because numbering restarts in the next volume, and the place also holds a new chapter numbered 50
- **THEN** the kept chapters' numbers are not increasing, so both kept chapters stay right after the preceding matched chapter, before the new chapter

### Requirement: Replace reuses unchanged translations
In `replace` mode, a file chapter that content-matches a stored chapter SHALL keep that chapter's translated title and text, status, provider, model, glossary version and flags, including chapters in status `edited`. No translation request is made for it.

#### Scenario: Unchanged chapter keeps its translation
- **WHEN** stored chapter 12 is `translated` and the file contains the same chapter 12 text
- **THEN** after `replace` the matching chapter is still `translated` with the same translation and no LLM request is made

#### Scenario: Unchanged edited chapter
- **WHEN** stored chapter 20 is `edited` and its source text is unchanged in the file
- **THEN** after `replace` the matching chapter is still `edited` with the owner's edited text

### Requirement: Replace discards translations of changed chapters
In `replace` mode, a file chapter that only title-matches a stored chapter SHALL take the file's title and text, SHALL lose the stored translation even if it was `edited`, and SHALL become `pending`. A file chapter without any match SHALL be added as `pending`.

#### Scenario: Author revised a chapter
- **WHEN** stored chapter 30 is `translated` and the file has the same title with revised text
- **THEN** after `replace` the matching chapter has the revised source text, no translation, and status `pending`

#### Scenario: Revised chapter that was edited
- **WHEN** stored chapter 31 is `edited` and the file has the same title with revised text
- **THEN** the change preview counts it as an edited translation that will be lost, and after `replace` it is `pending` without the edited text

### Requirement: Owner chooses which missing chapters to delete
In `replace` mode, the change preview SHALL list stored chapters that match no file chapter. None SHALL be selected by default, and a select-all action SHALL be provided. Selected chapters are deleted. Each unselected chapter is kept, with its data, right after the chapter that its preceding stored chapter matched, or at the start if none did.

#### Scenario: Missing chapter kept by default
- **WHEN** stored chapter X sits between stored chapters 3 and 4, is absent from the file, and the owner applies `replace` without selecting it
- **THEN** X is kept, with its translation, right after the new chapter that matched stored chapter 3

#### Scenario: Missing chapter deleted
- **WHEN** the owner selects stored chapter X for deletion and applies `replace`
- **THEN** X and its translation no longer exist and the remaining chapters are numbered consecutively

#### Scenario: Select all
- **WHEN** the owner uses select-all on the list of missing chapters
- **THEN** every listed chapter is selected for deletion

### Requirement: Change preview
Before applying, the system SHALL show a change preview without modifying the novel. For `append` it shows the anchor and the chapters to add. For `replace` it shows the counts of reused, changed, new and missing chapters, each new chapter with the chapter number it will have, the number of edited translations that will be lost, and where reading progress will move.

#### Scenario: Replace preview counts
- **WHEN** the owner previews `replace` with 497 unchanged, 3 revised (1 edited), 21 new and 1 missing chapter
- **THEN** the preview shows 497 reused, 3 changed, 21 new, 1 missing, and 1 edited translation that will be lost

#### Scenario: Replace preview shows where new chapters go
- **WHEN** the owner previews `replace` for a novel with chapters numbered 1, 2, 3, 6 and 7 using a file containing only chapters 4 and 5
- **THEN** the preview lists the two new chapters as chapters 4 and 5 of the updated novel

#### Scenario: Preview does not modify
- **WHEN** the owner requests change previews in both modes and then discards the update
- **THEN** the novel's chapters, translations and reading progress are unchanged

### Requirement: Novel data preserved
An update SHALL NOT change the novel's title, author, description, cover, glossary entries, glossary suggestions or glossary version.

#### Scenario: Replace keeps glossary and details
- **WHEN** a novel with a title, cover and 40 glossary entries is updated with `replace`
- **THEN** the title, cover and the 40 glossary entries are unchanged

### Requirement: Reading progress follows chapters
After `replace`, saved reading progress SHALL point to the new chapter matched by the chapter being read. If that chapter was changed or not kept, progress SHALL move to the nearest preceding kept chapter, or chapter 1, with the in-chapter position reset to the start. A content match keeps the in-chapter position. `append` SHALL NOT change reading progress.

#### Scenario: Reading chapter shifted
- **WHEN** the owner was reading stored chapter 312 at 40% and a chapter is inserted before it by `replace`
- **THEN** reading progress points to chapter 313 at 40%

#### Scenario: Reading chapter deleted
- **WHEN** the chapter being read is selected for deletion
- **THEN** reading progress points to the nearest preceding kept chapter at its start

### Requirement: Language must match the novel
The system SHALL reject a change preview or an update when the file's detected language is `zh` or `vi` and differs from the novel's source language. A file whose language is `unknown` SHALL be accepted.

#### Scenario: Vietnamese file for a Chinese novel
- **WHEN** the owner uploads a file detected as `vi` to update a novel whose source language is `zh`
- **THEN** the change preview and apply requests are rejected with a message naming both languages and the novel is unchanged

### Requirement: Pre-translated novels
For a novel imported as `vi`, added and changed chapters SHALL be stored as translated with the file's text, as in a `vi` import, and SHALL NOT be queued for translation.

#### Scenario: Append to a Vietnamese novel
- **WHEN** the owner appends 5 chapters to a novel whose source language is `vi`
- **THEN** the 5 new chapters are `translated` with the file's text and no LLM request is made

### Requirement: Stale preview rejected
The system SHALL reject applying an update if the novel's chapters changed after the change preview was computed, for example through translation, editing or another update. The owner then reviews a new change preview.

#### Scenario: Chapter translated after preview
- **WHEN** a chapter of the novel finishes translating between the change preview and the apply request
- **THEN** the apply request is rejected (HTTP 409) with a message to review the changes again, and the novel is unchanged

### Requirement: Replace blocked by active translation jobs
The system SHALL reject applying `replace` while a translation job for the novel is queued or running. `append` SHALL be allowed while jobs run.

#### Scenario: Job running
- **WHEN** chapter 501 of the novel is being translated and the owner applies `replace`
- **THEN** the request is rejected (HTTP 409) with a message to wait for translation to finish, and the novel is unchanged

### Requirement: Atomic update
Applying an update SHALL change the chapters and reading progress in a single transaction: either all changes are saved or none.

#### Scenario: Failure while saving
- **WHEN** saving fails partway through a `replace`
- **THEN** the novel's chapters and reading progress are exactly as before the request, and the preview can be applied again

### Requirement: CLI append
The CLI SHALL offer `novel import <file> --into <novel_id>`. It applies `append` with the default split and the automatic anchor, prints the anchor and the number of chapters added, and fails with exit code 1 when no anchor or number continuation is found or nothing is new.

#### Scenario: CLI append
- **WHEN** the owner runs `novel import new.txt --into 7` and the file continues novel 7 by 20 chapters
- **THEN** 20 chapters are appended and the command prints the anchor chapter and "20"

#### Scenario: CLI cannot place the file
- **WHEN** no anchor or number continuation is found
- **THEN** the command exits with code 1, says to use the web update, and the novel is unchanged
