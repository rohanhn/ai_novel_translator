# Spec Delta

## ADDED Requirements

### Requirement: Paragraph actions in the reader
When reading a stored translation, the owner SHALL be able to select a paragraph to open its actions: "Thêm vào bộ tên", "Dịch lại đoạn" and "Sửa đoạn". Actions SHALL NOT be offered while the chapter is streaming, and "Dịch lại đoạn" SHALL NOT be offered for a novel imported as Vietnamese.

#### Scenario: Open paragraph actions
- **WHEN** the owner taps paragraph 3 of a translated chapter
- **THEN** paragraph 3 is marked as selected and the three actions are shown with touch targets of at least 44 px

#### Scenario: Streaming chapter
- **WHEN** the chapter is still being translated
- **THEN** tapping a paragraph shows no actions

#### Scenario: Vietnamese novel
- **WHEN** the owner taps a paragraph in a novel imported as Vietnamese
- **THEN** only "Thêm vào bộ tên" and "Sửa đoạn" are shown

### Requirement: Add to glossary from the reader
The "Thêm vào bộ tên" action SHALL show the matching source paragraph so the owner can pick or type the source term, prefill the observed wrong rendering with the text selected in the translated paragraph, and save through the glossary.

#### Scenario: Prefilled from a selection
- **WHEN** the owner selects `Lâm Đông` in paragraph 3 and chooses "Thêm vào bộ tên"
- **THEN** the dialog shows source paragraph 3 and has `Lâm Đông` as the observed rendering

#### Scenario: Selected Han character becomes the source term
- **WHEN** the owner selects the leftover `幽` in the translation and chooses "Thêm vào bộ tên"
- **THEN** the dialog has `幽` as the source term and an empty observed rendering

### Requirement: Paragraph re-translation preview
The "Dịch lại đoạn" action SHALL show the proposed translation next to the current paragraph and SHALL store it only when the owner accepts.

#### Scenario: Reject the proposal
- **WHEN** the owner requests a paragraph re-translation and then dismisses it
- **THEN** the paragraph and chapter status are unchanged

#### Scenario: Accept the proposal
- **WHEN** the owner accepts the proposed text
- **THEN** the paragraph shows the new text and the chapter is labelled as edited
