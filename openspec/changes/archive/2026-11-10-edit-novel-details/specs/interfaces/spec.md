# Spec Delta

## ADDED Requirements

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
