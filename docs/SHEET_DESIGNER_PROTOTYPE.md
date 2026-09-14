# Sheet Designer beta boundary

Sheet Designer is an integrated Forge beta feature based on the approved
structured-composer specification and mockup. Its current narrow scope proves
the editing model, standalone boundary, Forge integration, and deterministic
PDF output before the formal FGS v1 format is designed.

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

The integrated route is an Admin feature. The standalone shell intentionally
has no account system and should only be bound to localhost for development.

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

The project plan says the formal FGS v1 schema should be designed before the
production editor and prefers YAML. The prototype specification permits JSON
for the experiment. To avoid accidentally declaring an incompatible v1, files
use JSON with the explicit version `0.1-prototype`. They contain stable semantic
IDs, no Forge database IDs, and no local paths. Imported files are strictly
validated and size-limited.

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
the normal Forge application is running. It remains visible only to Admins while
document ownership and sharing are undecided.

## Deferred decisions

- Formal human-authored FGS v1 syntax and schema
- Ownership, game association, and library import
- Responsive editing beyond basic stacking on small screens
- Multi-page output, repeating elements, image blocks, and style controls
- Publication of generated PDFs into the indexed library
- Collaboration, sharing, templates, and arbitrary canvas placement
