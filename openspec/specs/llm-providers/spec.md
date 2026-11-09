# llm-providers Specification

## Purpose
Lớp trừu tượng cho nhiều nhà cung cấp LLM, chọn được theo cấu hình hoặc theo từng lần dịch.

## Requirements

### Requirement: Pluggable provider registry
The system SHALL expose providers through a registry keyed by name. Built-in providers: `anthropic` (Claude, default model `claude-opus-5-5`), `openai`, `ollama` (OpenAI-compatible endpoint), and `echo` (offline, for tests).

#### Scenario: Select provider per request
- **WHEN** the user translates with `--provider ollama` (CLI) or `"provider": "ollama"` (API)
- **THEN** that chapter is translated with the ollama provider regardless of `NT_PROVIDER`

#### Scenario: Unknown provider
- **WHEN** the user selects a provider name that is not registered
- **THEN** the system returns an error listing available providers (API HTTP 400)

### Requirement: Default provider and model from configuration
The system SHALL use `NT_PROVIDER` as the default provider and `NT_MODEL` as the default model for that provider; an explicit model in the request MUST take precedence.

#### Scenario: Model override
- **WHEN** `NT_MODEL` is set and the user passes `--model X`
- **THEN** model `X` is used

### Requirement: Provider failures are normalized
Every provider SHALL raise `TranslationError` for refusals, output truncation, and API/network errors, so callers never depend on SDK-specific exceptions.

#### Scenario: Refusal
- **WHEN** the model declines to translate a segment
- **THEN** the provider raises `TranslationError`
