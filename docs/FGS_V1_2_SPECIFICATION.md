# FGS 1.2 specification

Status: Version 1.2, implemented locally; not yet published.
FGS 1.2 extends [FGS 1.1](FGS_V1_1_SPECIFICATION.md). A 1.2 reader must
accept valid 1.0 and 1.1 files. Documents using either addition below declare
`"format_version": "1.2"`. The normative structural schema is
[fgs-v1.2.schema.json](schemas/fgs-v1.2.schema.json). All previous limits,
decoded-logo validation, unique-ID rules, and namespaced extensions still apply.

## Designer Notes

The root may contain `designer_notes`: optional plain text, from zero to
4,000 Unicode characters. LF and TAB are allowed; other C0 control characters
and DEL are invalid. Whitespace and line breaks are preserved. Editors may omit
the property when the field is empty. This is one document-level attribute,
not a movable content block and not the existing rendered `notes` block.

Editors show it as **Designer Notes**, for the author or future editors.
It must not appear in the rendered page, SVG preview, PDF text or metadata,
printed output, or LiveSheet presentation. It consumes no page space and has
no effect on fit. Forge omits it from newly created LiveSheet snapshots.
Readers preserve it when importing, saving, duplicating, or exporting FGS.
It remains readable in the shared FGS JSON: it is editorial metadata, not a
private or encrypted field. Users must not put credentials or secrets here.

## Score-table first column heading

A `score_table` block may contain `first_column_heading`: nonblank,
single-line plain text of at most 80 Unicode characters. C0 control characters
and DEL are invalid. If omitted, its effective value is **Category**, including
in LiveSheets and for all older FGS files. Editors trim surrounding whitespace;
clearing the field restores the default and may omit the property.

This labels only the first column. It does not rename the block, change score-row
labels, alter player headings, or influence scoring/calculation rules. The
existing `title` property is unchanged; its editor label is **Score table title**.

```json
{
  "type": "score_table",
  "title": "Brains Eaten",
  "first_column_heading": "Round"
}
```

This is an illustrative fragment, not a complete valid block.

## Rendering and compatibility

The [FGS Page Rendering Profile 1.2](FGS_PAGE_RENDERING_PROFILE_1_2.md)
defines first-column header wrapping and preserves all previous geometry
when the new field is absent. Both products use the same pinned renderer build
for SVG and PDF. Designer Notes never enter its display list.

Editors retain a document's existing version until a new capability is used.
Adding Designer Notes or a nondefault first-column heading promotes the file
to 1.2; adding a logo or footer to a 1.2 file must never downgrade it to 1.1.
Removing an optional field need not downgrade the version. Older strict readers
must reject 1.2 rather than silently drop its content. Import/export, undo/redo,
PDF text/layout, and immutable LiveSheet snapshot behavior are tested.
