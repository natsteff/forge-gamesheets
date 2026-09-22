# FGS Renderer

The canonical, browser-and-Node page renderer for FGS GameSheets, maintained as
a source package in Forge GameSheets. It is not a replacement for the FGS
document specification or the
local release candidate Page Rendering Profile in Forge GameSheets at
`docs/FGS_PAGE_RENDERING_PROFILE_1_0.md`.

Both Forge GameSheets and FGS Studio must consume a pinned build from this
source; neither should maintain its own independent print layout rules.

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
records the profile ID and SHA-256 of each distributed artifact; consumers
commit their pinned copies so they can build without rebuilding this package.
Studio must identify the exact Forge source revision that produced its pinned
bundle, so recipients can obtain the corresponding source.

The current font set does not cover every Unicode script. Missing glyphs fail
explicitly; broad Unicode fallback is required before general conformance can
be claimed. No document data is transmitted or saved by the browser renderer.
