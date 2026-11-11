# Spec Delta

## ADDED Requirements

### Requirement: Untranslated text label
A chapter with a non-zero untranslated count SHALL show the plain label "Còn chữ chưa dịch" in the chapter list. The reader SHALL show a notice with the number of untranslated characters and a re-translate action, which follows the same confirmation as any re-translation of an edited chapter.

#### Scenario: Label in the chapter list
- **WHEN** chapter 2 has an untranslated count of 72
- **THEN** the chapter list shows chapter 2 with the label "Còn chữ chưa dịch"

#### Scenario: Notice in the reader
- **WHEN** the owner opens chapter 2 with an untranslated count of 72
- **THEN** the reader shows a notice that 72 characters are untranslated, with a "Dịch lại" action

#### Scenario: No label for a clean chapter
- **WHEN** a chapter's untranslated count is 0
- **THEN** neither the label nor the notice is shown

### Requirement: Highlight untranslated characters
The reader SHALL visually highlight every counted untranslated Han character in the displayed translated title and text, with a highlight that meets the UI contrast rules in light and dark themes and does not change the text itself.

#### Scenario: Highlighted leftovers
- **WHEN** the owner reads a translation containing `hoảng đ蕩着 hoàn nhiệt`
- **THEN** `蕩着` is highlighted and the surrounding Vietnamese text is shown normally

#### Scenario: Glossary-kept characters are not highlighted
- **WHEN** the translation contains `Đan (丹)` from the glossary mapping `丹 → Đan (丹)`
- **THEN** `丹` is not highlighted
