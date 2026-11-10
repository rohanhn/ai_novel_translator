# Spec Delta

## Purpose

Sao lưu hằng ngày database của app trên VPS, mã hoá để chỉ người giữ private key (ngoài VPS) đọc được, giữ số bản cố định và khôi phục được.

## ADDED Requirements

### Requirement: Daily encrypted backup of the app database
The repository SHALL provide a backup script that the operator schedules daily. Each run SHALL dump only the application's own database using the application's database credentials, and SHALL encrypt the dump to a configured `age` public key. Unencrypted dump data SHALL never be written to disk. The script SHALL need neither database superuser rights nor the database container's name.

#### Scenario: Successful run
- **WHEN** the scheduled backup runs
- **THEN** a new encrypted backup file appears in the backup directory, and it can be decrypted only with a configured recipient's private key

#### Scenario: No plaintext on disk
- **WHEN** a backup run is in progress or has finished
- **THEN** no unencrypted dump file exists on the server

### Requirement: Backup file naming and recipients
Each run SHALL produce one file named `<prefix>-<YYYYMMDD-HHMMSS>.dump.age` in UTC and SHALL never overwrite an existing backup. One or more `age` recipients MAY be configured, and each of them SHALL be able to decrypt the backup.

#### Scenario: File name
- **WHEN** a run finishes at 03:15:07 UTC on 2026-11-11
- **THEN** the new file is named `<prefix>-20261111-031507.dump.age`

#### Scenario: Two recipients
- **WHEN** two `age` public keys are configured
- **THEN** the backup can be decrypted with either matching private key

### Requirement: Backup retention
After a successful run, the script SHALL keep the 14 most recent backup files of the application and delete older ones. A failed run SHALL delete nothing and SHALL leave no partial backup file.

#### Scenario: Fifteenth backup
- **WHEN** a run succeeds while 14 backups already exist
- **THEN** 14 backups remain and the oldest one is gone

#### Scenario: Database unreachable
- **WHEN** the database cannot be reached during a run
- **THEN** the script exits with a non-zero code and an error message, no new file remains, and the existing 14 backups are kept

### Requirement: Backup configuration errors
The script SHALL refuse to run, with a message, when the environment file, the database URL or the `age` recipient is missing, or when the `age` tool is not installed.

#### Scenario: Missing recipient
- **WHEN** the script runs without an `age` recipient configured
- **THEN** it exits with a non-zero code and a message naming the missing setting, and dumps nothing

### Requirement: Documented restore
The deployment documentation SHALL describe how to restore a backup into the application's database: decrypting with the private key kept off the server, stopping the application, restoring in a single transaction, and starting the application again.

#### Scenario: Restore drill
- **WHEN** the operator follows the documented restore steps with a backup and the private key
- **THEN** the application's database returns to the state of that backup and the application starts and serves it
