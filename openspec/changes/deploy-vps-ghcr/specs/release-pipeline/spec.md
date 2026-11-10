# Spec Delta

## Purpose

Mỗi thay đổi đều được kiểm tra tự động; image chạy production chỉ được dựng, quét lỗ hổng và đẩy lên registry từ CI, với tag ổn định để VPS ghim và rollback.

## ADDED Requirements

### Requirement: Checks on pull requests, default branch and releases
For every pull request, every push to the default branch, and every push of a `vX.Y.Z` tag, CI SHALL run the Python linter, the Python test suite against a PostgreSQL 16 database, the web type check, the web contrast check, the web build, the browser end-to-end tests, and a lint of the shell scripts in the repository. Tests SHALL use the `echo` provider and SHALL NOT need or call a real LLM key. Any failing check SHALL fail the run.

#### Scenario: Failing test blocks the pull request
- **WHEN** a pull request contains a change that makes one Python test fail
- **THEN** the CI run for that pull request is reported as failed

#### Scenario: No LLM secret needed
- **WHEN** CI runs on a fork or without any LLM API key configured
- **THEN** all checks can still pass

### Requirement: Image build and vulnerability scan
After the checks pass, CI SHALL build the application image and scan it for known vulnerabilities. The run SHALL fail if the image contains a HIGH or CRITICAL vulnerability that has a fixed version available. The scan SHALL happen before any image is pushed.

#### Scenario: Fixable critical vulnerability
- **WHEN** the built image contains a CRITICAL vulnerability with a fix available
- **THEN** the run fails and no image is pushed

#### Scenario: Unfixed vulnerability
- **WHEN** the image only contains HIGH vulnerabilities with no fixed version available
- **THEN** the scan does not fail the run

### Requirement: Image publishing rules
CI SHALL push the scanned image to the GitHub Container Registry of the repository only for a push to the default branch or a push of a git tag of the form `vX.Y.Z`. Pull requests SHALL never push an image. A release tag SHALL be published only if its commit is in the default branch's history. The pushed image SHALL be the exact image that was scanned.

#### Scenario: Pull request
- **WHEN** CI runs for a pull request
- **THEN** the image is built and scanned but not pushed

#### Scenario: Release tag outside the default branch
- **WHEN** git tag `v1.5.0` is pushed on a commit that is not in the default branch's history
- **THEN** the run fails and no image is pushed

#### Scenario: Non-version tag
- **WHEN** a git tag `test-build` is pushed
- **THEN** no image is pushed

### Requirement: Image tags
An image pushed from the default branch SHALL be tagged `sha-<first 7 characters of the commit>` and `latest`. An image pushed for git tag `vX.Y.Z` SHALL be tagged `vX.Y.Z` only; a release SHALL NOT move `latest` and SHALL NOT overwrite an existing `sha-` tag.

#### Scenario: Merge to the default branch
- **WHEN** commit `a1b2c3d…` is pushed to the default branch and all checks pass
- **THEN** the registry has the image tagged `sha-a1b2c3d` and `latest`

#### Scenario: Release tag
- **WHEN** git tag `v1.4.0` is pushed on a commit whose checks pass
- **THEN** the registry has that image tagged `v1.4.0`, while `latest` and the commit's `sha-` tag still point to the images pushed from the default branch

### Requirement: Image carries its version
Each image SHALL record the version it was built from: the git tag for a release, otherwise `sha-<short commit>`. The running application SHALL log this version at startup and report it to the logged-in owner in its health response.

#### Scenario: Version visible after deploy
- **WHEN** the image tagged `v1.4.0` is running
- **THEN** its startup log and the health response seen by the logged-in owner both show `v1.4.0`
