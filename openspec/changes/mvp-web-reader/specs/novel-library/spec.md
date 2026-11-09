# Spec Delta

## ADDED Requirements

### Requirement: Upload novel from the web
The owner SHALL be able to upload a `.txt` file from the web library, optionally giving a title (defaulting to the file name); the file SHALL be imported with the same chapter-splitting and encoding rules as TXT import. Files larger than 50 MB SHALL be rejected.

#### Scenario: Upload from phone
- **WHEN** the owner uploads `phamnhan.txt` without a title
- **THEN** a novel titled `phamnhan` appears in the library with its chapters, all pending

#### Scenario: Oversized file
- **WHEN** the owner uploads a 60 MB file
- **THEN** the upload is rejected with a size error and no novel is created

### Requirement: Delete novel and all its data
The owner SHALL be able to delete a novel after confirmation; deletion SHALL permanently remove its source text, translations, glossary, suggestions, and reading progress, and cancel any pending prefetch for it.

#### Scenario: Delete
- **WHEN** the owner deletes novel 2 and confirms
- **THEN** novel 2 and all its chapters, glossary entries, suggestions, and progress no longer exist

#### Scenario: Unconfirmed delete
- **WHEN** a delete request is made without confirmation
- **THEN** nothing is deleted

### Requirement: Library overview
The library SHALL list each novel with its title, number of chapters, number translated, and last-read chapter, ordered by most recently read.

#### Scenario: Recently read first
- **WHEN** the owner read novel 3 after novel 1
- **THEN** novel 3 is listed before novel 1
