# translation-editing Specification

## Purpose
Cho phép chủ sở hữu sửa tay bản dịch của từng chương và đảm bảo các thay đổi tự động của hệ thống không bao giờ ghi đè lên phần đã biên tập.

## Requirements

### Requirement: Edit a chapter translation
The owner SHALL be able to edit the translated title and text of a translated chapter and save it; the saved text replaces the stored translation and the chapter status becomes edited.

#### Scenario: Save edit
- **WHEN** the owner changes a paragraph of chapter 3 and saves
- **THEN** chapter 3 displays the edited text and has status edited

#### Scenario: Edit untranslated chapter
- **WHEN** the owner attempts to edit a chapter with no translation
- **THEN** the system rejects the edit with an error

### Requirement: Edited chapters are protected from automatic changes
The system MUST NOT modify an edited chapter's text through any automatic process, including glossary rename propagation and prefetch.

#### Scenario: Rename does not touch edited chapter
- **WHEN** a glossary rename affects chapter 3, which is edited
- **THEN** chapter 3's text is unchanged and it is labelled glossary-outdated

### Requirement: Explicit re-translation of edited chapter
Re-translating an edited chapter SHALL require explicit confirmation from the owner, because it discards the manual edits.

#### Scenario: Confirmed re-translate
- **WHEN** the owner requests re-translation of edited chapter 3 and confirms
- **THEN** chapter 3 is translated again and its status becomes translated

#### Scenario: Unconfirmed request
- **WHEN** a re-translation of an edited chapter is requested without confirmation
- **THEN** the system rejects the request and the edit is preserved
