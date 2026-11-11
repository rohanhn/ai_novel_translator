# Spec Delta

## ADDED Requirements

### Requirement: Untranslated Han check
After a translation is produced, the system SHALL count the Han (Chinese) characters left in the translated title and text and store the count with the chapter. A translation with a non-zero count SHALL be stored and flagged, not rejected. Han characters that appear in the target text of one of the novel's glossary entries SHALL NOT be counted.

#### Scenario: Han characters left in the translation
- **WHEN** a chapter is translated and the translated text still contains `蕩`, `幽` and `瞬`
- **THEN** the translation is stored with status `translated` and an untranslated count of 3

#### Scenario: Clean translation
- **WHEN** a chapter is translated and the translated title and text contain no Han characters
- **THEN** the untranslated count is 0 and the chapter is not flagged

#### Scenario: Han character kept on purpose by the glossary
- **WHEN** the glossary maps `丹` to `Đan (丹)` and the translation contains `丹` only inside that rendering
- **THEN** that character is not counted

#### Scenario: Chinese punctuation is not counted
- **WHEN** the translated text contains `《`, `》` or `，` but no Han characters
- **THEN** the untranslated count is 0

### Requirement: Untranslated count follows the stored translation
The untranslated count SHALL be recomputed whenever the stored translated title or text changes, including re-translation and manual edits, and SHALL be 0 when the chapter has no translation. A chapter reused unchanged by a chapter update SHALL keep its count. Chapters translated before this check existed SHALL have their count computed when the system is upgraded, without re-translating them.

#### Scenario: Manual edit removes the leftovers
- **WHEN** the owner edits a chapter with an untranslated count of 3 and saves text without Han characters
- **THEN** the chapter's untranslated count becomes 0

#### Scenario: Re-translation
- **WHEN** a chapter with an untranslated count of 3 is re-translated and the new translation has none
- **THEN** the chapter's untranslated count becomes 0

#### Scenario: Existing translations after upgrade
- **WHEN** the system is upgraded while a stored translation contains 72 Han characters
- **THEN** that chapter has an untranslated count of 72 without any translation request
