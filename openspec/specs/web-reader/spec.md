# web-reader Specification

## Purpose
Trải nghiệm đọc truyện đã dịch trên web, ưu tiên điện thoại: mở chương nhanh, xem bản dịch hình thành dần khi đang dịch, tùy chỉnh giao diện đọc và tiếp tục đúng chỗ đã dừng.

## Requirements

### Requirement: Edit novel details screen
The novel page SHALL offer a "Sửa thông tin" action that opens a form pre-filled with the current title, author, short description and cover. Nothing SHALL be saved until the owner confirms; cancelling SHALL leave the novel unchanged. Server validation errors SHALL appear next to the field concerned while keeping the entered values. After saving, the novel page, page title and library SHALL show the new details without a manual reload.

#### Scenario: Edit title, author and description
- **WHEN** the owner opens "Sửa thông tin", changes the title, enters an author and a two-line description, and saves
- **THEN** the novel page shows the new title, the author and both description lines, and the library shows the new title and author

#### Scenario: Cancel
- **WHEN** the owner edits fields, chooses an image, and then cancels
- **THEN** nothing is saved and the novel looks as before

### Requirement: Cover selection in the edit form
The form SHALL preview the current cover (or the generated one), let the owner choose an image from the device or paste an image link, preview the new image before saving, and offer to remove an existing cover. A pasted link SHALL be downloaded by the server, never by the browser, with a loading state and errors shown next to the link field. A chosen file that is not JPG, PNG or WebP, or exceeds 10 MB, SHALL be reported without being uploaded.

#### Scenario: Choose and save a cover
- **WHEN** the owner chooses a PNG image in the form and saves
- **THEN** the form previews it first, and afterwards the novel page and the library card show that image instead of the generated cover

#### Scenario: Cover from a pasted link
- **WHEN** the owner pastes a link to an image, presses "Lấy ảnh", and saves
- **THEN** the form shows a loading state, then previews the downloaded image, and after saving the novel page and the library show it

#### Scenario: Broken link
- **WHEN** the owner pastes a link that cannot be downloaded or is not an image
- **THEN** the form shows the reason next to the link field and the current cover preview is kept

#### Scenario: Browser does not load the link
- **WHEN** the owner pastes an image link
- **THEN** the browser makes no request to the link's host; only the app server does

#### Scenario: Remove the cover
- **WHEN** the owner removes the cover in the form and saves
- **THEN** the novel page and the library show the generated cover again

#### Scenario: Unsupported file chosen
- **WHEN** the owner chooses a `.gif` file or a 12 MB JPG
- **THEN** the form explains which formats or size are accepted and does not upload the file

### Requirement: Edit form layout
The edit form SHALL be usable at 360 px width without horizontal scrolling, and its save and cancel buttons SHALL always be inside the viewport.

#### Scenario: Small screen
- **WHEN** the form is opened on a 360×740 screen
- **THEN** every field is reachable without horizontal scrolling and the save button is inside the viewport

### Requirement: Novel details display
The novel page SHALL show the author and the short description when present, keeping line breaks, and no empty labels otherwise. The library card SHALL show the author under the title when present. The library search SHALL match the title or the author.

#### Scenario: Search by author
- **WHEN** the owner types part of an author's name into the library search
- **THEN** the novels by that author are shown

#### Scenario: Novel without details
- **WHEN** the owner opens a novel that has no author, no description and no cover
- **THEN** the page shows the generated cover and no empty author or description labels

### Requirement: Cover display with fallback
The library and the novel page SHALL show the uploaded cover when one exists and the generated cover otherwise. If the image fails to load, the generated cover SHALL be shown instead. A cover shown next to the title SHALL have an empty alternative text.

#### Scenario: Broken image falls back
- **WHEN** a novel's cover image cannot be loaded
- **THEN** the generated cover with the novel's title is shown instead

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
The reader SHALL let the owner choose background theme (at least light, sepia, dark, displayed as Tuyên chỉ, Hoàng quyển and Dạ nguyệt), font size, and line height; preferences SHALL be stored server-side and apply on every device.

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

### Requirement: Plain-language labels
Every themed (xianxia-style) navigation or section label in the web UI SHALL be shown together with a plain-language label, and chapter statuses, error messages, quota notices and confirmation dialogs SHALL use plain wording only.

#### Scenario: Themed navigation label
- **WHEN** the owner sees the navigation item "Tàng Thư Các"
- **THEN** the plain label "Thư viện" is displayed with it

#### Scenario: Failed chapter status
- **WHEN** a chapter's translation has failed
- **THEN** its status is shown as plain wording such as "Lỗi" together with the reason, not as a themed term
