# Spec Delta

## Purpose

Trải nghiệm đọc truyện đã dịch trên web, ưu tiên điện thoại: mở chương nhanh, xem bản dịch hình thành dần khi đang dịch, tùy chỉnh giao diện đọc và tiếp tục đúng chỗ đã dừng.

## ADDED Requirements

### Requirement: Open a translated chapter
When the owner opens a chapter that already has a stored translation, the reader SHALL display the stored translation without calling any LLM.

#### Scenario: Stored translation
- **WHEN** the owner opens chapter 5 that has status translated
- **THEN** the translated title and text are displayed and no translation request is made

### Requirement: Open an untranslated chapter with streaming
When the owner opens a chapter with no stored translation, the reader SHALL start its translation as a foreground request and display translated paragraphs progressively as they arrive.

#### Scenario: Progressive display
- **WHEN** the owner opens a pending chapter
- **THEN** a translating indicator is shown and translated paragraphs appear incrementally before the whole chapter is complete

#### Scenario: Translation already in progress
- **WHEN** the owner opens a chapter whose translation is already running (for example from prefetch)
- **THEN** the reader attaches to that running translation instead of starting a second one

#### Scenario: Translation fails
- **WHEN** the translation of the opened chapter fails
- **THEN** the reader shows the reason and a retry action, and the source text remains viewable

### Requirement: Quota exhaustion notice
When no step of the provider chain has daily quota left, the reader SHALL tell the owner that today's quota is exhausted and when it resets, and SHALL keep stored translations readable.

#### Scenario: All quota exhausted
- **WHEN** the owner opens a pending chapter and every chain step has exhausted its daily quota
- **THEN** the reader shows the quota-exhausted notice with the reset time and does not mark the chapter failed

### Requirement: Chapter navigation
The reader SHALL provide previous/next chapter navigation and a chapter list showing each chapter's status (pending, translating, translated, edited, failed, glossary-outdated).

#### Scenario: Next chapter already prefetched
- **WHEN** the owner moves to chapter N+1 whose translation was completed by prefetch
- **THEN** it is displayed immediately as a stored translation

#### Scenario: Last chapter
- **WHEN** the owner is on the last chapter
- **THEN** the next-chapter control is disabled

### Requirement: Source text view
The reader SHALL let the owner switch between the translated text and the original source text of the current chapter.

#### Scenario: Toggle source
- **WHEN** the owner toggles to source view
- **THEN** the original Chinese title and text are shown

### Requirement: Translation provenance labels
The reader SHALL label a chapter that was translated by a fallback (non-primary) chain step, and a chapter whose translation predates a glossary change affecting it.

#### Scenario: Fallback label
- **WHEN** the displayed translation was produced by the second chain step
- **THEN** the reader shows a label indicating the fallback model was used, with a re-translate action

### Requirement: Reading preferences
The reader SHALL let the owner choose background theme (at least light, sepia, dark), font size, and line height; preferences SHALL be stored server-side and apply on every device.

#### Scenario: Preferences persist across devices
- **WHEN** the owner sets dark theme on the phone and later opens the reader on a laptop
- **THEN** the reader uses dark theme on the laptop

### Requirement: Reading progress
The system SHALL record, per novel, the last chapter read and the scroll position within it, and SHALL offer to resume from that point when the owner opens the novel.

#### Scenario: Resume reading
- **WHEN** the owner reads novel 1 to 40% of chapter 12, then later opens novel 1
- **THEN** the reader opens chapter 12 scrolled to approximately 40%

### Requirement: Mobile-first layout
The reader SHALL be usable without horizontal scrolling on viewports 360px wide and larger, with touch targets of at least 44x44 CSS pixels for navigation controls.

#### Scenario: Small phone
- **WHEN** the reader is displayed on a 360px-wide viewport
- **THEN** text wraps within the viewport and no horizontal scrollbar appears
