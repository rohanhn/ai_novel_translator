# interfaces Specification

## Purpose
Hai giao diện song song — CLI (`novel`) và HTTP API (FastAPI) — cùng gọi chung lớp application.

## Requirements

### Requirement: CLI commands
The system SHALL provide a `novel` CLI for administration and debugging with commands: `import`, `list`, `chapters`, `translate <novel> <start> [end]`, `show`, `export`, `glossary set|list|rm`, and `serve`. CLI translation SHALL use the same provider chain and storage as the web app.

#### Scenario: Translate a range
- **WHEN** the admin runs `novel translate 1 1 3`
- **THEN** chapters 1 to 3 of novel 1 are translated in order through the provider chain and each result is printed

#### Scenario: Shared data
- **WHEN** a chapter is translated via CLI
- **THEN** the web reader shows it as translated

### Requirement: HTTP API
The system SHALL expose a JSON HTTP API under `/api` covering: authentication, library (list, upload, delete), chapters (list, read, translate, edit), translation streaming, glossary and suggestions, reading progress and preferences, and settings/quota status. All endpoints except login and health SHALL require a session.

#### Scenario: Upload novel
- **WHEN** an authenticated client POSTs a TXT file as multipart to the library upload endpoint
- **THEN** the API returns 201 with the created novel

#### Scenario: Translation provider error
- **WHEN** a translation is requested and the provider chain cannot be used (missing API key, unknown provider or model)
- **THEN** the API returns HTTP 502 with the error category and message, and no job is created

#### Scenario: Provider error during translation
- **WHEN** an accepted translation (HTTP 202) later fails with a provider error other than quota
- **THEN** the translation event stream emits a `failed` terminal event carrying the error category and message

#### Scenario: Quota exhausted
- **WHEN** translation is requested while the whole chain is out of daily quota
- **THEN** the API returns HTTP 429 with the reset time, and no job is created

### Requirement: CLI edit novel details
The CLI SHALL provide `novel edit <novel> [--title T] [--author A] [--description D]`, changing only the given fields under the same rules as the API; an empty value SHALL clear author or description. No option, invalid values or an unknown novel SHALL exit non-zero with a message and change nothing. `novel list` SHALL show the author when present. Cover images are scoped to the web and HTTP API only.

#### Scenario: Set author from the CLI
- **WHEN** the user runs `novel edit 1 --author "Phong Hỏa Hí Chư Hầu"`
- **THEN** novel 1's author is set, its title is unchanged, and `novel list` shows the author

#### Scenario: No option given
- **WHEN** the user runs `novel edit 1`
- **THEN** the command exits with a non-zero code and a message saying at least one field is required

#### Scenario: Unknown novel
- **WHEN** the user runs `novel edit 999 --title X` and novel 999 does not exist
- **THEN** the command exits with a non-zero code and a "not found" message

### Requirement: Translation event stream
The API SHALL provide a server-sent event stream per chapter translation that emits progress events (waiting-for-quota, paragraph, fallback-step-used), then exactly one terminal event (completed, failed, or quota-exhausted). Multiple clients MAY subscribe to the same running translation.

#### Scenario: Subscribe mid-way
- **WHEN** a client subscribes to a translation that has already produced 10 paragraphs
- **THEN** it first receives those 10 paragraphs, then subsequent ones, then the terminal event

### Requirement: Web application delivery
The system SHALL serve the web application at the root path of its host from the same process as the API, with client-side routes falling back to the app entry page.

#### Scenario: Deep link
- **WHEN** an authenticated browser opens `/novels/1/chapters/12` directly
- **THEN** the web app loads and shows chapter 12 of novel 1
