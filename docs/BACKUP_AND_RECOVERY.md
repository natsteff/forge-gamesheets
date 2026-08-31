# Backup and recovery

Forge GameSheets separates source content, application state, and source code.
All three should be protected before upgrades or public-release preparation.

## What to back up

### PDF library

The configured `library/` directory contains authoritative source PDFs and any
detected artwork. Forge GameSheets does not store copies of these PDFs in SQLite.

### Application data

The configured `data/` directory contains:

- `forge-gamesheets.db`, including settings, categories, overrides, favorites,
  pins, Recent state, and history
- Uploaded game artwork
- Generated preview and artwork caches

The caches can be regenerated, but the database and uploaded artwork cannot.
Back up the entire directory together.

### Git repository

The Git repository contains source code and development history. Real PDFs and
runtime data are intentionally excluded. Before the first public GitHub push,
the detailed local history will be preserved with a backup branch, annotated
tag, and verified Git bundle outside the repository.

## Safe filesystem backup

1. Stop the application with `Ctrl+C`.
2. Confirm no Forge GameSheets container is writing to `data/`.
3. Copy `library/` and `data/` to a dated backup location.
4. Verify the copied database and uploaded-artwork files exist.
5. Keep at least one copy on a different disk or backup system.

Stopping first ensures the SQLite database and related files are captured as a
consistent set.

## Restore

1. Stop the application.
2. Preserve the current `library/` and `data/` directories until recovery is
   confirmed.
3. Restore both backed-up directories to the paths mounted by Compose.
4. Start the application.
5. Confirm games, settings, categories, and artwork appear.
6. Run a rescan and verify several PDFs.

## Before an application upgrade

1. Verify the current version starts normally.
2. Run the full tests and lint checks.
3. Stop the application and back up `data/`.
4. Build the new image.
5. Start it and allow migrations to complete.
6. Check Settings, categories, one game, and one resource before normal use.

Database migrations are automatic and forward-moving. A backup is the supported
recovery point if an upgrade must be abandoned.

## Public Git history preparation

Do not delete, reset, or rewrite the current development branch. The later
public-release procedure will create independent recovery references and a Git
bundle first, verify them, then build a separate consolidated public branch.
Only that public branch and release tag will be pushed.
