# FGS Page Rendering Profile 1.2

Status: Version 1.2, implemented locally; not yet published.
Profile ID: `fgs-page-1.2`. Extends
[Profile 1.1](FGS_PAGE_RENDERING_PROFILE_1_1.md); accepts FGS 1.0, 1.1, and 1.2.
Margins, fonts, logo/title positioning, footer reserve, row spacing, table
widths, and overflow/export policy are unchanged.

## First column heading

Use the score table's `first_column_heading`, defaulting to **Category** when
absent. Render it in neutral-colored Noto Sans Bold at 8.5 points, left-aligned
with the same 5-point horizontal cell inset as before. Wrap using the shared
font metrics in the first-column width minus 10 points. Let `L` be its wrapped
line count. Table header height is the maximum of 19 points, `L × 10 + 6`
points, and each player's existing wrapped heading height (`lines × 9.5 + 8`).
All header cells share this height. A longer heading can therefore increase
page height and trigger the existing overflow warning; do not clip, shrink,
or independently lay out PDF text. Default Category headers retain their
previous geometry.

## Editorial metadata

`designer_notes` is excluded from all drawing commands and PDF metadata.
Adding or removing it must produce an identical display list and identical
deterministic PDF bytes for the same document version and title.

## Conformance

One display list drives preview SVG and vector PDF in both products. Tests
cover default headings, custom headings, wrapped narrow/paired headings,
header-height/overflow behavior, escaped text, absence of Designer Notes,
and preservation of old geometry. LiveSheet is responsive scoring UI rather
than a page-profile renderer, but uses the same effective first-column label
and never presents Designer Notes.
