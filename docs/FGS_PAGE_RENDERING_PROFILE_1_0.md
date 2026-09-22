# FGS Page Rendering Profile 1.0

Status: **local release candidate; not yet published**. Profile ID: `fgs-page-1.0`. This is a
versioned appearance contract for
FGS 1.0 documents, separate from the [FGS document specification](FGS_V1_SPECIFICATION.md).
It does not change the meaning or schema of an `.fgs` file. Forge GameSheets
and FGS Studio must use a pinned build of the same renderer to claim this
profile. The source of that build is Forge's `packages/fgs-renderer/` package.

## Page and placement

Measurements are PDF points (1/72 inch), not screen pixels. Letter is 612 ×
792 points and A4 is 595.28 × 841.89 points; landscape exchanges width and
height. Every page has a 36-point content margin. Rows remain in document
order with 14 points between them. A two-block row has two equal-width blocks
separated by 16 points. A row's height is the greater of its blocks' measured
heights. No content may extend below the bottom 36-point margin. A failed fit
must report the first overflowing section; PDF export must fail rather than
clip it or add a page.

## Typography and score tables

The renderer bundles exact font files: Noto Sans Regular for body text, Noto
Sans Bold for table headings and **every category label**, and Noto Serif Bold
for the page and section headings. Measurements and wrapping use those files,
not installed system fonts. Page headings are 20 points, section headings 11
points, and table category labels 8.5 points. A section heading occupies 22
points before its table. The minimum table row height is 19 points. Longer
wrapped labels and headings increase row height; cells must not overlap.

The category column is at least 68 points. For a full-width table it receives
26% of the table width; for a paired table narrower than 350 points with at
most two players it receives 50%. Remaining width is divided equally among
player columns. Empty player names render as `Player N`. Ordinary category
labels use the same bold face in preview and PDF. `Total` and `Grand Total`
rows, matched without case sensitivity after trimming, use a light background
and a small `CALCULATED` marker. Their classification is a *presentation rule*
and does not add saved scores or formulas to FGS.

Table grid strokes are 0.5 points. Section rules are 1.2 points and use
`theme.accent` in both preview and PDF. The main page title and all section
titles also use the accent. If the chosen color has less than 4.5:1 contrast
against white, the renderer scales all three sRGB byte values by the largest
integer factor from 0 to 255 (divided by 255), rounding each channel to the
nearest integer, that yields at least 4.5:1 contrast. The resulting darker
color is used for title text only; rules retain the exact chosen accent. Table
text and grid lines remain neutral. The PDF is vector output with extractable
text; a full-page PNG inside a PDF is not conforming.

## Conformance and versioning

One point-based display list determines both the SVG preview and exported PDF.
Tests must check page size, block bounds, fit decisions, font roles, text
content, and PDF validity on the same synthetic fixtures in both products.
Images rendered at a fixed DPI are reviewed regression evidence, not the
normative standard: PDF viewers may antialias identical geometry differently.

The renderer package creates a manifest with SHA-256 hashes for its bundled
browser, Node, and font artifacts. Each consuming repository pins that build;
the copies must be verified against the manifest. Any change to layout or
appearance requires a new page-rendering-profile ID and reviewed conformance
fixtures.
The profile ID currently appears in PDF producer metadata, not in FGS 1.0
files. Pinning a profile *inside* a portable document requires a future FGS
minor-version change, with an explicit compatibility policy for old files.

The bundled fonts cover broad Latin, Greek, and Cyrillic text. For unsupported
glyphs the renderer reports an error rather than silently substituting a
character. Full Unicode fallback remains necessary before this profile can
claim coverage for every valid FGS text string.
