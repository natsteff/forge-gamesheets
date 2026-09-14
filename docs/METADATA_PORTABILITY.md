# Metadata portability

The Admin-only **Metadata portability** utility creates a portable copy of game
links and app-managed uploaded artwork without changing the read-only PDF
library. It is intended for migration, recovery, and initial link discovery. It
is not a replacement for backing up the complete Forge data directory.

## Export game metadata

The downloaded `forge-metadata-export.zip` contains:

- `forge-metadata-manifest.json`, which records each game folder, official and
  alternate link description and URL, BoardGameGeek association, and uploaded
  artwork relationship
- Windows `.url` shortcuts for each exported link
- macOS `.webloc` shortcuts for each exported link
- Artwork uploaded through Forge and stored in application data

Detected artwork already stored beside PDFs in the library is not duplicated.
Forge streams the ZIP to the browser and does not retain it after download.

The export deliberately excludes PDFs, detected library artwork, generated
previews and FORGE Reprints, Sheet Designer drafts, categories, display-title
overrides, favorites, pins, history, settings, accounts, and sessions. Preserve
those items with the normal library and complete `/data` backup procedure.

## Import a Forge metadata export

Importing a Forge ZIP is the recommended restore method because its manifest
preserves link descriptions and artwork relationships. A manifest-only JSON file
can restore links but cannot carry the artwork files referenced by a full ZIP.

Forge matches each record to the first-level source game-directory name. A
record whose directory is not present in the current scanned library is skipped.
The review page makes no changes. It reports additions, replacements, unchanged
records, and skipped or unmatched records before offering final confirmation.

Choose one policy:

- **Fill empty fields** adds missing links and artwork while preserving existing
  values.
- **Replace recognized fields** replaces only links or artwork represented in
  the import. It does not clear fields absent from the import.

## Scan library shortcut files

Folder-based link discovery searches beneath each game folder for recognized
Windows `.url` and macOS `.webloc` shortcuts. This is useful for initially
loading shortcuts collected outside Forge, or as an alternative recovery method
when the metadata manifest is unavailable.

Forge recognizes shortcuts named for **Official resource**, **Alternate
resource**, or **BoardGameGeek**. It discovers the URL stored in each file but
cannot discover custom descriptions or uploaded artwork from shortcuts alone.
The library remains read-only: scanning never moves, edits, or deletes shortcut
files or PDFs.

## Safety and backups

Preview every import before confirmation. Keep the exported ZIP outside the live
Forge data directory, protect it like other library metadata, and retain a full
backup of both configured persistent directories. See
[Backup and recovery](BACKUP_AND_RECOVERY.md).
