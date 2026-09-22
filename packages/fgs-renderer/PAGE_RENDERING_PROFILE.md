# FGS Page Rendering Profile 1.0 — local release candidate

This document specifies *appearance* separately from the FGS 1.0 document
schema. FGS 1.0's semantic meaning is unchanged. Forge and FGS Studio may claim
this page rendering profile only when both use the same pinned renderer build and pass
the conformance suite. This profile is not yet a published FGS standard.

All dimensions are PDF points (1/72 inch), not screen pixels. The page is one
Letter (612 × 792 pt) or A4 (595.28 × 841.89 pt) page, transposed for landscape.
Content begins 36 pt from every edge. Rows have 14 pt vertical separation; a
two-block row has two equal widths with a 16 pt gap. Content that crosses the
bottom 36 pt margin must report overflow and must not export a clipped PDF.

The bundled, pinned Noto Sans Regular, Noto Sans Bold, and Noto Serif Bold
fonts are used for body text, table headings/category labels, and section/page
titles respectively. Text wrapping is measured using the bundled font files,
not the operating system's fonts. Category labels are **bold in the preview
and PDF**, including ordinary rows. Text in calculated `Total` and `Grand
Total` rows also has a small `CALCULATED` marker and a light background.
The `theme.accent` value colors section rules and main/section titles in both
preview and PDF. Title text is darkened when necessary to achieve 4.5:1
contrast against white; the rule keeps the exact accent.

The canonical renderer calculates one point-based display list. Its SVG
preview and vector PDF consume that same list. The PDF must contain extractable
text, not a page-wide raster image. Layout bounds, text content, line breaks,
font roles, and fit decisions are normative. Raster pixels are regression
evidence only: viewer antialiasing may differ without changing layout.

Profile changes that alter layout or appearance require a new profile ID and
updated, reviewed conformance fixtures. Until an FGS document version can pin
a profile, applications must expose the renderer/profile revision used for
export and must not silently claim that older PDFs will be pixel-identical.

The bundled fonts cover broad Latin, Greek, and Cyrillic text. Other scripts
require explicit fallback-font support before this profile can claim full
Unicode rendering; exporters must fail clearly rather than substitute missing
glyphs. The FGS document remains Unicode and must not be rewritten to fit a
renderer limitation.
