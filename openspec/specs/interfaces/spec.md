# interfaces Specification

## Purpose
Hai giao diện song song — CLI (`novel`) và HTTP API (FastAPI) — cùng gọi chung lớp application.

## Requirements

### Requirement: CLI commands
The system SHALL provide a `novel` CLI with commands: `import`, `list`, `chapters`, `translate <novel> <start> [end]`, `show`, `export`, `glossary set|list|rm`, and `serve`.

#### Scenario: Translate a range
- **WHEN** the user runs `novel translate 1 1 3`
- **THEN** chapters 1 to 3 of novel 1 are translated in order and each result is printed

### Requirement: HTTP API
The system SHALL expose: `GET /health`, `GET /providers`, `GET|POST /novels`, `GET /novels/{id}/chapters`, `GET /novels/{id}/chapters/{index}`, `POST /novels/{id}/chapters/{index}/translate`, and `GET|PUT /novels/{id}/glossary`, `DELETE /novels/{id}/glossary/{term}`.

#### Scenario: Upload novel
- **WHEN** a client POSTs a TXT file as multipart to `/novels`
- **THEN** the API returns 201 with the created novel

#### Scenario: Translation provider error
- **WHEN** translation fails with a provider error
- **THEN** the API returns HTTP 502 with the error message

### Requirement: Feature parity
Every user-facing capability SHALL be reachable from both the CLI and the HTTP API, unless a change proposal explicitly scopes it to one interface.

#### Scenario: New capability
- **WHEN** a new user-facing capability is added
- **THEN** it is available in both CLI and API

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
