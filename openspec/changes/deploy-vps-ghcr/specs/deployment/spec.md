# Spec Delta

## Purpose

Cách app chạy trong production trên một VPS Docker dùng chung: container không trạng thái và hạ quyền, tự migrate trước khi nhận request, đứng sau Traefik, cập nhật và rollback chỉ bằng cách đổi tag image.

## ADDED Requirements

### Requirement: Deployment layout
The repository SHALL provide a deployment template of one compose file and one example environment file; running the application SHALL need only those two files in the server's application directory, which MAY also hold the backup script. All secrets SHALL live only in the environment file, which the documentation SHALL require to be readable by its owner only (mode 600).

#### Scenario: No source code on the server
- **WHEN** the operator deploys following the documentation
- **THEN** the server directory holds no source code, the application runs from the compose file and the environment file alone, and no build happens on the server

### Requirement: Pinned published image
The compose file SHALL run the published image selected by a required `IMAGE_TAG` variable and SHALL NOT build from source. Starting with a missing required variable SHALL fail with a message naming the variable.

#### Scenario: Missing image tag
- **WHEN** the operator starts the application with no `IMAGE_TAG` set
- **THEN** compose refuses to start and names `IMAGE_TAG` as missing

### Requirement: Update and rollback by image tag
Updating or rolling back SHALL consist of changing `IMAGE_TAG` in the environment file and then pulling and recreating the service. Rolling back to any earlier release that ran against the same database SHALL NOT require restoring the database.

#### Scenario: Update
- **WHEN** the operator changes `IMAGE_TAG` from `v1.3.0` to `v1.4.0` and runs pull and up
- **THEN** the application runs `v1.4.0`, applies any new migrations at startup, and logs `v1.4.0` at startup

#### Scenario: Short interruption
- **WHEN** the operator updates the image while the owner has a chapter stream open
- **THEN** the site is unavailable for less than 20 seconds (excluding image download and migration time), the reader shows that the connection was lost, and reopening the chapter afterwards translates it again

#### Scenario: Rollback without restoring data
- **WHEN** `v1.4.0` added a migration and the operator sets `IMAGE_TAG` back to `v1.3.0` and runs pull and up
- **THEN** `v1.3.0` starts successfully on the migrated database and its data is intact

### Requirement: Network exposure and routing
The application container SHALL publish no host port. It SHALL join the externally managed `traefik` and `postgres` networks and SHALL be routed by the shared reverse proxy over HTTPS for the host name configured in `APP_HOST`. The translation event stream SHALL be delivered incrementally through the reverse proxy.

#### Scenario: Reachable only through the proxy
- **WHEN** the application is running
- **THEN** it is reachable at `https://<APP_HOST>/` and no port of the application container is bound on the host

#### Scenario: Streaming through the proxy
- **WHEN** the owner opens an untranslated chapter through `https://<APP_HOST>`
- **THEN** translated paragraphs appear progressively, not all at once at the end

### Requirement: Stateless hardened container
The application container SHALL run with a read-only root filesystem, all Linux capabilities dropped, privilege escalation disabled, and a non-root user. It SHALL use no persistent volume. Only a size-limited in-memory temporary directory MAY be writable. Removing and recreating the container SHALL lose no data except in-progress translations, which return to "not translated". Exactly one container with one server process SHALL run.

#### Scenario: Large upload on a read-only filesystem
- **WHEN** the owner uploads a 50 MB TXT file to the running container
- **THEN** the upload succeeds

#### Scenario: Container recreated
- **WHEN** the container is removed and started again from the same image
- **THEN** all novels, translations, settings and sessions are still present

### Requirement: Migrate before serving
On startup the container SHALL apply missing database migrations under a database lock before starting the HTTP server. If migration fails, the container SHALL exit with a non-zero code and serve no request. Concurrent starts SHALL apply each migration exactly once. Running a one-off command from the image instead of the server SHALL NOT trigger migrations.

#### Scenario: Failed migration
- **WHEN** a migration fails at startup
- **THEN** the container exits with an error message naming the migration, and no HTTP request is served by that container

#### Scenario: One-off command without a database
- **WHEN** the operator runs `novel hash-password` from the image with no database configured
- **THEN** the command runs and prints the hash without attempting a migration

#### Scenario: Two starts at once
- **WHEN** two processes start the migration step against the same database at the same time
- **THEN** each pending migration is applied once and both finish without error

### Requirement: Health endpoint
The application SHALL expose `GET /api/health` without authentication. It SHALL return HTTP 200 with status `"ok"` when the database is reachable and HTTP 503 with status `"unavailable"` otherwise. The response SHALL include the running version only for a request with a valid session, and SHALL contain no other data. The container health check SHALL use this endpoint. `GET /health` SHALL keep working with the same response. The application SHALL log its version at startup.

#### Scenario: Healthy, anonymous
- **WHEN** an unauthenticated client calls `/api/health` while the database is up
- **THEN** it receives HTTP 200 with `{"status": "ok"}` and no version

#### Scenario: Healthy, logged in
- **WHEN** the logged-in owner calls `/api/health`
- **THEN** the response also contains the running version

#### Scenario: Database unreachable
- **WHEN** the database cannot be reached
- **THEN** `/api/health` returns HTTP 503 and the container is reported unhealthy

### Requirement: Rollback-safe migrations
Database migrations SHALL only add new tables (with any constraints), new nullable or defaulted columns, and new indexes. A migration SHALL NOT drop, rename or truncate anything, change a column type, make a column `NOT NULL`, delete rows, or add a unique, check or foreign key constraint to an existing table. A test SHALL reject any migration file that breaks these rules.

#### Scenario: Forbidden statement
- **WHEN** a new migration file contains `ALTER TABLE novels DROP COLUMN author`
- **THEN** the test suite fails, naming the file and the forbidden statement

#### Scenario: Constraint on an existing table
- **WHEN** a new migration file contains `ALTER TABLE novels ADD CONSTRAINT novels_title_uq UNIQUE (title)`
- **THEN** the test suite fails, naming the file and the forbidden statement

#### Scenario: New table with constraints
- **WHEN** a new migration creates a table with a primary key, a foreign key to `novels` and a `NOT NULL` column
- **THEN** the test suite accepts it

### Requirement: Older release runs on a newer schema
The migration runner SHALL start normally when the database records migrations newer than the ones it knows, applying nothing.

#### Scenario: Older release on a newer schema
- **WHEN** the database has migrations 1 to 4 applied and a release that knows only migrations 1 to 3 starts
- **THEN** it applies nothing, starts normally, and serves requests
