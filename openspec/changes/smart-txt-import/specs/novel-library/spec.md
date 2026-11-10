# Spec Delta

## MODIFIED Requirements

### Requirement: Import novel from TXT
The system SHALL import a novel from a plain-text file, auto-detecting UTF-8 or GB18030 encoding, splitting it into chapters and detecting its language according to the `chapter-splitting` capability. Chapters SHALL be numbered from 1 in file order. The detected language MAY be overridden by the caller (`zh` or `vi`); a file detected as `unknown` without override SHALL be imported as `zh`. The command-line import SHALL save immediately using the default split and SHALL print the split warnings.

#### Scenario: File with chapter headings
- **WHEN** the user imports a Chinese TXT file containing two `第X章` headings
- **THEN** a novel is created with 2 chapters, numbered from 1 in file order, each with status `pending`

#### Scenario: Vietnamese file with chapter headings
- **WHEN** the user imports a Vietnamese TXT file containing the headings `Chương 1: Rồng ngẩng đầu` and `Chương 2: Mở cửa`
- **THEN** a pre-translated novel is created with 2 chapters, each with status `translated`

#### Scenario: File without chapter headings
- **WHEN** the user imports a non-empty TXT file with no recognizable headings
- **THEN** a novel is created with a single chapter containing the whole text, and a "no headings found" warning is shown

#### Scenario: Language override
- **WHEN** the user imports a Vietnamese file with the language overridden to `zh`
- **THEN** the novel is created as a Chinese novel with all chapters `pending`

#### Scenario: Empty file
- **WHEN** the user imports an empty file
- **THEN** the import is rejected with an error and no novel is created

### Requirement: Upload novel from the web
The owner SHALL be able to upload a `.txt` file from the web library; files larger than 50 MB or empty SHALL be rejected. Uploading SHALL NOT save the novel immediately: the system SHALL first return a preview containing the detected language, the proposed chapters (number, title, length, first characters), the front matter if any, and the split warnings. The owner SHALL be able to remove or add chapter boundaries, choose to keep or discard the front matter, change the language, and set the title (defaulting to the file name) before confirming. Only on confirmation SHALL the novel be created from the adjusted split. A preview SHALL expire after at most 60 minutes or when the server restarts; confirming or adjusting an expired preview SHALL fail with a message asking to upload again. Cancelling a preview SHALL discard it without creating anything.

#### Scenario: Upload, review, confirm
- **WHEN** the owner uploads `kiemlai.txt` containing 3 `Chương N` headings and confirms the preview without changes
- **THEN** a novel titled `kiemlai` with 3 chapters appears in the library

#### Scenario: Nothing saved before confirmation
- **WHEN** the owner uploads a file and closes the preview without confirming
- **THEN** no novel is created

#### Scenario: Merge a false heading before saving
- **WHEN** the preview shows 4 chapters, the owner removes the boundary at chapter 3 and confirms
- **THEN** the novel is created with 3 chapters and chapter 2's text includes the former chapter 3's heading line and text

#### Scenario: Expired preview
- **WHEN** the owner confirms a preview after the server has restarted
- **THEN** the confirmation fails with a message asking to upload the file again, and no novel is created

#### Scenario: Oversized file
- **WHEN** the owner uploads a 60 MB file
- **THEN** the upload is rejected with a size error and no preview or novel is created

## ADDED Requirements

### Requirement: Pre-translated novels
A novel imported with language `vi` SHALL be stored as a pre-translated novel: each chapter's translated title and text SHALL equal the imported ones, its status SHALL be `translated`, and its provenance SHALL be recorded as imported rather than produced by a model. Editing, reading progress, export and deletion SHALL work as for any other novel.

#### Scenario: Read immediately
- **WHEN** a Vietnamese file with 3 chapters is imported
- **THEN** all 3 chapters are readable immediately and no LLM request is made

#### Scenario: Manual edit
- **WHEN** the owner edits a chapter of a pre-translated novel and saves
- **THEN** the chapter status becomes `edited` with the new text

#### Scenario: Export
- **WHEN** the owner exports a pre-translated novel to TXT
- **THEN** the output contains all its chapters in order

### Requirement: Pre-translated novels never reach an LLM
Chapters of a pre-translated novel SHALL never be sent to an LLM: translation and re-translation requests for them SHALL be rejected with a conflict error, and they SHALL never be selected for prefetch.

#### Scenario: Translate request rejected
- **WHEN** a translate request is made for a chapter of a pre-translated novel
- **THEN** the request is rejected with a conflict error and no translation job is created
