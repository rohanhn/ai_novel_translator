# Spec Delta

## MODIFIED Requirements

### Requirement: CLI commands
The system SHALL provide a `novel` CLI for administration and debugging with commands: `import`, `list`, `chapters`, `translate <novel> <start> [end]`, `show`, `export`, `glossary set|list|rm`, `migrate`, and `serve`. CLI translation SHALL use the same provider chain and storage as the web app. `novel migrate` SHALL apply the missing database migrations, print the versions it applied (or that the database is up to date), and exit with a non-zero code and a message if a migration fails. It SHALL need no LLM key and no login password configured.

#### Scenario: Translate a range
- **WHEN** the admin runs `novel translate 1 1 3`
- **THEN** chapters 1 to 3 of novel 1 are translated in order through the provider chain and each result is printed

#### Scenario: Shared data
- **WHEN** a chapter is translated via CLI
- **THEN** the web reader shows it as translated

#### Scenario: Migrate a fresh database
- **WHEN** the admin runs `novel migrate` against an empty database
- **THEN** every migration is applied, their versions are printed, and the command exits with code 0

#### Scenario: Nothing to migrate
- **WHEN** the admin runs `novel migrate` on an up-to-date database
- **THEN** it reports that the database is up to date and exits with code 0
