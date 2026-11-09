# Spec Delta

## MODIFIED Requirements

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
- **WHEN** translation fails with a provider error other than quota
- **THEN** the API returns HTTP 502 with the error category and message

#### Scenario: Quota exhausted
- **WHEN** translation is requested while the whole chain is out of daily quota
- **THEN** the API returns HTTP 429 with the reset time

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Feature parity
**Reason**: The web app is now the primary interface; reader-specific features (progress, prefetch, preferences, streaming) have no meaningful CLI equivalent.
**Migration**: The CLI remains an admin/debug tool with its existing commands; new user-facing features are delivered through the web app and API only.
