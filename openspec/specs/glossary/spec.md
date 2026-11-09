# glossary Specification

## Purpose
Bảng thuật ngữ theo từng truyện (tên nhân vật, địa danh, cảnh giới, chiêu thức) để bản dịch nhất quán giữa các chương.

## Requirements

### Requirement: Manage glossary terms per novel
The system SHALL let the user add or update (upsert), list, and remove glossary terms scoped to a single novel. A source term MUST be unique within a novel.

#### Scenario: Upsert existing term
- **WHEN** the user sets `林动 → Lâm Động` and later sets `林动 → Lâm Đông`
- **THEN** the glossary contains a single entry for `林动` with target `Lâm Đông`

#### Scenario: Remove missing term
- **WHEN** the user removes a term that does not exist
- **THEN** the system returns a not-found error
