# Sheet Designer beta boundary

Sheet Designer is an integrated Forge beta feature based on the approved
structured-composer specification and mockup. Its current narrow scope proves
the editing model, standalone boundary, Forge integration, and deterministic
PDF output while the [formal FGS v1 specification](FGS_V1_SPECIFICATION.md) is
stabilized through migration and conformance testing.

## Current scope

- Letter and A4 pages in portrait or landscape
- Header, score table, reference, checklist, and notes sections
- Dynamic score rows edited one per line, plus an optional, renameable summary row
- Numbered-row generation with a custom label, starting number, and row count
- Live one-line-per-item editing for reminder and checklist sections
- Full-width and two-column section rows
- Add, edit, duplicate, delete, drag, and arrow-button reordering
- Undo and redo for the current browser session
- Atomically saved local draft recovery
- A multi-sheet workspace with create, open, rename-through-title, duplicate,
  and delete workflows
- Import and export of experimental `.fgs` files
- Deterministic, single-page PDF export with overflow refusal
- The invented Expedition Score Sheet as the initial fixture

The integrated route is available to Admins and Contributors. Its drafts form a
shared installation-wide collection, like the shared PDF library; per-user
ownership is not part of v1. Either role can change or delete any saved draft.
Important FGS source should therefore be exported periodically and before
significant shared edits or deletion, in addition to normal application-data
backups. The standalone shell intentionally has no account system and should
only be bound to localhost for development.

## Architectural boundary

`app/sheet_designer/` owns the semantic model, validation, file-backed sheet
workspace, edit commands, and PDF renderer. Its storage root and HTTP template
adapter are injected by the host:

- Forge uses `<data>/sheet-designer/` and its normal Admin access control.
- The standalone shell uses `FORGE_SHEET_DESIGNER_DATA`, defaulting to
  `/tmp/forge-sheet-designer`, and does not initialize the Forge database or
  scan the PDF library.

Each sheet is stored as an independent `.fgs` draft. The active-sheet pointer
is separate from those portable documents, and the original single-draft file
is migrated automatically on first use.

Designer state is not stored in the main SQLite database and generated sheets
are not automatically indexed into the PDF library. This preserves the
filesystem-as-source-of-truth rule while ownership, game association, and
publication workflows remain undecided.

## Deliberate specification adaptations

New files use formal JSON-based FGS `1.0`. Existing `0.1-prototype` drafts are
validated and migrated when opened; they are never merely relabelled. Files
contain stable semantic IDs, no Forge database IDs, and no local paths. Imported
files are strictly validated and size-limited. FGS v1 formalizes compatibility,
namespaced extensions, and the separation between portable document identity
and an editor's local workspace identity.

The mockup's advanced-placement control is omitted because arbitrary placement
is outside the approved structured-layout scope. The first integration is
Admin-only because the current application has no document-ownership model;
multi-user ownership and sharing are later design decisions.

## Run the standalone shell

From the repository root:

```sh
.venv/bin/uvicorn app.sheet_designer.standalone:app --reload --port 8765
```

Open <http://127.0.0.1:8765/sheet-designer>. To retain the draft somewhere
other than the temporary default, set `FORGE_SHEET_DESIGNER_DATA` to a writable
development directory before starting the shell.

The integrated editor appears as **Sheet Designer** in the main navigation when
the normal Forge application is running. It is visible to Admins and
Contributors, who work in the same shared draft workspace.

## Deferred decisions

- Future FGS capabilities beyond the deliberately narrow v1 contract
- Ownership, game association, and library import
- Responsive editing beyond basic stacking on small screens
- Multi-page output, repeating elements, image blocks, and style controls
- Publication of generated PDFs into the indexed library
- Collaboration, sharing, templates, and arbitrary canvas placement
