# Spec Delta

## ADDED Requirements

### Requirement: Add a term with its observed wrong rendering
When adding or updating a term, the owner MAY give the wrong rendering seen in the translation. The system SHALL then replace whole-word, case-sensitive occurrences of that rendering with the term's target in translated chapters whose source contains the term, and label those chapters glossary-outdated. Edited chapters SHALL only be labelled.

#### Scenario: Wrong name fixed from the reader
- **WHEN** the owner adds `林动 → Lâm Động` with observed rendering `Lâm Đông`, and translated chapters 3 and 7 contain `林动`
- **THEN** every whole-word `Lâm Đông` in chapters 3 and 7 becomes `Lâm Động` and the glossary contains `林动 → Lâm Động`

#### Scenario: Edited chapter only labelled
- **WHEN** the same term is added with an observed rendering and chapter 5, which contains `林动`, is edited
- **THEN** chapter 5's text is unchanged and it is labelled glossary-outdated

#### Scenario: Chapter without the source term untouched
- **WHEN** chapter 9 contains `Lâm Đông` but its source does not contain `林动`
- **THEN** chapter 9 is not modified

#### Scenario: No observed rendering
- **WHEN** the owner adds a new term without an observed rendering
- **THEN** no chapter text is changed and no chapter is labelled, as for any new term
