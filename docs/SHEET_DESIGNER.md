# Sheet Designer and LiveSheets

Sheet Designer creates structured GameSheets from scratch. It does not open or
edit an existing PDF. The integrated Designer is available to Admins and
Contributors; [FGS Studio](https://natsteff.github.io/FGS-Studio/) provides a
browser-only Designer without installing the full FORGE GameSheets application.

## Start and edit a sheet

Choose **New sheet**, **Open sheets** (including FGS import), or **Resume last
sheet** on the Designer startup screen. In the editor, add or reorder headers,
score tables, references, checklists, notes, trackers, and paper patterns.
Sections can be duplicated, deleted, made full-width, or paired side by side.
Score rows and checklist items are editable; the numbered-row tool can generate
many score rows at once. A score row named **Total** or **Grand Total** becomes
a calculated LiveSheet row.

The printable preview updates as you edit. Click a heading, table label, or
list item on the preview to select its section and focus the source field. A
score-row label focuses the corresponding line in **Score rows**. This is
navigation to the editor, not direct editing on the printed sheet.

Trackers, introduced in FGS 1.3 and supported in 1.4, include checkboxes,
numbered boxes, segmented bars, and current/maximum values. Paper patterns
include ruled, square, dot, hex, music, tablature, coordinate, and blank
game-board layouts. Paper is printable
content, not a digital ink canvas. See [FGS format and version
history](FGS_FORMAT.md) for the formal content and rendering rules.

## Finished size and PDF output

Choose Full Page, Half Page, Poker Card, Bridge Card, or an explicit custom
size before designing for a smaller format. The preview and PDF use the same
finished-size composition. Smaller designs wrap at the selected width and then
fit uniformly if needed; the preview reports the fit percentage and approximate
body-text size so you can judge readability. Full Page retains its existing
single-page overflow behavior. Automatic pagination is not yet supported.

**Export PDF** creates one page at the finished size. **Create print sheet**
places copies on Letter or A4 with optional cut guides. For ordinary printers,
use the print-sheet workflow for smaller sizes and print at actual size (100%),
with the displayed orientation and Fit to page off. Borderless two-up Half Page
requires a matching printer and paper. See the
[finished-size printing guide](PRINT_SIZE_PRINTING.md) before cutting or
printing card-sized sheets.

FGS 1.4 stores optional finished-size defaults and remembers print-sheet
settings only after successful export. Both remain editable after reopening;
older FGS files still open with Full Page. Designer
Notes travel with an exported FGS file but never appear on the printed sheet,
PDF, or LiveSheet. A one- or two-line Footer and one header logo can be part of
the portable FGS source. New integrated-Designer sheets start with an editable
footer pointing to the local FORGE GameSheets server; existing or imported
sheets retain their own footer.

## Save, share, and associate

The integrated Designer autosaves drafts under `data/sheet-designer/`. They are
a shared installation-wide workspace, not private per-user files. Back up
`data/`, and periodically **Export .fgs** for an independent editable copy,
especially before major changes. Import creates a separate saved draft; it
does not replace the previously open sheet. **Export PDF** does not add the
result to the indexed PDF library automatically. To manage an exported PDF as
a game resource, place it in a game folder and rescan.

A saved GameSheet can be associated with an existing library game. The game
page then presents it alongside its other resources and offers a LiveSheet
action when eligible. Association is local metadata; it does not change the
game folder or embed a local game ID in the portable FGS file. The association
dialog may suggest an exact title match, but it saves nothing until confirmed.

## Temporary LiveSheets

Mark a compatible score sheet **LiveSheet ready** in the integrated Designer.
The full application can then start a temporary single-scorer or
individual-scoring session from its latest saved design. Invited players use
a QR code or link; in individual mode they claim one player position and edit
only their own scores. In single-scorer mode, the host enters scores and
players can follow along. Changes refresh across devices. The session has an
independent snapshot: Designer edits do not disrupt an active game, and scores
and player names are never written back to the FGS source.

The [screenshot gallery](SCREENSHOT_GALLERY.md) includes an active LiveSheet
from a disposable invented demo. Its invitation and QR display are placeholders,
not working sharing credentials.

## Scope and Designer-only mode

FGS is intended for portable score tracking, references, checklists, and
structured printable aids. It is not a free-positioning page editor or
spreadsheet: general image sections, custom formulas, multi-page output, and
pixel-perfect recreation of arbitrary PDFs are not supported.

The published image can also run only the Designer with
`FORGE_GAMESHEETS_MODE=designer`. That mode uses the same `/data` mount for
saved drafts but does not initialize the library, accounts, or LiveSheets.
Because it has no account system, retain a localhost bind unless another
trusted access-control layer protects it. The normal full-application default
remains unchanged. For a browser-only alternative with no container install,
use FGS Studio.
