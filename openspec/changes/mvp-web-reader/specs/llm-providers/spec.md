# Spec Delta

## MODIFIED Requirements

### Requirement: Pluggable provider registry
The system SHALL expose providers through a registry keyed by name. Built-in providers: `gemini` (Google Gemini API, the default), `anthropic` (Claude), `openai`, `ollama` (OpenAI-compatible endpoint), and `echo` (offline, for tests). Each provider SHALL authenticate with the owner's own API key from configuration.

#### Scenario: Select provider per request
- **WHEN** an admin translates via CLI with `--provider ollama`
- **THEN** that chapter is translated with the ollama provider, bypassing the configured chain

#### Scenario: Unknown provider
- **WHEN** the user selects a provider name that is not registered
- **THEN** the system returns an error listing available providers (API HTTP 400)

#### Scenario: Missing API key
- **WHEN** a chain step's provider has no API key configured
- **THEN** startup or the first translation reports a configuration error naming the missing key, without exposing any key value

### Requirement: Default provider and model from configuration
The system SHALL translate using an ordered provider chain read from configuration, where each step is a provider plus model. The default chain SHALL be a primary Gemini model followed by a lighter Gemini model using the same key. An explicit provider/model given via CLI MUST take precedence over the chain.

#### Scenario: Model override
- **WHEN** the chain is configured and the admin passes `--model X` on the CLI
- **THEN** model `X` is used for that translation

#### Scenario: Default chain
- **WHEN** no chain is configured and only a Gemini API key is set
- **THEN** the system uses the default two-step Gemini chain

### Requirement: Provider failures are normalized
Every provider SHALL report refusals, output truncation, API/network errors, and quota exhaustion as provider-independent error categories, so callers never depend on provider-specific errors. Quota exhaustion MUST be classified as either per-minute (rate) or per-day (daily), with a reset time when the provider supplies one.

#### Scenario: Refusal
- **WHEN** the model declines to translate a chapter
- **THEN** the failure is reported as a refusal error

#### Scenario: Rate limit
- **WHEN** the provider responds with a per-minute rate limit
- **THEN** the failure is classified as rate quota with the suggested retry delay

#### Scenario: Daily limit
- **WHEN** the provider responds that the per-day limit is exhausted
- **THEN** the failure is classified as daily quota

## ADDED Requirements

### Requirement: Fallback chain execution
A foreground translation SHALL try chain steps in order: on daily-quota exhaustion of a step it SHALL move to the next step; on any other error it SHALL stop and report the error without trying further steps. A step known to be exhausted for the day SHALL be skipped without sending a request.

#### Scenario: Primary exhausted
- **WHEN** step 1 returns daily-quota exhaustion for a foreground translation
- **THEN** the same chapter is translated with step 2 and the stored translation records step 2's provider and model

#### Scenario: Non-quota error
- **WHEN** step 1 fails with a refusal
- **THEN** the translation fails with the refusal error and step 2 is not called

#### Scenario: Whole chain exhausted
- **WHEN** every step is exhausted for the day
- **THEN** the translation is rejected with a quota-exhausted result including the earliest reset time

### Requirement: Rate-limit retry
On per-minute rate quota, the system SHALL wait and retry the same step with exponential backoff, honoring the provider's suggested delay, for at most 3 retries before reporting the error.

#### Scenario: Recovered after wait
- **WHEN** step 1 returns a rate-limit error once and then succeeds
- **THEN** the translation completes on step 1 and the reader was informed it is waiting for quota

### Requirement: No quota circumvention
The system MUST use only official provider APIs with the owner's own credentials, MUST NOT rotate multiple accounts or keys of the same provider to bypass limits, and MUST NOT retry beyond the bounds defined here.

#### Scenario: Single key per provider
- **WHEN** two chain steps use the same provider with different models
- **THEN** both steps authenticate with that provider's single configured key; configuration offers no way to assign a different key per step

### Requirement: Daily usage tracking
The system SHALL count successful requests per chain step per day, record when each step became exhausted and its expected reset, and expose this usage to the owner.

#### Scenario: Usage display
- **WHEN** the owner opens settings after 12 successful translations on step 1 today
- **THEN** step 1 shows 12 requests used today and its exhaustion state
