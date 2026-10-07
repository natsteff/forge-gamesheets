# FGS format and version history

FGS is the portable, JSON-based source format for structured GameSheets. The
current file version is **1.4**. An `.fgs` file can be opened in the integrated
FORGE GameSheets Sheet Designer or in the browser-only
[FGS Studio](https://natsteff.github.io/FGS-Studio/). It is not a PDF, and
FGS 1.4 can store finished-size and print-sheet defaults while allowing export
overrides. The file-format version and page-rendering-profile version are
separate: FGS 1.4 still uses Page Rendering Profile 1.3.1.

## Current specification

The specification is cumulative. **The version additions are not complete
standalone documents**: read the base format, then each version's additions.

1. [FGS 1.0 base specification](FGS_V1_SPECIFICATION.md)
2. [FGS 1.1 additions](FGS_V1_1_SPECIFICATION.md) — footer and header logo
3. [FGS 1.2 additions](FGS_V1_2_SPECIFICATION.md) — Designer Notes and table headings
4. [FGS 1.3 additions](FGS_V1_3_SPECIFICATION.md) — trackers and paper patterns
5. [FGS 1.4 additions](FGS_V1_4_SPECIFICATION.md) — portable print defaults

For machine validation, use the
[current FGS 1.4 JSON Schema](schemas/fgs-v1.4.schema.json). Earlier schemas
remain available for [1.0](schemas/fgs-v1.schema.json),
[1.1](schemas/fgs-v1.1.schema.json), and
[1.2](schemas/fgs-v1.2.schema.json), and [1.3](schemas/fgs-v1.3.schema.json).

File structure and printed appearance are separate contracts. The current
[Page Rendering Profile 1.3.1](FGS_PAGE_RENDERING_PROFILE_1_3.md) defines
single-page layout and fit for FGS 1.0–1.4. FGS 1.4 changed which print defaults
can be saved in the file, not the rendering geometry; there is no separate
Profile 1.4. Earlier rendering profiles are retained for
[1.0](FGS_PAGE_RENDERING_PROFILE_1_0.md),
[1.1](FGS_PAGE_RENDERING_PROFILE_1_1.md), and
[1.2](FGS_PAGE_RENDERING_PROFILE_1_2.md).
The editable source and tests are in the
[FGS Renderer package](../packages/fgs-renderer/README.md); published
FORGE GameSheets images include a verified, version-pinned build.

## Creating and using FGS files

See the [Sheet Designer guide](SHEET_DESIGNER.md) for creating, importing,
exporting, and backing up sheets, and the
[finished-size printing guide](PRINT_SIZE_PRINTING.md) for Half Page, card,
and custom-size output. Compatible score sheets can be used as temporary
LiveSheets without writing scores into the reusable FGS source.

An LLM can help draft an FGS file from a score-sheet image or PDF when given
the cumulative specification above. Review the result as untrusted input and
verify labels, calculations, and layout before importing it. Only share source
documents with that service when you have permission to do so.
