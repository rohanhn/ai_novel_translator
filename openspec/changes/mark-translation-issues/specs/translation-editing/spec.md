# Spec Delta

## ADDED Requirements

### Requirement: Edit a single paragraph
The owner SHALL be able to replace one paragraph of a chapter's stored translation, identified by its position, without sending the rest of the chapter. Other paragraphs and the title SHALL stay unchanged, and the chapter status SHALL become edited.

#### Scenario: Paragraph edited
- **WHEN** the owner replaces paragraph 3 of translated chapter 2 with new text
- **THEN** paragraph 3 shows the new text, every other paragraph is unchanged, and chapter 2 has status edited

#### Scenario: Empty paragraph rejected
- **WHEN** the owner saves paragraph 3 with only whitespace
- **THEN** the request is rejected with a validation error and the chapter is unchanged

#### Scenario: Chapter without translation
- **WHEN** the owner edits a paragraph of a chapter that has no translation
- **THEN** the request is rejected and nothing is stored

### Requirement: Paragraph changes require an unchanged chapter
A paragraph edit SHALL include the paragraph text the owner saw. If the stored paragraph at that position differs, for example because the chapter was re-translated meanwhile, the system SHALL reject the edit (HTTP 409) and leave the chapter unchanged.

#### Scenario: Chapter re-translated meanwhile
- **WHEN** chapter 2 is re-translated after the owner opened it and the owner then saves paragraph 3
- **THEN** the edit is rejected with HTTP 409 and a message to reload the chapter, and the new translation is kept

### Requirement: Re-translate a single paragraph
The owner SHALL be able to request a new translation of one paragraph of a chapter. The system SHALL send only the matching source paragraph, with the novel's glossary, in one request through the normal provider chain and quota accounting, and SHALL return the proposed text without storing it.

#### Scenario: Proposal returned
- **WHEN** the owner requests a re-translation of paragraph 3 of chapter 2
- **THEN** exactly one translation request containing source paragraph 3 is made, the proposed Vietnamese text is returned, and chapter 2 is unchanged

#### Scenario: Proposal accepted
- **WHEN** the owner accepts the proposed text for paragraph 3
- **THEN** paragraph 3 is replaced as in a paragraph edit and chapter 2 has status edited

#### Scenario: Paragraph counts differ
- **WHEN** chapter 2's translation has a different number of paragraphs from its source
- **THEN** a paragraph re-translation request is rejected with a message to edit the paragraph or re-translate the chapter, and no translation request is made

#### Scenario: Quota exhausted
- **WHEN** the owner requests a paragraph re-translation while the whole chain is out of daily quota
- **THEN** the quota-exhausted result is reported and the chapter is unchanged

#### Scenario: Novel without source text to translate
- **WHEN** the owner requests a paragraph re-translation in a novel imported as Vietnamese
- **THEN** the request is rejected and no translation request is made
