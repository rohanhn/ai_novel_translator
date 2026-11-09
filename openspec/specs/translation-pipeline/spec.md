# translation-pipeline Specification

## Purpose
Dịch một chương từ ngôn ngữ nguồn sang ngôn ngữ đích bằng LLM, giữ cấu trúc đoạn và tôn trọng glossary.

## Requirements

### Requirement: Segment chapters for LLM calls
The system SHALL split chapter text into segments of at most `NT_MAX_SEGMENT_CHARS` characters, breaking only at paragraph boundaries unless a single paragraph exceeds the limit, in which case it MUST be hard-split.

#### Scenario: Paragraphs fit in limit
- **WHEN** a chapter has five 20-character paragraphs and the limit is 45
- **THEN** no segment exceeds 45 characters and no paragraph is split

#### Scenario: Oversized paragraph
- **WHEN** a single paragraph is 120 characters and the limit is 50
- **THEN** it is split into segments of 50, 50 and 20 characters

### Requirement: Translate a chapter
The system SHALL translate a chapter's title and all its segments with the selected provider, join the results in order, store them on the chapter, record the provider and model used, and set status to `translated`.

#### Scenario: Successful translation
- **WHEN** the user translates chapter 1 of a novel
- **THEN** the chapter has a translated title and text, status `translated`, and provider/model recorded

#### Scenario: Already translated
- **WHEN** the user translates a chapter that is already `translated` without `force`
- **THEN** the existing translation is returned and no LLM call is made

#### Scenario: Provider failure
- **WHEN** the provider raises a translation error (refusal, truncation, API error)
- **THEN** the chapter status becomes `failed` and the error is reported to the user

### Requirement: Glossary-aware prompting
The system SHALL include every glossary entry of the novel in the system prompt as a mandatory term mapping, and SHALL keep the system prompt identical across segments of the same chapter so providers can cache it.

#### Scenario: Glossary present
- **WHEN** the novel's glossary maps `林动` to `Lâm Động`
- **THEN** the system prompt sent to the provider contains `林动 → Lâm Động`
