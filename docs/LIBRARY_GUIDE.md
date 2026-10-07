# Using the resource library

FORGE GameSheets indexes files under one first-level folder per game. The
filesystem is authoritative: scans discover files but do not alter the source
files. Library files and the separate writable `data/` directory both need
backups. See [deployment](deployment.md) for setup and
[backup and recovery](BACKUP_AND_RECOVERY.md) for safe copies and restore.

## Organize games and resources

Place each game in its own folder beneath `library/`; files may be nested inside
that folder. A descriptive filename such as `Farkle - Score Sheet.pdf` helps
recognition, but imperfect filenames remain accessible under Other. PDFs
directly in the library root are ignored. Use an ordinary `Unsorted/` game
folder for documents awaiting organization. After adding, moving, or removing
files, select **Rescan library**, or choose an **Auto Rescan Mode** in Settings.
The default is **Disabled (Manual ONLY)**, meaning no automatic scans after
startup. **Automatic local-change detection only** scans when a filesystem
event arrives, with event scans spaced at least 30 seconds apart, but has no
scheduled fallback. Local disks normally report events; some NAS mounts do not.
The 15-minute, 30-minute, 1-hour, 8-hour, and 24-hour options use event detection
plus a scheduled scan when no event arrives.
Scans do not rename or modify source
files. Before applying any index changes, every scan checks for missing entries.
If at least 10% of indexed games or resources appear missing, no changes from
that scan are applied. Check a NAS mount before reviewing and confirming
removals. A manual confirmation rescans and only applies the reviewed missing
set; source files are never deleted by FORGE.
After a scan, the home page shows the same added, updated, and removed game
and resource counts recorded in Activity history.

The home page and **All games** both show the complete alphabetical game list.
With 50 or more games, their letter bar stays visible while scrolling. Select
a letter to jump to its first title, or **#** for titles that begin with a number or symbol. On narrow
screens the bar moves to a horizontally scrollable strip above the games.
**Categories** remains a separate way to browse assigned groups.

You may add a publication-year hint to a game folder, for example
`Falling (1998)/`. A trailing four-digit year in parentheses is used to help
distinguish exact-title BoardGameGeek matches. It is omitted from the default
display title (`Falling`), but the folder name stays unchanged. The hint is
optional; see [Links and BoardGameGeek](#links-and-boardgamegeek) below.

PDFs retain their browser viewing, printing, preview, and Reprint actions.
FGS files default to their own **FGS GameSheets** section, but you can change
an individual resource's category with **Edit**. The game page displays the
Sheet Title read from a valid FGS file alongside its library entry name. When
saved Designer sheets have the same title and FGS content, the game page offers
**Open matching FGS in Sheet Designer** for one match or a choice among multiple
identical saved copies. If none match, it offers **Preview/Open FGS** for a read-only preview;
that page can explicitly import a new editable copy. Opening a matching sheet
does not create a copy, while importing always creates a new saved draft.
Neither action changes the library source. FGS files can also be downloaded.
PNG, JPEG, WebP, and GIF files have browser image previews and view/download
actions. Word, Excel, PowerPoint, OpenDocument, RTF, plain-text, Markdown, and
CSV/TSV files are listed by category but download only.
Unsupported files are named, without action links, in **Other Files Detected**
at the bottom of the game page. Hidden files and folders are skipped. Top-level
`icon.*` and `cover.*` PNG, JPEG, and WebP files are reserved for game artwork;
they are listed there with an explanation, rather than as ordinary images. The
preferred artwork file is still displayed on the game entry. Files named
`icon` or `cover` without a supported extension are listed as unsupported.

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
For automatic matching, a folder named `Falling (1998)` searches BGG for
`Falling` and uses `1998` only to break a tie between exact-title results.
Only a trailing standalone `(YYYY)` is recognized; the folder and displayed
title are separate: the folder remains `Falling (1998)`, while its default
display title is `Falling`. Manually edited display titles are preserved.
This title behavior does not require a BGG token. A year is a hint, not a
required match, because BGG may list the original publication year rather than
a particular edition's year.
Newly discovered games are searched individually, then details for automatic
matches are fetched in groups of up to 20. This applies to initial scans and
later rescans that discover many new folders. A rescan does not re-query
already-known games; use Admin **Refresh all eligible games** for that.
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
