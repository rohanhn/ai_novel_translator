# Spec Delta

## Purpose
Tách nội dung một file truyện dạng văn bản thành các chương (raw tiếng Trung hoặc bản tiếng Việt), nhận diện ngôn ngữ file, và báo các điểm đáng ngờ để người dùng kiểm tra trước khi lưu.

## ADDED Requirements

### Requirement: Chinese chapter headings
The splitter SHALL recognise a line as a Chinese chapter heading when, after trimming, it starts with one of: `第<number>章`, `第<number>回`, `第<number>节`, `第<number>话`, `Chapter <number>`, or one of the special headings `序章`, `序言`, `楔子`, `引子`, `尾声`, `后记`, `番外`, where `<number>` is Arabic digits (half- or full-width) or Chinese numerals (including `零〇一二三四五六七八九十百千万两`). The text after the marker on the same line SHALL be kept as part of the chapter title.

#### Scenario: Mixed numeral styles
- **WHEN** a file contains the lines `第一章 少年`, `第2章 修炼` and `第１０章 突破` on their own
- **THEN** three chapters are produced with titles `第一章 少年`, `第2章 修炼` and `第１０章 突破`, and chapter numbers 1, 2 and 10

#### Scenario: Special heading
- **WHEN** a file starts with a line `楔子` followed by text, then a line `第一章 开始`
- **THEN** `楔子` becomes chapter 1 and `第一章 开始` becomes chapter 2

### Requirement: Vietnamese chapter headings
The splitter SHALL recognise a line as a Vietnamese chapter heading when, after trimming, it starts (case-insensitively) with `Chương` or `Hồi` followed by a number (Arabic digits or Roman numerals), optionally followed by a separator (`:`, `-`, `–`, `—`, `.`) and a title; or when the whole line is one of the special headings `Mở đầu`, `Lời mở đầu`, `Tiết tử`, `Phiên ngoại`, `Ngoại truyện`, `Vĩ thanh` (optionally followed by a separator and a title or number).

#### Scenario: Vietnamese headings with separators
- **WHEN** a file contains the lines `Chương 1: Rồng ngẩng đầu`, `Chương 2 - Mở cửa` and `CHƯƠNG 3. Đi xa` on their own
- **THEN** three chapters are produced with those lines as titles and chapter numbers 1, 2 and 3

#### Scenario: Chapter-end notes in the middle of a file
- **WHEN** the middle of a file reads: body text of chapter 1 ending with `… gọi là “rồng ngẩng đầu”.`, then the note line `(3) Vỡ vỡ bình an: câu nói thường dùng khi lỡ tay làm rơi vỡ đồ vật, nhằm cầu xin đây là một điềm lành.`, then the line `Chương 2: Mở cửa`, then `Trời vừa tảng sáng, gà còn chưa gáy thì Trần Bình An đã rời giường.`
- **THEN** a chapter boundary is placed only at `Chương 2: Mở cửa`; the closing text and the `(3) …` note stay at the end of chapter 1's body, and chapter 2's body starts with `Trời vừa tảng sáng`

### Requirement: Heading lines must stand alone
A line SHALL only be treated as a heading when it is at most 80 characters long, the heading marker is at the very start of the line, and the line does not end with sentence-ending punctuation (`。`, `！`, `？`, `.`, `!`, `?`, `…`) unless the punctuation directly follows the chapter number. Lines in the body that merely mention a chapter SHALL NOT be treated as headings.

#### Scenario: Sentence mentioning a chapter
- **WHEN** a body line reads `Chương này kể về việc Trần Bình An học nghề nung gốm ở trấn nhỏ.`
- **THEN** it is not treated as a heading

#### Scenario: Footnote line
- **WHEN** a line starts with `(3)` or `[3]` or `3.` followed by text
- **THEN** it is not treated as a heading

#### Scenario: Overlong line
- **WHEN** a line starts with `第五章` but is 200 characters long
- **THEN** it is not treated as a heading

### Requirement: Volume headings
Lines starting with `第<number>卷`, `第<number>部`, `Quyển <number>`, `Tập <number>` or `Q<number>` (standalone, same rules as chapter headings) SHALL be treated as volume headings, not chapter boundaries, when the file also contains chapter headings: the volume text SHALL be prefixed to the title of the next chapter as `<volume> · <chapter title>`, and SHALL NOT appear in any chapter body. When the file contains volume headings but no chapter headings, each volume heading SHALL start a chapter.

#### Scenario: Volume above chapters
- **WHEN** a file contains `Quyển 1: Kiếm khí`, then `Chương 1: Rồng ngẩng đầu`, then text
- **THEN** one chapter is produced titled `Quyển 1: Kiếm khí · Chương 1: Rồng ngẩng đầu`, and its body does not contain the volume line

#### Scenario: Volumes only
- **WHEN** a file contains only the headings `第一卷` and `第二卷`, each followed by text
- **THEN** two chapters are produced, titled `第一卷` and `第二卷`

### Requirement: Front matter before the first heading
Non-empty text before the first heading SHALL be reported as front matter. By default it SHALL become a chapter titled `Mở đầu` placed first when it is at least 200 characters long, and SHALL be discarded otherwise (typically title, author or source notes). The caller SHALL be able to override this choice.

#### Scenario: Short book header
- **WHEN** a file starts with `Kiếm Lai\nTác giả: Phong Hỏa Hí Chư Hầu` then `Chương 1: …`
- **THEN** the front matter is reported and, by default, discarded; chapter 1 is `Chương 1: …`

#### Scenario: Long prologue without heading
- **WHEN** 1,500 characters of story text precede the first heading
- **THEN** by default the result starts with a chapter titled `Mở đầu` holding that text

### Requirement: Fallback when no heading is found
When a non-empty file contains no recognised heading, the splitter SHALL produce a single chapter holding the whole text and SHALL report a warning that no chapter headings were found.

#### Scenario: Plain text
- **WHEN** a non-empty file contains no recognised heading
- **THEN** one chapter is produced and a "no headings found" warning is reported

### Requirement: Language detection
The splitter SHALL classify a file as Chinese (`zh`) when Han characters make up at least 30% of the letters in its text, as Vietnamese (`vi`) when it is not Chinese and contains Vietnamese-specific letters (letters with Vietnamese diacritics or `đ`), and otherwise as `unknown`. Heading recognition SHALL use both Chinese and Vietnamese rules regardless of the detected language.

#### Scenario: Chinese raw
- **WHEN** the file body is mostly Chinese characters
- **THEN** the detected language is `zh`

#### Scenario: Vietnamese text
- **WHEN** the file body is Vietnamese with diacritics and contains no Han characters
- **THEN** the detected language is `vi`

### Requirement: Chapter number sequence warnings
The splitter SHALL report a warning on a chapter whose number is not the previous number plus one: a gap, a repeated number, or a decreasing number. Special headings and volumes SHALL be excluded from this check. Warnings SHALL NOT change the split.

#### Scenario: Number gap
- **WHEN** the recognised headings are `Chương 1`, `Chương 2`, `Chương 5`
- **THEN** a gap warning is reported on the chapter `Chương 5` mentioning that chapters 3–4 are missing

#### Scenario: Repeated number
- **WHEN** two headings both read `第十章`
- **THEN** a repeated-number warning is reported on the second one

### Requirement: Chapter length warnings
The splitter SHALL report a warning on a chapter shorter than 100 characters, and on a chapter longer than both 20,000 characters and three times the median chapter length.

#### Scenario: Suspiciously short chapter
- **WHEN** a recognised heading is followed by only 30 characters before the next heading
- **THEN** a too-short warning is reported on that chapter

#### Scenario: Missed headings inside a long chapter
- **WHEN** the median chapter length is 6,000 characters and one chapter has 45,000 characters
- **THEN** a too-long warning is reported on that chapter

### Requirement: Adjustable split
The splitter SHALL accept an adjusted set of chapter boundaries, expressed as line numbers of the source text, and produce chapters starting at exactly those lines (the line becoming the chapter title), together with the front-matter choice. Removing a boundary SHALL merge that chapter's title line and body into the previous chapter's body; adding a boundary at any non-empty line SHALL start a new chapter there.

#### Scenario: Merge by removing a heading
- **WHEN** the detected boundaries are lines 1, 40 and 90 and the caller keeps only lines 1 and 90
- **THEN** two chapters are produced and the first one's body includes the former heading line 40 and its text

#### Scenario: Split at an arbitrary line
- **WHEN** the caller adds line 60 as a boundary
- **THEN** a new chapter starts at line 60, titled with that line's text
