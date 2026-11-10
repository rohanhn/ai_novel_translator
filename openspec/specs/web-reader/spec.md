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
