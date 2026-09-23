# FGS v1 specification

Status: Version 1.0

FGS 1.1 adds an optional header logo and author footer; see the separate
[FGS 1.1 specification](FGS_V1_1_SPECIFICATION.md). This 1.0 definition
remains valid for existing files.

FGS is the portable, application-independent source format for a GameSheet.
Forge GameSheets is one editor and renderer, but a conforming file must not
depend on a Forge installation, database, library, web route, or local path.
Version 1 deliberately standardizes only the capabilities proven by the current
Sheet Designer.

## Representation

- Files use the `.fgs` extension and contain UTF-8 JSON without a byte-order
  mark. Duplicate object keys and non-finite numbers are invalid.
- Forge uses the project media type `application/vnd.forge-gamesheets+json`.
- Property order and insignificant whitespace have no semantic meaning. Forge
  exports two-space-indented JSON with sorted keys and a trailing line feed.
- Every file declares `"format": "forge-gamesheets"` and
  `"format_version": "1.0"`.

JSON is the v1 representation. The working browser and Python implementations,
deterministic exports, strict parsing, and standard JSON Schema tooling provide
the compelling portability and security reason anticipated by the roadmap's
earlier YAML preference.

## Versioning and compatibility

Versions use `major.minor` form. Patch releases clarify the specification or
fix implementations and do not appear in documents.

- A minor revision may add optional capabilities without changing earlier
  meanings. A 1.x implementation must read earlier supported 1.x documents.
- A major revision may make incompatible changes.
- An editor must not silently save an unsupported version. It must migrate it
  through a defined migration or leave it unchanged and report the problem.
- A renderer may offer an explicitly labelled best-effort preview of a newer
  minor version, but must not overwrite it or claim conformance.
- Unknown ordinary properties are invalid. Namespaced `extensions` are the only
  extension point and must be preserved when an editor saves their parent.
- Experimental `0.1-prototype` files are not v1. Migration must validate and
  transform them; implementations must never merely relabel them.

## Validation and safety

[`schemas/fgs-v1.schema.json`](schemas/fgs-v1.schema.json) is normative. Readers
must validate the complete document before storing, editing, or rendering it.
Document, row, and block IDs must also be globally unique within the document.
Forge limits imported files to 256 KiB. Implementations must apply reasonable
parser limits, reject prohibited control characters, and never interpret text
as code, formulas, templates, HTML, URLs, or filesystem paths.

## Document model

The root contains `format`, `format_version`, `id`, `title`, `page`, `theme`,
`rows`, and optional `extensions`.

`id` is a stable portable-document identity, not an editor's storage key.
Importing colliding IDs must not silently overwrite a local sheet. Duplicating
a sheet creates a new document ID. All IDs are opaque, 1–64 character ASCII
strings matching `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.

`page.size` is `letter` or `a4`; `page.orientation` is `portrait` or
`landscape`. v1 produces one page. Overflow must be reported rather than
silently clipped or converted to an extra page. `theme.accent` is a lowercase
six-digit sRGB color (`#rrggbb`).

`rows` defines reading and rendering order. A row contains one full-width block
or two equal-width blocks in array order. It contains no coordinates. FGS v1
guarantees semantic interoperability, not pixel-identical rendering.

Applications that want consistent page layout may implement the separate,
versioned [FGS Page Rendering Profile 1.0](FGS_PAGE_RENDERING_PROFILE_1_0.md). The profile is a
separate rendering contract and does not add fields to FGS 1.0 or change its semantic
compatibility promise. A future minor FGS version may allow a document to pin
a page rendering profile explicitly.

## Blocks

Every block has a globally unique `id`, `type`, `title`, and optional
`extensions`.

- `header`: primary `title` plus `subtitle`; either may be empty.
- `score_table`: 1–12 `players`, 1–30 `score_rows`, `show_total`, and
  `total_label`. Empty player headings render as `Player N`. Cells are blank
  writable areas; v1 stores no scores or formulas.
- `reference`: 1–30 ordered `items`, rendered as reference bullets.
- `checklist`: 1–30 ordered `items`, each rendered with an unchecked box. v1
  stores no checked state.
- `notes`: 1–20 blank writing `lines`.

Field length and required-property rules are defined by the schema. Text is
Unicode. Editors may trim outer whitespace from single-line fields but must not
otherwise rewrite content.

Forge's optional LiveSheet target recognizes score rows named exactly `Total`
or `Grand Total`, ignoring capitalization and surrounding whitespace, as
calculated rows. This does not make runtime scores part of FGS v1. The legacy
`show_total` and `total_label` representation remains valid; Forge presents that
summary as a visible row when it is edited and saves new tables with visible
row-driven totals.

## Extensions

An `extensions` object maps reverse-domain names, such as
`org.example.print-marks`, to JSON values. Extensions cannot weaken validation,
alter standard-field meanings, execute code, or grant resource access. An
editor unable to preserve an extension must refuse to save the enclosing
object.

## Deferred from 1.0

FGS 1.1 adds one header logo and an author footer. General images, resource
references, absolute placement, custom fonts, calculations,
page breaks, repeating page elements, multiple pages, saved field values,
scripts, HTML, ownership, and Forge library metadata are future capabilities.
