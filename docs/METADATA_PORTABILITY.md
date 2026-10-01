# Metadata portability

The Admin-only **Metadata portability** utility creates a portable copy of game
links, optional box dimensions, manual BGG edition references and app-managed uploaded artwork without changing the read-only PDF
library. It is intended for migration, recovery, and initial link discovery. It
is not a replacement for backing up the complete FORGE GameSheets data directory.

## Export game metadata

The downloaded `forge-metadata-export.zip` contains:

- `forge-metadata-manifest.json`, which records each game folder, official and
  alternate link description and URL, BoardGameGeek association, and uploaded
  artwork relationship, plus manually supplied box dimensions and BGG edition references when known
- Windows `.url` shortcuts for each exported link
- macOS `.webloc` shortcuts for each exported link
- Artwork uploaded through FORGE GameSheets and stored in application data

Detected artwork already stored beside PDFs in the library is not duplicated.
FORGE GameSheets streams the ZIP to the browser and does not retain it after download.

The export deliberately excludes PDFs, detected library artwork, generated
previews and FORGE GameSheets Reprints, Sheet Designer drafts, categories, display-title
overrides, favorites, pins, history, settings, accounts, and sessions. Preserve
those items with the normal library and complete `/data` backup procedure.

## Import a FORGE GameSheets metadata export

Importing a FORGE GameSheets ZIP is the recommended restore method because its manifest
preserves link descriptions and artwork relationships. A manifest-only JSON file
can restore links and dimensions but cannot carry the artwork files referenced by a full ZIP.

FORGE GameSheets matches each record to the first-level source game-directory name. A
record whose directory is not present in the current scanned library is skipped.
The review page makes no changes. It reports additions, replacements, unchanged
records, and skipped or unmatched records before offering final confirmation.

Choose one policy:

- **Fill empty fields** adds missing links, dimensions and artwork while preserving existing
  values.
- **Replace recognized fields** replaces only links, dimensions or artwork represented in
  the import. It does not clear fields absent from the import.

## Box dimensions and manifest compatibility

The metadata manifest now uses version **1.1** (not an FGS format version).
FORGE GameSheets still accepts legacy 1.0 manifests, which leave existing dimensions alone.
Older FORGE GameSheets readers may reject a 1.1 export; use a current reader to restore it.
Normal library/application-data backups retain measurements in the database.
Migration 31 adds an empty, optional `game_box_dimensions` table without changing
or populating existing game records.

The optional `games` list contains records such as:

```json
{
  "game_directory": "Example",
  "box_dimensions": {"length": 11.6, "width": 8.7, "depth": 2.8, "unit": "in"}
}
```

This is a record fragment, not a complete manifest. Measurements must be positive
finite numbers; all three and unit (`in` or `cm`) are required together. No unit
conversion or dimension sorting occurs. Duplicate game records, extra properties,
invalid values and partial measurement objects are rejected before applying imports.
Each measurement object is one recognized field for preview counts/import policy.
Exports include only known dimensions. Missing records never erase existing values;
an explicit `box_dimensions: null` clears a known value only under **Replace
recognized fields**. It leaves it untouched under **Fill empty fields**.
Shortcut scans cannot recover dimensions. No BGG dimension retrieval, FGS file
changes or page-layout behavior is involved.

## BGG edition references

Version 1.1 also accepts optional `bgg_edition` in each `games` record:

```json
{
  "game_directory": "Example",
  "bgg_edition": {"version_id": 187468, "label": "English edition", "parent_bgg_id": 822}
}
```

The edition and dimensions are independent recognized fields. A record can contain
either or both; omission never clears a value. `bgg_edition: null` clears only under
**Replace recognized fields**; **Fill empty fields** preserves existing editions.
Legacy 1.0 manifests leave editions unchanged. Positive numeric version IDs are
required; labels are optional (at most 160 characters). The optional parent game ID
records the association at selection time, not proof that the edition belongs to it.
After import, a different current association prompts a review in the editor.
Migration 32 creates empty optional edition storage. No API requests, scraping,
verification or dimension updates occur. Shortcut scans cannot recover editions;
use the JSON/ZIP manifest or a full data backup.

## Scan library shortcut files

Folder-based link discovery searches beneath each game folder for recognized
Windows `.url` and macOS `.webloc` shortcuts. This is useful for initially
loading shortcuts collected outside FORGE GameSheets, or as an alternative recovery method
when the metadata manifest is unavailable.

FORGE GameSheets recognizes shortcuts named for **Official resource**, **Alternate
resource**, or **BoardGameGeek**. It discovers the URL stored in each file but
cannot discover custom descriptions or uploaded artwork from shortcuts alone.
The library remains read-only: scanning never moves, edits, or deletes shortcut
files or PDFs.

## Safety and backups

Preview every import before confirmation. Keep the exported ZIP outside the live
FORGE GameSheets data directory, protect it like other library metadata, and retain a full
backup of both configured persistent directories. See
[Backup and recovery](BACKUP_AND_RECOVERY.md).
