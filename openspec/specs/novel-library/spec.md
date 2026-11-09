# novel-library Specification

## Purpose
Quản lý truyện và chương: nhập truyện từ file nguồn, liệt kê, xem nội dung, xuất bản dịch.

## Requirements

### Requirement: Import novel from TXT
The system SHALL import a novel from a plain-text file, splitting it into chapters by headings of the form `第X章`, `第X回`, `第X节` or `第X卷`, and SHALL auto-detect UTF-8 or GB18030 encoding.

#### Scenario: File with chapter headings
- **WHEN** the user imports a TXT file containing two `第X章` headings
- **THEN** a novel is created with 2 chapters, numbered from 1 in file order, each with status `pending`

#### Scenario: File without chapter headings
- **WHEN** the user imports a non-empty TXT file with no recognizable headings
- **THEN** a novel is created with a single chapter containing the whole text

#### Scenario: Empty file
- **WHEN** the user imports an empty file
- **THEN** the import is rejected with an error and no novel is created

### Requirement: Browse novels and chapters
The system SHALL list novels, list chapters of a novel with their translation status, and show a chapter's source or translated text.

#### Scenario: Unknown novel
- **WHEN** the user requests chapters of a novel id that does not exist
- **THEN** the system returns a not-found error (CLI exit code 1, API HTTP 404)

### Requirement: Export translated novel
The system SHALL export the translated chapters of a novel to a file, in chapter order, skipping chapters that are not yet translated. Supported formats: `txt`.

#### Scenario: Partially translated novel
- **WHEN** a novel has chapter 1 translated and chapter 2 pending, and the user exports to TXT
- **THEN** the output contains the novel title and chapter 1 only

#### Scenario: Unsupported format
- **WHEN** the user exports with a format that has no exporter
- **THEN** the system returns an error listing supported formats
