# Spec Delta

## ADDED Requirements

### Requirement: Client address behind a trusted proxy
The system SHALL determine the client IP used for brute-force protection from the direct connection, unless that connection comes from a trusted proxy. For a connection from a trusted proxy, the system SHALL use the last address in `X-Forwarded-For` when it is a valid IP, and the direct connection address otherwise.

#### Scenario: Proxy inside a trusted range
- **WHEN** trusted proxies are set to `172.18.0.0/16` and a request comes from `172.18.0.5` with `X-Forwarded-For: 203.0.113.7`
- **THEN** failed logins are counted for `203.0.113.7`

#### Scenario: Untrusted sender spoofs the header
- **WHEN** a request comes directly from `198.51.100.9`, which is not trusted, with `X-Forwarded-For: 203.0.113.7`
- **THEN** failed logins are counted for `198.51.100.9`

### Requirement: Trusted proxy configuration
Trusted proxies SHALL be configurable as a comma-separated list of IP addresses and CIDR ranges, in IPv4 and IPv6. An invalid entry SHALL stop startup with a message naming the entry.

#### Scenario: Single address and range together
- **WHEN** trusted proxies are set to `10.0.0.2, fd00::/8`
- **THEN** requests from `10.0.0.2` and from `fd00::5` are both treated as coming from a trusted proxy

#### Scenario: Invalid setting
- **WHEN** trusted proxies are set to `172.18.0.0/99`
- **THEN** the application refuses to start and names `172.18.0.0/99` as invalid
