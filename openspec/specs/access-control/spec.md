# access-control Specification

## Purpose
Bảo vệ workspace cá nhân trên internet: chỉ chủ sở hữu duy nhất đăng nhập được, và nội dung không bị công cụ tìm kiếm lập chỉ mục.

## Requirements

### Requirement: Single-owner password login
The system SHALL authenticate the single owner with one password configured via environment variable and establish a session cookie that is HttpOnly, Secure, and SameSite=Lax. The system MUST refuse to start if no password is configured.

#### Scenario: Correct password
- **WHEN** the owner submits the configured password on the login page
- **THEN** a session is created and the owner is redirected to the library

#### Scenario: Wrong password
- **WHEN** a client submits an incorrect password
- **THEN** the system responds with an authentication error and creates no session

#### Scenario: Missing configuration
- **WHEN** the application starts without a configured password
- **THEN** startup fails with an error explaining which variable is missing

### Requirement: Protected endpoints
The system SHALL require a valid session for every page and API endpoint except the login page, the login endpoint, the health check, and static assets needed to render the login page.

#### Scenario: Unauthenticated API call
- **WHEN** a client without a valid session calls any protected API endpoint
- **THEN** the API returns HTTP 401 and no data

#### Scenario: Unauthenticated page visit
- **WHEN** a browser without a valid session opens any app page
- **THEN** it is shown the login page

### Requirement: Session lifetime and logout
Sessions SHALL expire after 30 days of inactivity, and the owner SHALL be able to log out, which invalidates the current session immediately.

#### Scenario: Logout
- **WHEN** the owner logs out
- **THEN** the session cookie is cleared and subsequent requests with the old cookie return HTTP 401

#### Scenario: Expired session
- **WHEN** a request carries a session idle for more than 30 days
- **THEN** it is treated as unauthenticated

### Requirement: Brute-force protection
The system SHALL lock login attempts from a client IP for 15 minutes after 5 consecutive failed attempts within 15 minutes.

#### Scenario: Too many failures
- **WHEN** a client IP fails login 5 times within 15 minutes
- **THEN** further login attempts from that IP are rejected with HTTP 429 for 15 minutes, even with the correct password

### Requirement: No search indexing
Every response SHALL carry an `X-Robots-Tag: noindex, nofollow` header, and `/robots.txt` SHALL disallow all crawling.

#### Scenario: Crawler request
- **WHEN** any client fetches `/robots.txt`
- **THEN** it receives a policy disallowing all paths for all user agents
