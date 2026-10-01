# Using the PDF library

FORGE GameSheets indexes PDFs under one first-level folder per game. The
filesystem is authoritative: scans discover files but do not alter the source
PDFs. Library files and the separate writable `data/` directory both need
backups. See [deployment](deployment.md) for setup and
[backup and recovery](BACKUP_AND_RECOVERY.md) for safe copies and restore.

## Organize games and resources

Place each game in its own folder beneath `library/`; PDFs may be nested inside
that folder. A descriptive filename such as `Farkle - Score Sheet.pdf` helps
recognition, but imperfect filenames remain accessible under Other. PDFs
directly in the library root are ignored. Use an ordinary `Unsorted/` game
folder for documents awaiting organization. After adding, moving, or removing
files, select **Rescan library**. Scans do not rename or modify source files.

Put optional `icon.webp` or `cover.webp` (PNG and JPEG also work) at the top of
a game folder, or upload permitted artwork through **Edit game entry**. Web
uploads are stored in application data and override detected folder artwork
without changing the source folder. See [backup and recovery](BACKUP_AND_RECOVERY.md).

Use **Games → Assign game categories** to edit multiple games with a review
step. Optional folder-name hints such as `Yahtzee [Dice, Children]` can be
enabled for newly discovered games; existing games require an explicit preview
and application. See [game categories](GAME_CATEGORIES.md).

## Links and BoardGameGeek

Each game can have official and alternate resource links. FORGE GameSheets
stores the URLs but does not fetch their files. The separate global **Links**
directory offers Personal Favorites and shared FGS Favorites; Admins maintain
its starter records. See [Links behavior](LINKS.md).

BoardGameGeek associations can be entered manually without an API token.
Optional API enrichment requires an operator-supplied, BGG-approved token.
Physical edition references and box dimensions are separate optional game
metadata; neither changes an FGS sheet's layout. See
[manual BGG links](BGG_MANUAL_LINKS.md) and [BGG API setup](BGG_API.md).

## View, print, and Reprint

Open original PDFs in the browser or download them without modification. A
FORGE GameSheets Reprint is an optional derived copy with a QR return link and
source-rights notice. Admins can use **FORGE GameSheets Reprints** to review
the inventory and explicitly create missing, refresh existing, or rebuild all
eligible copies. The maintenance job confirms changes, reports progress and
skips, and never edits source PDFs. Rescan after changing source files before
running maintenance. See the [Reprint decision record](decisions/005-bulk-forge-reprint-maintenance.md)
for the full behavior and recovery boundary.

Source rights remain with the rights holder. FORGE GameSheets does not provide
or authorize redistribution of an operator's PDFs. A QR link can make a
resource reachable according to the installation's access settings; printed
copies and downloaded files cannot be recalled.

## Move metadata or back up

Admins can export game links, box dimensions, and uploaded artwork in a
versioned ZIP and preview an import before applying it. Library `.url` and
`.webloc` shortcuts offer a narrower URL-recovery route. Neither replaces a
complete backup of `library/` and `data/`. See
[metadata portability](METADATA_PORTABILITY.md) and
[backup and recovery](BACKUP_AND_RECOVERY.md).
