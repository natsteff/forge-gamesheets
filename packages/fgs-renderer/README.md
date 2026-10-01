# FGS Renderer

The canonical, browser-and-Node page renderer for FGS GameSheets, maintained as
a source package in Forge GameSheets. It is not a replacement for the FGS
document specification or the
local-review Page Rendering Profile in Forge GameSheets at
`docs/FGS_PAGE_RENDERING_PROFILE_1_3.md` (`fgs-page-1.3.1`).

FGS 1.3 adds bounded resource trackers and generated reusable paper/music
patterns. Shared controls/defaults also live in this package, so both editors
use the same content options, validation and physical-unit conversions.

Both Forge GameSheets and FGS Studio must consume a pinned build from this
source; neither should maintain its own independent print layout rules.

Print jobs may select Full Page, Half Page, Poker Card, Bridge Card, or a bounded
custom finished size. These options are outside the strict `.fgs` schema. One
display list drives the SVG preview and finished-size PDF. A separate imposition
step places unchanged copies on Letter or A4 with optional cut guides and keeps
ordinary-printer output at least 0.5 inch from the page edge; exact
two-up Half Page is available only with an explicit borderless option. The
renderer keeps Full Page's one-page overflow refusal. Compact sheets instead
wrap for their finished width and, when needed, uniformly scale the composition
to one item; the preview reports the resulting scale and approximate body type
size so the designer can judge legibility.

The same point-based display list produces an SVG preview and a vector PDF
with extractable text. Fonts are pinned Noto files under `fonts/OFL.txt`.
The renderer itself and its local distribution are AGPL-3.0-only; bundled
pdf-lib and fontkit remain MIT-licensed dependencies.

From this repository, build and test with:

```sh
pnpm install --frozen-lockfile
pnpm build
pnpm test
```

Then run `node scripts/sync-renderer.mjs` from FGS Studio and
`python3 scripts/sync_fgs_renderer.py` from Forge GameSheets to pin the
generated artifacts in each consumer. Both scripts verify the build manifest
before copying. Do not edit the copied bundles directly. The build manifest
records the profile ID and SHA-256 of each relevant source and distributed artifact; consumers
commit their pinned copies so they can build without rebuilding this package.
Studio must identify the exact Forge source revision that produced its pinned
bundle, so recipients can obtain the corresponding source.

The current font set does not cover every Unicode script. Missing glyphs fail
explicitly; broad Unicode fallback is required before general conformance can
be claimed. No document data is transmitted or saved by the browser renderer.
