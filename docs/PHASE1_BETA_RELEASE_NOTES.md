# Forge GameSheets Phase 1 beta

Forge GameSheets is a self-hosted browser library for printable board-game
resources. This first beta focuses on organizing and using existing PDFs while
keeping files portable, private, and under the owner's control.

## Included in this beta

### Filesystem library

- Treats ordinary first-level folders as games
- Discovers PDFs recursively without requiring metadata files
- Accepts imperfect filenames and keeps unrecognized documents accessible
- Uses the filesystem as the source of truth and mounts it read-only
- Rescans on demand and handles partial scans without discarding the last good
  index

### Browse and search

- Provides category cards, All Games, and Uncategorized views
- Supports multiple customizable categories per game
- Searches game titles and resource titles
- Groups resources into rules, score sheets, player references, answer sheets,
  tournament materials, setup documents, and Other

### PDF workflow

- Opens PDFs in the browser for viewing and browser-managed printing
- Downloads original PDFs without modifying them
- Generates cached first-page previews with a hide/show preference
- Marks missing resources unavailable and handles preview failures gracefully

### Personal organization

- Edits game and resource display metadata without renaming source files
- Detects game cover artwork and supports validated artwork uploads
- Saves favorites and up to ten pinned homepage resources
- Tracks configurable Recent resources and view/download history
- Allows category creation, renaming, and safe deletion

### Settings and persistence

- Customizes or hides the library footer
- Configures the Recent list from 0 to 15 items
- Persists settings, categories, overrides, artwork, shortcuts, and activity in
  SQLite
- Applies versioned database upgrades automatically

### Reliability and access

- Uses guarded filesystem path resolution and rejects symbolic-link escapes
- Provides responsive desktop, tablet, and phone layouts
- Includes keyboard landmarks, visible focus behavior, and a skip link
- Runs through Docker Compose with a local-only default port binding
- Includes automated scanner, parser, database, reconciliation, file-safety,
  preview, web, and restart workflow tests

## Known limitations

- Browser printing cannot be reliably recorded as a completed print action.
- Previews show the first PDF page only.
- Phase 1 does not edit, combine, stamp, or generate PDFs.
- Authentication and public network deployment are not included.
- BoardGameGeek enrichment, cloud synchronization, and remote backup are not
  included.

## Beta feedback requested

Testers are especially encouraged to report discovery problems with real-world
folder structures, filename classification errors, PDFs that open but cannot be
previewed, confusing organization workflows, responsive layout problems, and
state that does not survive a restart or rescan.

See `docs/BETA_TESTING.md` for the complete test workflow and safe reporting
guidance.
