# Phase 1 beta testing guide

Thank you for testing Forge GameSheets. The goal is to learn whether an ordinary
collection of board-game PDFs can be organized and used without requiring every
filename to be cleaned up first.

Use copies of PDFs for beta testing. Forge GameSheets mounts the library as
read-only and should not modify source files, but a separate test collection
makes verification and cleanup easier.

## Before testing

Record:

- Operating system and version
- Docker and Docker Compose versions
- Browser and version
- Approximate number of games and PDFs
- Whether the collection contains unusually large, scanned, or malformed PDFs

Start the application with:

```sh
docker compose up --build
```

Open <http://localhost:8000> and confirm `/health` reports an `ok` status.

## Test 1 — initial discovery

1. Add at least five first-level game folders.
2. Include both well-named and imperfectly named PDFs.
3. Include a nested PDF beneath one game folder.
4. Start Forge GameSheets or select **Rescan library**.
5. Confirm every game appears in All Games.
6. Confirm every PDF remains accessible, even when classified as Other.

Note missing games, unexpected titles, incorrect document types, and files that
are silently omitted.

## Test 2 — finding and using resources

1. Search for a game title.
2. Search for a resource title or variant.
3. Open several PDFs with View.
4. Download at least one PDF.
5. Print one PDF through the browser's PDF viewer or print command.
6. Confirm Recent and History reflect successful views and downloads.

Browser printing itself is not recorded because browsers do not reliably report
whether a print completed.

## Test 3 — previews and unavailable files

1. Show and hide PDF previews on a game page.
2. Check portrait, landscape, scanned, and multi-page PDFs.
3. Temporarily move a test PDF out of the library after a scan.
4. Confirm the resource is marked unavailable rather than breaking the page.
5. Restore it and rescan.

Report PDFs that open correctly but cannot generate a preview. Include the PDF's
general origin and characteristics, but do not share copyrighted files unless
you have permission.

## Test 4 — metadata and artwork

1. Edit a game display title without renaming its folder.
2. Edit a resource title, document type, and variant.
3. Upload game artwork and then remove it.
4. Restart the application and rescan.
5. Confirm overrides and uploaded artwork persist.

## Test 5 — categories and shortcuts

1. Assign several categories to one game.
2. Create, rename, and delete a category in Settings.
3. Confirm category deletion never deletes a game or PDF.
4. Confirm a game with no categories appears under Uncategorized.
5. Favorite resources and pin up to ten homepage resources.
6. Confirm an eleventh pin is rejected with a useful explanation.

## Test 6 — Settings and restart persistence

1. Customize the library footer.
2. Change the Recent limit between 0 and 15.
3. Confirm 0 hides Recent while History continues recording activity.
4. Stop and restart the application.
5. Confirm settings, categories, favorites, pins, metadata, and history persist.

## Test 7 — responsive and keyboard use

1. Resize the browser to phone, tablet, and desktop widths.
2. Navigate primary pages using only Tab, Shift+Tab, Enter, and Space.
3. Confirm focused controls remain visible.
4. Confirm long game, category, and resource names do not overlap controls.

## Reporting a problem

Include:

- What you expected
- What happened instead
- Exact steps that reproduce it
- Page address where it happened
- Browser, operating system, and Docker versions
- Relevant application log lines
- A screenshot when it helps explain layout or state
- Whether the problem persists after a rescan or restart

Do not include private PDFs, passwords, tokens, or the SQLite database in a
public report. Describe filenames and folder structure with sanitized examples.

## Beta success questions

- Could you find the sheet needed during a game without browsing the filesystem?
- Were imperfect filenames manageable without renaming source files?
- Did categories and pinned resources reduce the time needed to find documents?
- Was any action or label confusing?
- What would prevent you from continuing to use the application?
