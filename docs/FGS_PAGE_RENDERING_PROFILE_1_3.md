# FGS Page Rendering Profile 1.3.1

Status: Implemented and owner-reviewed. Publication is verified separately.
Profile ID: `fgs-page-1.3.1`. Extends [Profile 1.2](FGS_PAGE_RENDERING_PROFILE_1_2.md)
and accepts FGS 1.0–1.3. Fonts, 36-point margins,
16-point column gap, 14-point row gap, logo/title placement and optional
footer reserve remain unchanged for one-line footers. No automatic pagination is introduced.

The 1.3.1 adjustment moves the final full-page footer baseline from 26 to
42 points above the lower edge. The reserve above a two-line footer increases
from 22 to 33 points so dense content cannot overlap it. Page dimensions,
upper and side margins, row spacing, and compact-size geometry are unchanged.
Dense sheets that no longer fit report overflow rather than shrinking.

## Score-table column widths (beta adjustment)

Each column's preferred width is the font-measured heading plus 10 points of
cell padding; the first column also considers its row labels. A long heading's
preferred width is capped at 40% of the table to prevent it monopolizing the
page. Table width is divided in proportion to these preferences, with a small
28-point floor to avoid unusable slivers. When even that cannot fit, all
columns share the available width evenly. Short numeric headings can therefore
produce genuinely narrow columns, including in paired tables.
Headings and labels wrap within their resulting cells, increasing row height
where needed. The same geometry drives preview and PDF; overflowing tables
produce a fit warning rather than clipped output.

Footer input is not cut off at 160 characters. A 4,000-character import-safety
ceiling remains, but actual printability is checked against the selected
finished size. An overwide full-page footer reports a fit warning and blocks
PDF export without discarding the entered text.

## Shared geometry

One point-based display list drives SVG preview and selectable-text/vector PDF
in both products. New primitives are lines and filled circles, not raster paper
images. Pattern strokes are neutral gray `#808080`, 0.5 points wide; dots have
0.75-point radius. Existing accent rules apply to section titles, not writing marks.
A nonempty new section title reserves 27 points above its body. An empty paper
title reserves none. Physical dimensions assume actual-size/100% printing;
browser zoom affects display only, and printer fit-to-page scaling changes spacing.
Reject drawings beyond the 20,000-command budget rather than hang or truncate.

## Trackers

Checkbox/numbered spaces occupy an 18-point square with four-point gaps.
Columns are `floor((width + 4) / 22)`; wrap complete spaces into rows. Outlines
are inset 0.25 points. Number labels use eight-point sans text. Segmented bars
are 18 points high across the available width; segments narrower than six
points fail with guidance to use another appearance. Current/maximum uses a
54-point writing underline and 12-point sans maximum label. Optional `Start: N`
guidance adds 16 points below the body, in 8.5-point text.
Printable spaces remain blank regardless of starting guidance or session state.

## Patterns

Fixed heights exclude title space. Music group height is four line spacings
for a single staff; paired staves use eight spacings plus the gap between
the bottom line of the first staff and top line of the second. Tablature uses
`(strings - 1) × line_spacing_pt`. Fixed-count body height is
`count × groupHeight + (count - 1) × group_gap_pt + 0.5` points.
The group gap is between the last line of one group and first line of the next.
Fill mode allocates all remaining printable height but draws only complete groups;
it must accommodate at least one group including its stroke allowance.

Music and tablature lines start 0.25 points below the body top. Tablature label
gutter is the widest label measured in eight-point sans plus eight points;
at least 36 points of writing width must remain. Lines retain full width when
labels are absent. There are no partial staff groups at the bottom.

Ruled lines start one spacing below the body top. Square grids start 0.25
points inside the top/left boundaries. Dot rows/columns start one spacing in;
only complete circles are drawn. Optional ruled margin guides must leave at
least 36 points of writing width. Hexagons are complete flat-top cells:
horizontal center step 1.5 times side length, vertical step `sqrt(3)` times
side length, alternate columns offset half the vertical step. Shared edges are
drawn once; outlines are inset for their stroke width. Partial cells are omitted.

Fail clearly when dimensions cannot fit a complete usable pattern or when a
fixed section overflows. Do not shrink spacing, clip content, or export only
the visible portion. LiveSheet uses responsive host controls for trackers and
static SVG crops for paper sections, not page-anchored scoring overlays.

## Coordinate grids and blank boards

Coordinate grids reserve a minimum 12-point inset on each edge and require at least one
grid step inside it. Centered axes use the center of the body; bottom-left uses
the lower-left inset. Grid lines are aligned to that origin at `spacing_pt`.
The inset grows for wide numeric labels: estimate the longest positive/negative
label at `ceil(max(body width, body height) / spacing_pt) * units_per_step` in
seven-point sans. Reserve half its width plus two points for centered axes, or
its full width plus four points for bottom-left axes, with a 12-point minimum.
This gutter is additional to the normal document margins; cell spacing remains
exact and square, and incomplete edge cells are omitted.
Axes and arrowheads are dark, one-point strokes. Number labels use seven-point
sans text; axis titles use eight-point sans. Numeric tick interval is the greater
of `label_every` and `ceil((widest endpoint label + 4) / spacing_pt)`. Zero is
printed once. Labels do not alter scale or physical grid spacing.

Board geometry reserves three points for strokes/dots. A single board is horizontally
centered at the top of the body. Repeated boards use as many complete columns/rows
as fit with the requested gap; the group of columns is horizontally centered.
The longest side is `board_size_pt`; Dots and Boxes spacing is that length divided
by `max(dot_rows - 1, dot_columns - 1)`. Dots have 1.5-point radius. Tic-tac-toe
has four internal one-point lines, no outer border. Sudoku has 20 grid lines:
outer and every third boundary are 1.5 points, other boundaries 0.5 points.
All boards are dark `#242424`, not accent-colored. Unused space is left blank;
boards are never stretched to fill it. The existing command limit still applies.
