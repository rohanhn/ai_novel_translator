# Spec Delta

## ADDED Requirements

### Requirement: Edit novel details
The owner SHALL be able to change a novel's title, author and short description after import. Author and description SHALL be optional and absent on a newly imported novel. Only the fields supplied in a request SHALL change. Editing details SHALL NOT change any chapter, translation, glossary or reading progress, and SHALL NOT send any request to an LLM. A TXT export SHALL use the current title.

#### Scenario: Rename and add author
- **WHEN** the owner sets the title of novel 1 to `Kiếm Lai` and its author to `Phong Hỏa Hí Chư Hầu`
- **THEN** the novel shows the new title and author, and its chapters and translations are unchanged

#### Scenario: Partial update
- **WHEN** the owner sends only a new description for a novel that has an author
- **THEN** the description changes and the title and author stay as they were

#### Scenario: Export uses the new title
- **WHEN** the owner renames a novel and then exports it as TXT
- **THEN** the exported file starts with the new title

### Requirement: Novel details validation
After trimming surrounding whitespace, the title SHALL be 1–200 characters, the author at most 100 characters and the description at most 2000 characters. The description SHALL keep its line breaks. An empty or whitespace-only author or description SHALL clear that field. An invalid request SHALL be rejected with a message naming the field and SHALL change nothing.

#### Scenario: Clear the author
- **WHEN** the owner submits an empty author
- **THEN** the novel no longer has an author

#### Scenario: Blank title rejected
- **WHEN** the owner submits a title consisting only of spaces
- **THEN** the request is rejected with a message about the title and nothing changes

#### Scenario: Description too long
- **WHEN** the owner submits a description longer than 2000 characters
- **THEN** the request is rejected with a message about the description and nothing changes

#### Scenario: Line breaks kept
- **WHEN** the owner saves a description of two lines
- **THEN** the stored description still has two lines

### Requirement: Novel cover upload
The owner SHALL be able to upload a cover image for a novel from their device in JPG, PNG or WebP format, up to 10 MB. The format SHALL be checked from the file content by decoding it; any other file SHALL be rejected with a message and the previous cover kept. A new upload SHALL replace the old cover. The owner SHALL be able to remove the cover, after which the generated cover is shown again.

#### Scenario: Not an image
- **WHEN** the owner uploads a text file renamed to `bia.jpg`
- **THEN** the upload is rejected with a message saying the file is not a JPG, PNG or WebP image, and the previous cover (or the lack of one) is unchanged

#### Scenario: File too large
- **WHEN** the owner uploads an 11 MB image
- **THEN** the upload is rejected with a message stating the 10 MB limit

#### Scenario: Remove the cover
- **WHEN** the owner removes the cover of a novel
- **THEN** the novel has no cover and fetching the cover returns "not found"

### Requirement: Cover image from a link
The owner SHALL be able to provide an http or https link to an image on the internet, at most 2000 characters long. The system SHALL download it, check and process it exactly like an uploaded file, and return the processed image for preview without storing anything. The cover SHALL change only when the owner then saves that image. Downloads SHALL be limited to 10 MB, 15 seconds and 3 redirects. Each failure SHALL be reported in plain language.

#### Scenario: Valid image link
- **WHEN** the owner submits a link to a public 1200×1800 JPG
- **THEN** the system returns a processed preview no larger than 600×900, and the novel's cover is unchanged until the owner saves it

#### Scenario: Link is not an image
- **WHEN** the owner submits a link to an HTML page
- **THEN** the request is rejected with a message saying the link does not point to a JPG, PNG or WebP image

#### Scenario: Unreachable link
- **WHEN** the link's server returns 404, refuses the connection, or does not answer within 15 seconds
- **THEN** the request is rejected with a message saying the image could not be downloaded

#### Scenario: Image too large at the link
- **WHEN** the image at the link is larger than 10 MB
- **THEN** the download stops at 10 MB and the request is rejected with a message stating the limit

#### Scenario: Invalid link
- **WHEN** the owner submits `ftp://example.com/a.jpg` or text that is not a link
- **THEN** the request is rejected with a message saying only http or https links are accepted, and no network request is made

### Requirement: Link fetch safety
Link downloads SHALL only connect to public internet addresses on port 80 or 443. Loopback, private, link-local (including cloud metadata), multicast and reserved addresses, in IPv4 and IPv6, SHALL be refused. The check SHALL apply to every redirect and to the address actually connected to, so a name resolving to an internal address is refused. Downloads SHALL send no cookie, session or credential and use no proxy from the environment. Each request SHALL be made once, without automatic retry.

#### Scenario: Internal address refused
- **WHEN** the owner submits `http://127.0.0.1:8000/api/novels` or `http://169.254.169.254/latest/meta-data/`
- **THEN** the request is rejected with a message saying the address is not allowed, and no connection is made to it

#### Scenario: Redirect to an internal address
- **WHEN** a public link redirects to `http://10.0.0.5/image.png`
- **THEN** the redirect is not followed and the request is rejected

#### Scenario: Name resolving to an internal address
- **WHEN** the owner submits a link whose host name resolves to `192.168.1.10`
- **THEN** the request is rejected and no connection is made to that address

#### Scenario: Internal address hidden inside IPv6
- **WHEN** the owner submits a link whose host resolves to `64:ff9b::7f00:1` or `::ffff:127.0.0.1`
- **THEN** the request is rejected because the embedded IPv4 address is internal

#### Scenario: Owner session not forwarded
- **WHEN** the system downloads an image from a link
- **THEN** the outgoing request carries no cookie or authorization header from the owner's session

### Requirement: Cover image processing
A stored cover SHALL be scaled down, keeping its aspect ratio, to fit within 600×900 pixels; smaller images SHALL NOT be enlarged. The stored cover SHALL follow the photo's orientation and SHALL NOT keep embedded metadata such as EXIF or GPS. Images whose pixel count exceeds a safe decoding limit SHALL be rejected.

#### Scenario: Upload a large photo
- **WHEN** the owner uploads a 3000×4000 phone JPG with rotation and GPS metadata
- **THEN** the stored cover fits within 600×900 with the same aspect ratio, is upright, and has no GPS metadata

#### Scenario: Small image is not enlarged
- **WHEN** the owner uploads a 300×450 PNG as a cover
- **THEN** the stored cover is 300×450

### Requirement: Cover image access
Novel data returned to clients SHALL include a cover address. It SHALL be empty when there is no cover, and SHALL change whenever the cover is replaced so that a cached old image is never shown. The image SHALL be served only to an authenticated session, SHALL carry the no-indexing marker, and SHALL be cacheable only privately. Deleting a novel SHALL delete its cover.

#### Scenario: Replace changes the address
- **WHEN** the owner uploads a second cover for a novel that already has one
- **THEN** the novel's cover address differs from the previous one and fetching it returns the new image

#### Scenario: Cover requires login
- **WHEN** a client without a valid session requests a novel's cover image
- **THEN** the request is rejected as unauthenticated and no image data is returned

#### Scenario: Deleting the novel deletes the cover
- **WHEN** the owner deletes a novel that has a cover
- **THEN** the cover image is removed together with the novel
