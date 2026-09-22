# Decision 007: shared FGS print renderer

Status: locally implemented for verification; not yet published.

FGS 1.0 specifies a portable semantic document. It intentionally did not
promise identical-looking pages. Separate HTML, Python/PyMuPDF, and Studio
canvas renderers then disagreed on category-label weight, spacing, and fit.
Tuning each by eye did not remove the cause.

We therefore maintain a versioned browser-and-Node JavaScript renderer in
`packages/fgs-renderer/`. Its single point-based display list drives SVG preview and vector
PDF. Forge pins the browser and Node bundles and runs the latter in an
unprivileged, bounded subprocess after Python validates the FGS input. Studio
pins the same browser bundle and runs entirely locally in the browser. Exact
build hashes are recorded in a manifest and verified in both repositories.
Forge's image adds a Node runtime for this approved exception to the general
server-rendered preference.

The appearance contract is `docs/FGS_PAGE_RENDERING_PROFILE_1_0.md` with ID
`fgs-page-1.0`, distinct from the FGS document schema. It applies the accent
to page and section titles as well as section rules, while retaining neutral
table text. This avoids falsely claiming that all FGS 1.0 readers
produce identical PDFs. Pixel screenshots serve as regression evidence, not
layout coordinates. A future FGS minor version may pin a page rendering profile in a
document; FGS 1.0 files do not yet do so. The package, container build,
headless browser path, and full Unicode fallback require further verification
before publication or a general conformance claim.
