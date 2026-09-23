# FGS 1.1 specification

Status: Version 1.1. FGS 1.1 extends [FGS 1.0](FGS_V1_SPECIFICATION.md)
without changing its fields. A 1.1 reader must continue to accept valid 1.0 files.
Documents using the additions below declare `"format_version": "1.1"`. The normative
structural schema is [fgs-v1.1.schema.json](schemas/fgs-v1.1.schema.json); the
additional decoded-image checks below are normative too.

## Author footer

The root may contain `footer`, a one- or two-line plain-text credit of at most
160 Unicode characters including a single optional line feed. Neither line may
be blank. Other control characters are invalid. The footer is presentation
content, not a URL, an executable link, a rights claim supplied by Forge, or a
FORGE Reprint footer. On a LiveSheet it follows the sheet content.

## Header logo

At most one `header` block per document may contain `logo`. The logo moves with
that header row. Its value has exactly these fields:

```json
{
  "media_type": "image/png",
  "data": "BASE64_PNG_BYTES",
  "alt": "Game logo",
  "decorative": false
}
```

`data` is canonical, padded RFC 4648 base64 without a data-URL prefix or
whitespace. Decoded content must be a valid, non-animated PNG of at most 128 KiB, with width
and height from 1 to 1024 pixels and at most one million total pixels. Readers
must verify the decoded image, not trust the media type or PNG header alone.
Informative logos require nonblank `alt` of at most 120 characters. Decorative
logos use `"decorative": true` and empty `alt`. Alt text is available to
LiveSheet and SVG preview; the current PDF renderer does not produce tagged
PDFs and cannot promise equivalent PDF image accessibility.

Editors may accept JPEG input but must normalize it to PNG before saving FGS.
The image bytes are embedded in JSON to keep this deliberately single-logo
version portable as one `.fgs` file. This increases file size and makes image
data opaque in diffs. The existing 256 KiB FGS document limit still applies.
FGSZ bundles and separate image sections are not part of 1.1.

## Rendering and LiveSheet

The [FGS Page Rendering Profile 1.1](FGS_PAGE_RENDERING_PROFILE_1_1.md)
defines the logo box, footer placement, and single-page fit rules. A LiveSheet
uses the logo and footer from its immutable FGS snapshot; neither is scoring
state. Source edits affect new sessions only.
