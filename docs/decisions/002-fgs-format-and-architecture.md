# 002 — FGS is the portable structured GameSheet format

## Status

Accepted for roadmap and future architecture. This record does not define the
FGS v1 schema or authorize implementation during Phase 1.5 or BGG integration.

## Decision

**Forge GameSheets** is the application. **FGS** is the application's native
structured GameSheet format, and `.fgs` is its portable file extension. An
**FGS file** is editable structured source. A **GameSheet** is a human-readable
result rendered from that source.

Use these terms consistently:

- **Forge GameSheets** — the self-hosted application and project.
- **FGS** — the native structured GameSheet format.
- **FGS file** — a portable source document using the `.fgs` extension.
- **GameSheet** — a rendered output produced from an FGS file.
- **FGS Editor** — functionality that creates or modifies FGS files.
- **FGS Renderer** — functionality that renders FGS files.
- **FGS Library** — the collection of FGS files associated with library
  entries.

Do not use "Forge GameSheets file" for an FGS file where it could be confused
with a file belonging to the application.

## Product boundary

FGS is a portable, structured, declarative definition of a GameSheet. It is not
merely a configuration file for a board-game quick-reference PDF.

The initial Forge use case remains tabletop games, but FGS must be broad enough
for:

- quick references, setup guides, player aids, and scoring sheets;
- character, NPC, encounter, campaign, roster, unit, and tracking sheets;
- card, yard-game, golf, fishing, league, and tournament scoring;
- brackets, checklists, logs, trackers, and custom/home-created games.

FGS must support three broad document styles:

1. **Reference sheets**, which primarily present static information.
2. **Record or score sheets**, which primarily provide writable fields.
3. **Hybrid sheets**, which combine reference material and tracking areas.

The schema must not assume that every document is a commercial board game,
rules reference, static page, text-only page, or PDF.

## Source and rendering model

An FGS file is the structured source. Rendered targets may include:

```text
.fgs source
    |
    +-- PDF
    +-- print output
    +-- browser-rendered view
    +-- future interactive or display outputs
```

The formal schema should favor semantic structure over hard-coded PDF
coordinates wherever practical. It should describe what information exists,
how it is grouped, which fields repeat, which calculations apply, and general
rendering intent.

Schema design must anticipate, without requiring all features in v1:

- headings, text, images, tables, and grids;
- writable fields, blank lines, checkboxes, counters, and score fields;
- repeated rows and sections;
- labels, calculated totals, and constrained formulas;
- QR codes, page breaks, and multi-page documents;
- static print rendering and future interactive browser behavior.

FGS remains declarative. It is not an executable scripting language.

## Representation and versioning

FGS will be a plain-text, human-readable, editable format. YAML is the preferred
representation unless formal schema work identifies a compelling reason to use
another structured text format.

Every production FGS file must contain an explicit format/schema version from
the first version onward. The importer and renderer must use that version for
compatibility, validation, and future migration. The `.fgs` extension alone is
not a compatibility signal.

Any examples shown before formal schema approval are illustrative and must not
be treated as the FGS v1 specification.

## Storage and portability

A library entry may have zero, one, or many independent FGS files. The data
model must not assume one FGS per game.

An FGS file must be portable between Forge installations. It must not depend on:

- a Forge database ID;
- an absolute path from the originating installation;
- a private runtime cache;
- the continued availability of the installation that created it.

Users should eventually be able to export, copy, share, import, associate,
edit, render, and download an FGS file. Existing PDFs remain static artifacts;
they are not interchangeable with editable FGS sources.

## External identifiers and BoardGameGeek

An FGS may contain an optional BoardGameGeek ID or other external identifier.
This can associate differently titled local and shared documents with the same
game, but a BGG ID is not required for a valid FGS.

BGG matching for a Forge library entry and optional BGG metadata inside an FGS
are related but separate concerns. Non-BGG use cases such as a private golf
outing, homemade game, or custom tournament must remain first-class.

## Import security

All imported FGS files are untrusted input. The future importer must:

- validate the declared schema and supported version;
- reject malformed or unexpected structures;
- reject executable or script content;
- constrain local and external resource references;
- prevent path traversal and arbitrary filesystem access;
- impose practical size, nesting, repetition, and calculation limits;
- return useful validation errors without partially trusting the document.

Arbitrary code execution is prohibited unless a future security review makes a
new explicit decision.

## Sharing and content boundary

Forge is private, self-hosted tooling, not a public FGS repository. Users may
independently share both a rendered GameSheet and its editable source, for
example a PDF and a corresponding `.fgs` file.

BoardGameGeek Files may become an external community-sharing location. During
the structured FGS phase, investigate `forgegamesheets` as the canonical
discovery convention; `fgs` may be shorthand but is too generic to be the
canonical identifier. Do not scrape BGG Files or automate uploads without an
officially supported API and a later explicit decision.

Forge distributes software and original fictional examples, not copyrighted
rulebooks, commercial sheets, community-created FGS files, or other third-party
game content. Existing operator-responsibility notices remain applicable.

## Implementation sequence

When the FGS phase begins, design and approve the FGS v1 schema before building
the FGS Editor or FGS Renderer. Schema design must explicitly evaluate:

- document and game metadata;
- optional external identifiers;
- sections and content blocks;
- tables, fields, repetition, images, and calculations;
- semantic structure versus layout hints;
- page behavior and output targets;
- validation and constrained resource references;
- portability and schema migration;
- forward/backward compatibility;
- static and interactive rendering.

Current work must preserve these boundaries but must not implement the schema,
editor, or renderer ahead of the approved phase.
