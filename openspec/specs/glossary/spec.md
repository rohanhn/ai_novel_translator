# glossary Specification

## Purpose
Bảng thuật ngữ theo từng truyện (tên nhân vật, địa danh, cảnh giới, chiêu thức) để bản dịch nhất quán giữa các chương.

## Requirements

### Requirement: Manage glossary terms per novel
The system SHALL let the user add or update (upsert), list, and remove glossary terms scoped to a single novel. A source term MUST be unique within a novel.

#### Scenario: Upsert existing term
- **WHEN** the user sets `林动 → Lâm Động` and later sets `林动 → Lâm Đông`
- **THEN** the glossary contains a single entry for `林动` with target `Lâm Đông`

#### Scenario: Remove missing term
- **WHEN** the user removes a term that does not exist
- **THEN** the system returns a not-found error

### Requirement: Glossary versioning
Each novel's glossary SHALL have a version number that increases whenever an entry is added, changed, or removed, so each stored translation can be compared with the current glossary.

#### Scenario: Version bump
- **WHEN** the glossary of novel 1 is at version 3 and the owner adds a term
- **THEN** the glossary version becomes 4

### Requirement: Suggestion review queue
The system SHALL keep, per novel, a queue of name suggestions produced during translation. The owner SHALL be able to accept (adds the term), accept with an edited rendering, or dismiss each suggestion.

#### Scenario: Accept suggestion
- **WHEN** the owner accepts the suggestion `苏柔 → Tô Nhu`
- **THEN** `苏柔 → Tô Nhu` is added to the glossary and the suggestion leaves the queue

#### Scenario: Accept with edit
- **WHEN** the owner edits the suggestion to `Tô Nhược` and accepts
- **THEN** `苏柔 → Tô Nhược` is added to the glossary

#### Scenario: Dismissed term not re-suggested
- **WHEN** the owner dismisses `苏柔` and a later chapter's translation suggests `苏柔` again
- **THEN** no new suggestion for `苏柔` is added to the queue

#### Scenario: Existing term not suggested
- **WHEN** a translation suggests a source term that is already in the glossary
- **THEN** it is not added to the queue

### Requirement: Rename propagation to translated chapters
When the owner changes the rendering of an existing term, the system SHALL find chapters whose source text contains the source term and, in those chapters with status translated, replace whole-word, case-sensitive occurrences of the old rendering with the new one.

#### Scenario: Rename applied
- **WHEN** the owner changes `苏柔` from `Tô Nhu` to `Tô Nhược`, and chapters 3 and 7 contain `苏柔` and are translated
- **THEN** every whole-word `Tô Nhu` in chapters 3 and 7 becomes `Tô Nhược`

#### Scenario: Unrelated chapter untouched
- **WHEN** chapter 5 contains the text `Tô Nhu` but its source does not contain `苏柔`
- **THEN** chapter 5 is not modified

#### Scenario: Partial word not replaced
- **WHEN** a chapter affected by the rename contains `Tô Nhuận`
- **THEN** `Tô Nhuận` is left unchanged

### Requirement: Glossary-outdated labelling
After a term is changed or removed, every affected chapter (source contains the term) that is translated or edited SHALL be labelled glossary-outdated with a re-translate action; edited chapters SHALL receive the label but no text replacement.

#### Scenario: Edited chapter labelled only
- **WHEN** a rename affects chapter 3, which is edited
- **THEN** chapter 3 is labelled glossary-outdated and its text is unchanged

#### Scenario: Label cleared on re-translation
- **WHEN** the owner re-translates a glossary-outdated chapter
- **THEN** the label is removed and the chapter records the current glossary version
