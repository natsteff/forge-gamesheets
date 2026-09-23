# FGS Page Rendering Profile 1.1

Status: Version 1.1. Profile ID: `fgs-page-1.1`. This
extends [Page Rendering Profile 1.0](FGS_PAGE_RENDERING_PROFILE_1_0.md) and
accepts both FGS 1.0 and 1.1. Every 1.0 document without a footer or logo
keeps its 1.0 geometry. All units below are PDF points (1/72 inch).

## Header logo

The optional header logo fits without cropping into a 48 × 32 point box at the
left of its header block. The image preserves its aspect ratio and is centered
in that box. The title and optional subtitle are centered on the full header
block, independently of the logo. An 8-point gap separates the logo box from
the nearest possible text; text that cannot fit without overlapping the logo
is rejected rather than shifted off center. The ordinary header height stays
40 points without a subtitle or 54 points with one. A paired header uses its
own block width; the logo never escapes into the adjacent block.

## Author footer

A present footer reserves 22 additional points below all content rows. Their
bottom fit boundary is page height minus the usual 36-point margin and this
reserve. One or two lines are centered horizontally in Noto Sans Regular at
8 points, with 11-point baseline spacing. The final baseline is 26 points
above the page bottom. Footer text that exceeds the page content width is an
error; it is not silently clipped or shrunk. An absent footer reserves no
space. A sheet that no longer fits with its footer must report overflow and
must not export a clipped PDF.

## Conformance

The same point-based display list must drive SVG preview and vector PDF
output in Forge and Studio. The renderer must emit an image command with the
same box in both outputs and keep footer text selectable in the PDF. Tests
cover old 1.0 geometry, a logo with different aspect ratios, footer fit,
page dimensions, and PDF validity. A future geometry change requires another
profile ID; packaging changes alone do not.
