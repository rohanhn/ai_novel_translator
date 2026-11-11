# translation-pipeline Specification

## Purpose
Dịch một chương từ ngôn ngữ nguồn sang ngôn ngữ đích bằng LLM, giữ cấu trúc đoạn và tôn trọng glossary.

## Requirements

### Requirement: Segment chapters for LLM calls
The system SHALL send a whole chapter in a single request when its source text is at most the configured chapter limit (default 20,000 characters). Only longer chapters SHALL be split into segments of at most that limit, breaking at paragraph boundaries unless a single paragraph exceeds the limit, in which case it MUST be hard-split.

#### Scenario: Normal chapter
- **WHEN** a chapter has 6,000 source characters and the limit is 20,000
- **THEN** exactly one LLM request is made for the chapter, covering title and body

#### Scenario: Paragraphs fit in limit
- **WHEN** a chapter has five 20-character paragraphs and the limit is 45
- **THEN** no segment exceeds 45 characters and no paragraph is split

#### Scenario: Oversized paragraph
- **WHEN** a single paragraph is 120 characters and the limit is 50
- **THEN** it is split into segments of 50, 50 and 20 characters

### Requirement: Translate a chapter
The system SHALL translate a chapter's title and body in the same request (the first request when segmented), store the result on the chapter, record the provider, model and glossary version used, and set status to `translated`. Translated text SHALL be delivered incrementally to subscribed readers while it is generated.

#### Scenario: Successful translation
- **WHEN** the user translates chapter 1 of a novel
- **THEN** the chapter has a translated title and text, status `translated`, and provider, model and glossary version recorded

#### Scenario: Streaming delivery
- **WHEN** a reader is subscribed to a chapter being translated
- **THEN** it receives translated paragraphs in order as they are produced, then a completion event

#### Scenario: Already translated
- **WHEN** the user translates a chapter that is already `translated` or `edited` without `force`
- **THEN** the existing translation is returned and no LLM call is made

#### Scenario: Provider failure
- **WHEN** the provider reports a refusal, truncation, malformed output, or API error
- **THEN** the chapter status becomes `failed`, no partial translation is stored, and the error is reported to the user

#### Scenario: Quota exhausted
- **WHEN** the translation cannot run because the whole chain is out of daily quota
- **THEN** the chapter stays `pending` (not `failed`) and the quota-exhausted result is reported

### Requirement: Glossary-aware prompting
The system SHALL include every glossary entry of the novel in the instructions sent to the provider as a mandatory term mapping, and SHALL keep those instructions identical across segments of the same chapter so providers can cache them.

#### Scenario: Glossary present
- **WHEN** the novel's glossary maps `林动` to `Lâm Động`
- **THEN** the instructions sent to the provider contain `林动 → Lâm Động`

### Requirement: Name suggestions in the same response
The translation request SHALL ask the model to list proper nouns found in the chapter that are not in the glossary, each with a proposed Vietnamese rendering and a short category; these SHALL be returned in the same response as the translation and added to the glossary suggestion queue without an extra request.

#### Scenario: New name found
- **WHEN** chapter 4 contains `苏柔`, which is not in the glossary
- **THEN** after translation a pending suggestion `苏柔 → <proposed rendering>` exists for the novel and no additional LLM request was made

#### Scenario: No suggestions section
- **WHEN** the response contains a complete title and body but no name list
- **THEN** the translation is stored normally and no suggestions are added

### Requirement: Output completeness check
The system SHALL reject a response whose body is empty or whose generation was cut off before completion, and SHALL flag (not reject) a translation whose paragraph count differs from the source by more than 20%.

#### Scenario: Truncated output
- **WHEN** the provider stops because of its output limit
- **THEN** the translation fails as truncated and nothing is stored

#### Scenario: Paragraph mismatch
- **WHEN** the source has 50 paragraphs and the translation has 35
- **THEN** the translation is stored with a possible-omission flag visible in the reader
