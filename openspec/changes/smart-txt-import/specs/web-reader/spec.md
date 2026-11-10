# Spec Delta

## ADDED Requirements

### Requirement: Pre-translated chapter display
For chapters of a pre-translated (imported Vietnamese) novel, the reader SHALL display the stored text immediately, SHALL show a provenance label "Bản dịch có sẵn", and SHALL NOT offer the source-text toggle, the re-translate action, or any translation-in-progress state. Opening such a chapter SHALL NOT send a translation request, and reading signals on it SHALL NOT start a prefetch. The edit action SHALL remain available.

#### Scenario: Open an imported chapter
- **WHEN** the owner opens chapter 2 of a novel imported from a Vietnamese file
- **THEN** the text is shown at once with the label "Bản dịch có sẵn", and no "Xem bản gốc" or "Dịch lại" control is shown

#### Scenario: No prefetch
- **WHEN** the owner reads chapter 1 of a pre-translated novel for more than 30 seconds
- **THEN** no translation job is started for chapter 2

### Requirement: Import preview screen
The web library SHALL present the upload preview as a review step before saving, showing the detected language (changeable), the title, the chapter count, each chapter's number, title, length and opening characters, the front matter with a keep/discard choice, and each warning in plain wording next to its chapter. The preview SHALL be usable on a 360px-wide viewport.

#### Scenario: Warning shown in context
- **WHEN** the preview contains a number gap between `Chương 2` and `Chương 5`
- **THEN** the chapter `Chương 5` shows a plain-language warning that chapters 3–4 are missing

#### Scenario: Change language
- **WHEN** a file is detected as Vietnamese and the owner switches the language to Chinese before confirming
- **THEN** the novel is created as a Chinese novel with chapters awaiting translation

### Requirement: Adjust chapters in the preview
In the preview, the owner SHALL be able to merge a chapter into the previous one and split a chapter at any of its lines; the chapter list and warnings SHALL update before confirmation.

#### Scenario: Split at a missed heading
- **WHEN** the owner opens a too-long chapter, picks the line `【第三章】` and chooses to split there
- **THEN** the list shows a new chapter starting at that line, and the too-long warning disappears if both parts are within limits
