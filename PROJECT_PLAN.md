# Forge GameSheets Project Plan

Status labels used below:

- **Confirmed** — approved planning baseline; do not redesign casually.
- **Proposed** — preferred implementation direction, subject to validation.
- **Future idea** — deliberately outside the current milestone.

## 1. Project identity

- **Confirmed:** Product name: **Forge GameSheets**
- **Confirmed:** Tagline: **Organize. Customize. Print. Play.**
- **Confirmed:** Repository and container naming: `forge-gamesheets`
- **Confirmed:** The product is a self-hosted printable-game-resource library
  and, in later phases, a print-on-demand document forge.
- **Confirmed:** Brand artwork exists outside this repository and will be added
  to `app/static/brand/` when an approved source asset is available.

## 2. Problem and hosting model

Board-game rules, score sheets, quick references, player aids, and other
printables tend to be scattered across folders and websites. Forge GameSheets
will provide one browsable, searchable place to organize and print them.

- **Confirmed:** The application will be self-hosted.
- **Confirmed:** Docker Compose is the target packaging and runtime workflow.
- **Confirmed:** The library, configuration, and application data remain in
  ordinary host directories so they are portable and easy to back up.
- **Confirmed:** Production is expected eventually under
  `/opt/forge-gamesheets/`, but production deployment is not part of repository
  setup or the first development milestone.
- **Confirmed:** No cloud service is required for core operation.

## 3. Design principles

1. **Confirmed:** The filesystem is authoritative for library content.
2. **Confirmed:** SQLite is an index/cache and stores application state; PDF
   blobs do not belong in the database.
3. **Confirmed:** Existing PDFs work without metadata or database entry.
4. **Confirmed:** Naming conventions improve discovery but are not mandatory.
   Unrecognized files remain accessible as `Other` rather than being rejected.
5. **Confirmed:** First-level library directories represent games; PDFs are
   discovered recursively within them.
6. **Confirmed:** The UI must work well on phones, tablets, and desktops.
7. **Confirmed:** Static PDFs and future generated documents are both modeled
   as resources belonging to a game.
8. **Confirmed:** Dynamic document generation is outside Phase 1.
9. **Confirmed:** External enrichment services are outside the MVP.
10. **Confirmed:** Work should proceed in small, tested Git commits.

## 4. Filesystem convention

The expected basic layout is:

```text
library/
├── Yahtzee/
│   ├── Yahtzee - Rules.pdf
│   ├── Yahtzee - Score Sheet.pdf
│   └── Yahtzee - Quick Reference.pdf
└── Farkle/
    ├── Farkle - Rules.pdf
    └── Farkle - Scoring Reference.pdf
```

- **Confirmed:** Folder name supplies the default game name.
- **Confirmed:** Preferred filename shape is
  `<Game Name> - <Document Type> [optional variant].pdf`.
- **Confirmed:** The parser must be tolerant of deviations.
- **Confirmed:** Common aliases normalize to stable categories. Examples:
  `rules`, `score_sheet`, `reference`, `answer_sheet`, `tournament`, `setup`,
  and `other`. Instructions normalize to rules; player aids and cheat sheets
  normalize to player references.
- **Proposed:** Optional `game.yaml` and document sidecars can later provide
  titles, aliases, tags, player counts, paper information, and overrides.
  Sidecars must never be required for basic discovery.

## 5. Resource model

A game owns resources. In Phase 1, the only provider is a discovered PDF. Later
providers may include generated PDFs, HTML references, images, or links.

Minimum Phase 1 concepts:

- Game: stable identity, display title, filesystem path, timestamps.
- Resource: game, provider/type, category, title/variant, source path, file
  identity, timestamps, and availability state.
- Application state: favorite, recent use, print history, and scanner status.

- **Confirmed:** Files removed from the filesystem must not remain falsely
  available after a successful scan.
- **Proposed:** Use stable derived identifiers where possible so rescans preserve
  application state when files are unchanged.
- **Proposed:** Keep scanner, filename parser, persistence, HTTP layer, and UI
  concerns independently testable.

## 6. Phase 1 — PDF library and manager

### Core milestone

- Scan a configured library root.
- Treat each first-level directory as a game.
- Discover PDFs recursively.
- Infer document category and variant from forgiving filenames.
- Persist the current index in SQLite.
- Browse all games and open a game's resources.
- Search games and documents.
- View, download, and use browser printing for PDFs.
- Manually rescan the library and report useful results/errors.
- Provide tests for discovery, parsing, reconciliation, and path safety.

### Phase 1 completion features

- Favorites.
- Recently used resources.
- PDF thumbnails/previews.
- Print/use history.
- Clear empty, unavailable, malformed, and partial-scan states.
- Responsive and accessible navigation.

### Explicitly out of scope for Phase 1

- Editing source PDFs.
- Dynamic score-sheet generation.
- QR stamping or public reprint links.
- Visual template design.
- BoardGameGeek or other external metadata integration.
- User accounts, remote synchronization, or cloud storage.
- Automatic production deployment.

## 7. Phase 1.5 — Forge Mark and QR reprints

- **Confirmed roadmap:** Offer optional printable copies with a small Forge Mark,
  brief reprint instructions, and a QR code.
- **Confirmed:** QR destinations open a resource page with view/print actions;
  scanning must not trigger printing automatically.
- **Proposed:** Stable application URLs should survive display-title changes.
- **Future idea:** Configurable branding/footer placement and access policies.

## 8. Phase 2 — declarative print-on-demand generation

Phase 2 introduces configurable templates as another resource provider rather
than replacing the Phase 1 library.

- **Confirmed:** Templates describe documents declaratively; do not hardcode a
  separate renderer for every game.
- **Confirmed:** Generic primitives and a layout engine handle tables, text,
  scoring rows, repeated cards, margins, orientation, and pagination.
- **Confirmed:** Preserve the lifecycle:
  template → saved configuration → immutable print snapshot.
- **Confirmed:** Layout supports full sheet (1 item), half sheet (2 items), and
  quarter sheet (4 items), with templates able to restrict unreadable sizes.
- **Confirmed:** Generated and static resources coexist in the same game view.

Representative user stories include configurable Yacht-style score sheets,
Farkle round sheets, Bunco packs, Euchre tournament assignments, randomized
Bingo cards, and tasting/judging sheets. These examples preserve product intent;
they are not all Phase 2 launch requirements.

## 9. Phase 3 — design and advanced workflows

- **Future idea:** Visual template designer.
- **Future idea:** Multi-document game-night packs.
- **Future idea:** Advanced layout and print optimization.
- **Future idea:** Template import, export, and sharing.
- **Future idea:** Optional external library enrichment.

## 10. Proposed technical baseline

- Python web application using FastAPI.
- Server-rendered responsive interface initially; avoid an unnecessary separate
  frontend build until product needs justify it.
- SQLite for index/cache and application state.
- SQL migrations from the first persisted schema.
- Filesystem adapters for library discovery and safe PDF delivery.
- Pytest for unit and integration tests.
- Ruff for formatting and linting; type checking can be added when the initial
  code shape is established.
- Docker image and `compose.yml` for reproducible development and later hosting.

These are proposed implementation choices, not permission to expand Phase 1.

## 11. Development and Git strategy

- Keep `main` in a runnable, tested state.
- Make one focused change per commit; include tests with the behavior they cover.
- Prefer vertical milestones that can be demonstrated locally.
- Record meaningful architecture decisions under `docs/decisions/`.
- Never commit real personal library PDFs, local databases, secrets, or generated
  runtime data.

Suggested early commits after this scaffold:

1. Minimal FastAPI health endpoint and test.
2. Library configuration and path validation.
3. Filesystem scanner with fixture-based tests.
4. Forgiving filename/category parser with table-driven tests.
5. SQLite schema, migrations, and scan reconciliation.
6. Read-only library and game views.
7. Safe PDF view/download behavior.
8. Search and manual rescan.

## 12. Decisions to preserve

- Do not store source PDFs in SQLite.
- Do not reject resources because filenames are imperfect.
- Do not require sidecar metadata.
- Do not hardcode individual games into application logic.
- Do not let future generation needs distort the Phase 1 scope, but keep the
  resource abstraction compatible with them.
- Do not expose arbitrary filesystem paths through the web application.
- Do not begin production deployment until the local milestones are tested and
  production host, port, storage, permissions, backups, and access are reviewed.

## 13. Open questions for incremental validation

- Exact rules for recognizing game folders below the first level.
- Filename precedence and the initial category alias table.
- Whether missing files are immediately removed from the index or retained as
  unavailable for a short diagnostic/history window.
- Thumbnail generation library and cache invalidation strategy.
- Whether print history records an explicit in-app action or only resource use,
  since browser printing cannot always be observed reliably.
- Authentication and network exposure expectations for eventual deployment.

Open questions should be resolved through small implementation experiments and
documented decisions, not broad redesigns.
