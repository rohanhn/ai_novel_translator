# Spec Delta

## Purpose

Dịch trước chương kế tiếp (N+1) khi chủ sở hữu thực sự đang đọc chương N, để lật chương không phải chờ, mà không lấn vào quota dành cho chương được chủ động mở.

## ADDED Requirements

### Requirement: Reading-signal trigger
The system SHALL start a background translation of chapter N+1 only after at least one reading signal on chapter N: the chapter has been visible for 30 seconds, the owner has scrolled past 60% of it, or the owner explicitly requests preparing the next chapter.

#### Scenario: Read long enough
- **WHEN** chapter 7 has been open and visible for 30 seconds and chapter 8 is pending
- **THEN** a background translation of chapter 8 starts

#### Scenario: Just opened
- **WHEN** the owner opens chapter 7 and leaves within 10 seconds without scrolling past 60%
- **THEN** no prefetch of chapter 8 is started

### Requirement: Prefetch blocking conditions
The system MUST NOT start a prefetch when chapter N+1 does not exist, already has a stored translation, is already being translated, is marked edited, or when prefetch is disabled in settings.

#### Scenario: Next already translated
- **WHEN** the reading signal fires on chapter 7 and chapter 8 is already translated
- **THEN** no LLM request is made

#### Scenario: Last chapter
- **WHEN** the reading signal fires on the last chapter
- **THEN** no prefetch is started

### Requirement: One-chapter depth
At most one prefetch SHALL run at a time, and it SHALL only target the chapter immediately after the one being read.

#### Scenario: No chaining
- **WHEN** a prefetch of chapter 8 completes while the owner is still on chapter 7
- **THEN** chapter 9 is not prefetched until a reading signal fires on chapter 8

### Requirement: Prefetch uses primary quota only
A background prefetch SHALL use only the first step of the provider chain. If that step is out of daily quota, prefetch SHALL be suspended until the quota resets; fallback steps are reserved for chapters the owner opens.

#### Scenario: Primary exhausted
- **WHEN** the first chain step returns daily-quota exhaustion and the reading signal fires
- **THEN** no prefetch is started and no request is sent to the second chain step

#### Scenario: Owner opens chapter after primary exhausted
- **WHEN** the first chain step is exhausted and the owner opens a pending chapter
- **THEN** the foreground translation uses the second chain step

### Requirement: Prefetch completion on navigation away
A prefetch that has already sent its request SHALL run to completion and store its result even if the owner leaves the novel; a prefetch that has not yet sent its request SHALL be cancelled.

#### Scenario: Owner leaves mid-translation
- **WHEN** the owner closes the reader while chapter 8's prefetch is streaming
- **THEN** chapter 8's translation is completed and stored

### Requirement: Prefetch setting
The owner SHALL be able to enable or disable prefetch globally; it SHALL be enabled by default.

#### Scenario: Disabled
- **WHEN** prefetch is disabled and a reading signal fires
- **THEN** no background translation starts
